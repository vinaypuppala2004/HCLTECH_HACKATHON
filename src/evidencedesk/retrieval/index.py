"""Backend-owned local Qdrant persistence with committed document generations."""

import json
import logging
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Literal, Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field
from qdrant_client import QdrantClient, models

from evidencedesk.contracts.models import (
    Contract,
    Document,
    EmbeddingInput,
    Envelope,
    IngestItem,
    IngestResult,
    Passage,
    QueryInput,
    Scope,
    SearchResult,
    SourcesInput,
    SourcesResult,
)
from evidencedesk.core.responses import failure, success
from evidencedesk.retrieval.bm25 import BM25Corpus, reciprocal_rank_fusion
from evidencedesk.retrieval.hybrid import (
    Evidence,
    make_hit,
    matches_scope,
    select_version_counterparts,
)
from evidencedesk.retrieval.projection import CompactEmbeddings

_POINTS = "evidencedesk_passages_v1"
_STATE = "evidencedesk_state_v1"
_STATE_ID = str(uuid5(NAMESPACE_URL, "evidencedesk/committed-state/v1"))
_LOG = logging.getLogger(__name__)


class _StoredDocument(Contract):
    document: Document
    generation: str = Field(min_length=1)
    passage_ids: list[str]
    fingerprint: str


class _IndexState(Contract):
    format_version: Literal[1]
    profile: dict[str, object]
    model_digest: str | None
    index_revision: int = Field(ge=0)
    documents: dict[str, _StoredDocument]


class QdrantIndex:
    """Own one local client per backend process; close it before reopening the path.

    New passage generations stay invisible until a single state point commits
    their document metadata and revision. Old generations are then garbage-collected.
    """

    def __init__(self, path: str | Path, embedder: CompactEmbeddings):
        self._embedder = embedder
        self._lock = RLock()
        self._closed = False
        self._unhealthy = False
        self._corpus_revision = -1
        self._evidence: dict[str, Evidence] = {}
        self._lexical: BM25Corpus | None = None
        self._client = QdrantClient(path=str(path))
        try:
            self._state = self._open_state()
            self._validate_committed_points()
            self._cleanup()
        except Exception:
            self._client.close()
            raise

    @property
    def index_revision(self) -> int:
        return self._state.index_revision

    @property
    def document_count(self) -> int:
        return len(self._state.documents)

    @property
    def ready(self) -> bool:
        return not self._closed and not self._unhealthy

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._client.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def index_document(
        self, document: Document, passages: Sequence[Passage]
    ) -> Envelope[IngestResult]:
        with self._lock:
            if not self.ready:
                return self._unavailable()
            if not passages:
                return failure("EMPTY_DOCUMENT", "No passages were supplied for indexing.")
            passages = [passage.model_copy(deep=True) for passage in passages]
            document = document.model_copy(deep=True)
            ids = [passage.passage_id for passage in passages]
            occupied = {
                passage_id
                for doc_id, entry in self._state.documents.items()
                if doc_id != document.document_id
                for passage_id in entry.passage_ids
            }
            total = sum(
                entry.document.passage_count
                for doc_id, entry in self._state.documents.items()
                if doc_id != document.document_id
            ) + len(passages)
            if (
                not document.document_id
                or document.passage_count != len(passages)
                or len(set(ids)) != len(ids)
                or any(not passage_id or passage_id in occupied for passage_id in ids)
                or total > 500
                or any(
                    passage.document_id != document.document_id
                    or not passage.text.strip()
                    or (document.format != "pdf" and passage.page is not None)
                    for passage in passages
                )
            ):
                return failure(
                    "BAD_INPUT", "Invalid passages, duplicate IDs, or 500-passage limit exceeded."
                )
            encoded = json.dumps(
                [document.model_dump(mode="json"), [p.model_dump(mode="json") for p in passages]],
                sort_keys=True,
                ensure_ascii=False,
            )
            fingerprint = sha256(encoded.encode()).hexdigest()
            existing = self._state.documents.get(document.document_id)
            if existing and existing.fingerprint == fingerprint:
                return self._receipt(document, "duplicate")
            response = self._embedder(
                EmbeddingInput(texts=[passage.text for passage in passages], kind="document")
            )
            if not response.ok or response.data is None:
                return response
            embedded = response.data
            if self._state.model_digest not in (None, embedded.model_digest):
                return failure(
                    "EMBEDDING_UNAVAILABLE", "Model digest changed; rebuild in a new index path."
                )
            generation = uuid4().hex
            points = [
                models.PointStruct(
                    id=str(
                        uuid5(
                            NAMESPACE_URL,
                            json.dumps([document.document_id, generation, passage.passage_id]),
                        )
                    ),
                    vector=vector,
                    payload={
                        "generation": generation,
                        "document": document.model_dump(mode="json"),
                        "passage": passage.model_dump(mode="json"),
                    },
                )
                for passage, vector in zip(passages, embedded.vectors, strict=True)
            ]
            updated = self._state.model_copy(deep=True)
            updated.model_digest = embedded.model_digest
            updated.index_revision += 1
            updated.documents[document.document_id] = _StoredDocument(
                document=document,
                generation=generation,
                passage_ids=ids,
                fingerprint=fingerprint,
            )
            try:
                self._client.upsert(_POINTS, points=points, wait=True)
                self._save_state(updated)
                self._state = updated
                self._corpus_revision = -1
            except Exception:
                self._unhealthy = True
                _LOG.exception("Qdrant write failed; close and reopen before using the index.")
                return self._unavailable()
            self._cleanup()
            return self._receipt(document, "ready")

    def search(self, request: QueryInput) -> Envelope[SearchResult]:
        """Fuse scope-filtered BM25 and Nomic rankings, then add version comparisons."""
        with self._lock:
            if not self.ready:
                return self._unavailable()
            if not self._state.documents:
                return failure("INDEX_EMPTY", "No documents have been committed to the index.")
            generations = self._generations(request.context)
            if not generations:
                return success(
                    SearchResult(
                        index_revision=self.index_revision,
                        hits=[],
                        warnings=["No committed passages match the selected scope."],
                    )
                )
            try:
                self._ensure_corpus()
                eligible = {
                    passage_id
                    for passage_id, evidence in self._evidence.items()
                    if matches_scope(evidence.document, request.context)
                }
                if not eligible:
                    raise ValueError("Committed document metadata has no corresponding passages.")
            except Exception:
                _LOG.exception("The committed retrieval corpus could not be loaded.")
                return failure("INTERNAL_ERROR", "Committed retrieval data could not be loaded.")
            response = self._embedder(EmbeddingInput(texts=[request.question], kind="query"))
            if not response.ok or response.data is None:
                return response
            if response.data.model_digest != self._state.model_digest:
                return failure(
                    "EMBEDDING_UNAVAILABLE", "Model digest changed; rebuild in a new index path."
                )
            try:
                result = self._client.query_points(
                    _POINTS,
                    query=response.data.vectors[0],
                    query_filter=self._generation_filter(generations),
                    limit=len(eligible),
                    with_payload=True,
                )
                semantic_scores = {}
                for point in result.points:
                    passage_id = point.payload["passage"]["passage_id"]
                    if passage_id not in eligible or passage_id in semantic_scores:
                        raise ValueError("Unexpected or duplicate semantic search passage.")
                    semantic_scores[passage_id] = point.score
                if set(semantic_scores) != eligible:
                    raise ValueError("Semantic results do not cover the committed scoped passages.")
                lexical_scores = self._lexical.scores(request.question, eligible)
                return self._compose_result(request, lexical_scores, semantic_scores)
            except Exception:
                _LOG.exception("Hybrid retrieval failed.")
                return failure(
                    "INTERNAL_ERROR", "Hybrid search failed; inspect and reopen the index."
                )

    def search_lexical(self, request: QueryInput) -> Envelope[SearchResult]:
        """Explicit BM25-only port; hybrid search never silently downgrades to this."""
        with self._lock:
            if not self.ready:
                return self._unavailable()
            if not self._state.documents:
                return failure("INDEX_EMPTY", "No documents have been committed to the index.")
            try:
                self._ensure_corpus()
                eligible = {
                    passage_id
                    for passage_id, evidence in self._evidence.items()
                    if matches_scope(evidence.document, request.context)
                }
                if not eligible:
                    return success(SearchResult(
                        index_revision=self.index_revision,
                        hits=[],
                        warnings=["No committed passages match the selected scope."],
                    ))
                return self._compose_result(
                    request,
                    self._lexical.scores(request.question, eligible),
                    {},
                    warnings=["BM25-only retrieval was explicitly selected; semantic ranking was not used."],
                )
            except Exception:
                _LOG.exception("Lexical retrieval failed.")
                return failure("INTERNAL_ERROR", "BM25 search failed; inspect and reopen the index.")

    def _compose_result(
        self,
        request: QueryInput,
        lexical_scores: dict[str, float],
        semantic_scores: dict[str, float],
        *,
        warnings: list[str] | None = None,
    ) -> Envelope[SearchResult]:
        ranking = reciprocal_rank_fusion(lexical_scores, semantic_scores)
        ranked = [
            make_hit(
                self._evidence[passage_id],
                rank=rank,
                bm25_score=lexical_scores.get(passage_id, 0.0),
                cosine_score=semantic_scores.get(passage_id),
                rrf_score=score,
                scope=request.context,
            )
            for rank, (passage_id, score) in enumerate(ranking, start=1)
        ]
        hits, comparison_warnings = select_version_counterparts(ranked, self._evidence, request)
        messages = list(warnings or [])
        messages.extend(comparison_warnings)
        if not any(score > 0 for score in lexical_scores.values()):
            messages.append("No lexical matches were found in the selected scope.")
        return success(SearchResult(
            index_revision=self.index_revision, hits=hits, warnings=messages
        ))

    def _ensure_corpus(self) -> None:
        if self._corpus_revision == self.index_revision and self._lexical is not None:
            return
        corpus: dict[str, Evidence] = {}
        records = self._scroll(self._generation_filter(self._generations()))
        for point in records:
            document = Document.model_validate(point.payload["document"])
            passage = Passage.model_validate(point.payload["passage"])
            entry = self._state.documents.get(document.document_id)
            if (
                entry is None
                or point.payload["generation"] != entry.generation
                or document != entry.document
                or passage.document_id != document.document_id
                or passage.passage_id not in entry.passage_ids
                or passage.passage_id in corpus
            ):
                raise ValueError("Stored passages do not match the committed corpus.")
            corpus[passage.passage_id] = Evidence(document=document, passage=passage)
        expected = sum(entry.document.passage_count for entry in self._state.documents.values())
        if len(corpus) != expected:
            raise ValueError("Committed corpus passage counts do not match.")
        lexical = BM25Corpus({
            passage_id: evidence.lexical_text for passage_id, evidence in corpus.items()
        })
        self._evidence = corpus
        self._lexical = lexical
        self._corpus_revision = self.index_revision

    def read_sources(self, request: SourcesInput) -> Envelope[SourcesResult]:
        with self._lock:
            if not self.ready:
                return self._unavailable()
            if request.document_id is None:
                return success(
                    SourcesResult(
                        documents=[
                            self._state.documents[key].document.model_copy(deep=True)
                            for key in sorted(self._state.documents)
                        ],
                        passages=[],
                    )
                )
            entry = self._state.documents.get(request.document_id)
            if entry is None:
                return failure("NOT_FOUND", "Document not found in the committed index.")
            try:
                records = self._scroll(self._generation_filter([entry.generation]))
                passages = {
                    point.payload["passage"]["passage_id"]: Passage.model_validate(
                        point.payload["passage"]
                    )
                    for point in records
                }
                return success(
                    SourcesResult(
                        documents=[entry.document.model_copy(deep=True)],
                        passages=[passages[passage_id] for passage_id in entry.passage_ids],
                    )
                )
            except Exception:
                return failure("INTERNAL_ERROR", "Stored source data could not be read.")

    def _open_state(self) -> _IndexState:
        exists = [self._client.collection_exists(name) for name in (_POINTS, _STATE)]
        if not any(exists):
            self._client.create_collection(
                _POINTS,
                vectors_config=models.VectorParams(
                    size=self._embedder.profile.dimensions, distance=models.Distance.COSINE
                ),
            )
            self._client.create_collection(
                _STATE, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT)
            )
            state = _IndexState(
                format_version=1,
                profile=self._embedder.profile.as_dict(),
                model_digest=None,
                index_revision=0,
                documents={},
            )
            self._save_state(state)
            return state
        if not all(exists):
            raise ValueError("Incomplete index collections; inspect the path before reopening.")
        records = self._client.retrieve(_STATE, ids=[_STATE_ID], with_payload=True)
        if len(records) != 1:
            raise ValueError("Committed index metadata is missing.")
        state = _IndexState.model_validate(records[0].payload)
        vectors = self._client.get_collection(_POINTS).config.params.vectors
        if (
            state.profile != self._embedder.profile.as_dict()
            or vectors.size != self._embedder.profile.dimensions
            or vectors.distance != models.Distance.COSINE
        ):
            raise ValueError(
                "Embedding profile/dimensions differ; use the matching profile or a new path."
            )
        return state

    def _save_state(self, state: _IndexState) -> None:
        self._client.upsert(
            _STATE,
            points=[
                models.PointStruct(
                    id=_STATE_ID, vector=[1.0], payload=state.model_dump(mode="json")
                )
            ],
            wait=True,
        )

    def _validate_committed_points(self) -> None:
        entries = self._state.documents
        count = sum(entry.document.passage_count for entry in entries.values())
        if count > 500 or (entries and not self._state.model_digest):
            raise ValueError("Invalid committed index metadata.")
        expected = {}
        for doc_id, entry in entries.items():
            if (
                doc_id != entry.document.document_id
                or len(entry.passage_ids) != entry.document.passage_count
            ):
                raise ValueError("Document metadata and passage counts do not match.")
            for passage_id in entry.passage_ids:
                if passage_id in expected:
                    raise ValueError("Duplicate committed passage IDs.")
                expected[passage_id] = entry
        records = self._scroll(self._generation_filter(self._generations())) if entries else []
        if len(records) != count:
            raise ValueError("Committed passage count does not match stored points.")
        for point in records:
            passage = Passage.model_validate(point.payload["passage"])
            entry = expected.pop(passage.passage_id, None)
            if (
                entry is None
                or point.payload["generation"] != entry.generation
                or point.payload["document"] != entry.document.model_dump(mode="json")
                or passage.document_id != entry.document.document_id
            ):
                raise ValueError("Stored evidence does not match the committed document.")

    def _generations(self, scope: Scope | None = None) -> list[str]:
        return [
            entry.generation
            for entry in self._state.documents.values()
            if scope is None or matches_scope(entry.document, scope)
        ]

    @staticmethod
    def _generation_filter(generations: list[str]) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="generation", match=models.MatchAny(any=generations))]
        )

    def _scroll(self, selection: models.Filter) -> list:
        result, offset = [], None
        while True:
            points, offset = self._client.scroll(
                _POINTS, scroll_filter=selection, limit=500, offset=offset, with_payload=True
            )
            result.extend(points)
            if offset is None:
                return result

    def _cleanup(self) -> None:
        generations = self._generations()
        selection = (
            models.Filter(must_not=self._generation_filter(generations).must)
            if generations
            else models.Filter()
        )
        try:
            self._client.delete(_POINTS, points_selector=selection, wait=True)
        except Exception:
            _LOG.warning("Uncommitted/obsolete points could not be removed; cleanup deferred.")

    def _receipt(
        self, document: Document, state: Literal["ready", "duplicate"]
    ) -> Envelope[IngestResult]:
        return success(
            IngestResult(
                index_revision=self.index_revision,
                results=[
                    IngestItem(
                        filename=document.filename,
                        state=state,
                        document_id=document.document_id,
                        passage_count=document.passage_count,
                        error=None,
                    )
                ],
            )
        )

    @staticmethod
    def _unavailable() -> Envelope:
        return failure(
            "INTERNAL_ERROR",
            "Index unavailable; close and reopen to inspect the committed revision.",
        )
