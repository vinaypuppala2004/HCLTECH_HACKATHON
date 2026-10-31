"""Real local Qdrant files with synthetic embeddings: persistence and failure semantics."""

import json
import subprocess
import sys
from hashlib import sha256

import pytest

from evidencedesk.contracts.models import EmbeddingOutput, QueryInput, Scope, SourcesInput
from evidencedesk.core.responses import failure, success
from evidencedesk.mocks.fixtures import mock_hit
from evidencedesk.retrieval.embeddings import EMBEDDING_MODEL
from evidencedesk.retrieval.index import QdrantIndex
from evidencedesk.retrieval.projection import CompactEmbeddings


class SyntheticEmbeddings:
    def __init__(self):
        self.calls = 0
        self.digest = "a" * 64
        self.fail = False

    def __call__(self, request):
        self.calls += 1
        if self.fail:
            return failure("MODEL_TIMEOUT", "Simulated timeout.", retryable=True)
        vectors = [[1, 0, 0, 0] if "password" in text else [0, 1, 0, 0] for text in request.texts]
        return success(
            EmbeddingOutput(
                model=EMBEDDING_MODEL, model_digest=self.digest, dimensions=4, vectors=vectors
            )
        )


@pytest.fixture
def embedder():
    return SyntheticEmbeddings()


def compact(native, dimensions=3):
    return CompactEmbeddings(native, source_dimensions=4, dimensions=dimensions)


def document(doc_id="guide", text="Reset your password in the account portal.", *, version="v1"):
    hit = mock_hit()
    doc = hit.document
    doc.document_id = doc_id
    doc.filename = f"{doc_id}.txt"
    doc.metadata.product = "Demo"
    doc.metadata.version = version
    doc.metadata.environment = "Production"
    doc.sha256 = sha256(text.encode()).hexdigest()
    passage = hit.passage
    passage.document_id = doc_id
    passage.passage_id = f"{doc_id}/passage"
    passage.text = text
    return doc, [passage]


def query(**scope):
    return QueryInput(
        question="How do I reset my password?",
        context=Scope(
            product=scope.get("product"),
            version=scope.get("version"),
            environment=scope.get("environment"),
        ),
    )


def test_persist_search_sources_and_revision_survive_reopen(tmp_path, embedder):
    doc, passages = document()
    doc.format = "pdf"
    passages[0].page = 7
    passages[0].section_path = ["Account", "Reset"]
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.search(query()).error.code == "INDEX_EMPTY"
        result = index.index_document(doc, passages)
        assert result.ok and result.data.results[0].state == "ready"
        assert result.data.index_revision == 1
        assert index.document_count == 1
    with QdrantIndex(tmp_path, compact(embedder)) as restarted:
        assert restarted.index_revision == 1
        result = restarted.search(query())
        assert result.ok and result.data.hits[0].passage == passages[0]
        assert result.data.hits[0].document == doc
        assert result.data.hits[0].cosine_score == pytest.approx(1)
        source = restarted.read_sources(SourcesInput(document_id=doc.document_id)).data
        assert source.passages == passages and source.documents == [doc]
        summary = restarted.read_sources(SourcesInput(document_id=None)).data
        assert summary.documents == [doc] and summary.passages == []


def test_duplicate_is_idempotent_and_replacement_hides_old_generation(tmp_path, embedder):
    doc, passages = document()
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(doc, passages).ok
        before = embedder.calls
        assert index.index_document(doc, passages).data.results[0].state == "duplicate"
        assert embedder.calls == before and index.index_revision == 1
        doc, changed = document(text="Reset your password using the recovery page.")
        changed[0].passage_id = "replacement"
        assert index.index_document(doc, changed).data.index_revision == 2
        assert index.search(query()).data.hits[0].passage.passage_id == "replacement"
        assert index.read_sources(SourcesInput(document_id="guide")).data.passages == changed
        assert index._client.count("evidencedesk_passages_v1", exact=True).count == 1


def test_scope_matching_and_six_hit_cap(tmp_path, embedder):
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        for number in range(8):
            doc, passages = document(str(number), version="v1" if number < 7 else "V1")
            assert index.index_document(doc, passages).ok
        result = index.search(query(product="demo", environment="PRODUCTION", version="v1")).data
        assert len(result.hits) == 6
        assert all(hit.document.metadata.version == "v1" and hit.applicable for hit in result.hits)
        assert [hit.rank for hit in result.hits] == [1, 2, 3, 4, 5, 6]
        before = embedder.calls
        assert index.search(query(product="Other")).data.hits == []
        assert embedder.calls == before


@pytest.mark.parametrize("invalid", ["count", "owner", "blank", "page", "id"])
def test_invalid_documents_do_not_call_model_or_appear_ready(tmp_path, embedder, invalid):
    doc, passages = document()
    if invalid == "count":
        doc.passage_count = 2
    elif invalid == "owner":
        passages[0].document_id = "wrong"
    elif invalid == "blank":
        passages[0].text = " "
    elif invalid == "page":
        passages[0].page = 1
    else:
        passages[0].passage_id = ""
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(doc, passages).error.code == "BAD_INPUT"
        assert embedder.calls == 0
        assert index.index_revision == 0 and index.document_count == 0


def test_empty_limit_and_global_duplicate_ids_are_rejected(tmp_path, embedder):
    doc, passages = document()
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(doc, []).error.code == "EMPTY_DOCUMENT"
        doc.passage_count = 501
        many = [passages[0].model_copy(update={"passage_id": str(i)}) for i in range(501)]
        assert index.index_document(doc, many).error.code == "BAD_INPUT"
        doc.passage_count = 1
        assert index.index_document(doc, passages).ok
        other, others = document("other")
        others[0].passage_id = passages[0].passage_id
        assert index.index_document(other, others).error.code == "BAD_INPUT"
        assert index.document_count == 1


def test_model_failure_and_digest_change_never_commit(tmp_path, embedder):
    doc, passages = document()
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        embedder.fail = True
        assert index.index_document(doc, passages).error.code == "MODEL_TIMEOUT"
        assert index.index_revision == 0
        embedder.fail = False
        assert index.index_document(doc, passages).ok
        embedder.digest = "b" * 64
        assert index.search(query()).error.code == "EMBEDDING_UNAVAILABLE"
        other, other_passages = document("other")
        assert index.index_document(other, other_passages).error.code == "EMBEDDING_UNAVAILABLE"
        assert index.index_revision == 1 and index.document_count == 1


def test_dimension_profile_mismatch_fails_without_locking_path(tmp_path, embedder):
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(*document()).ok
    with pytest.raises(ValueError, match="profile"):
        QdrantIndex(tmp_path, compact(embedder, dimensions=2))
    with QdrantIndex(tmp_path, compact(embedder)) as reopened:
        assert reopened.document_count == 1


def test_partial_data_write_is_invisible_after_restart(tmp_path, embedder, monkeypatch):
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(*document()).ok
        original = index._client.upsert

        def partial_write(collection_name, *, points, **kwargs):
            if collection_name == "evidencedesk_passages_v1":
                original(collection_name, points=points[:1], **kwargs)
                raise OSError("Simulated interrupted indexing.")
            return original(collection_name, points=points, **kwargs)

        monkeypatch.setattr(index._client, "upsert", partial_write)
        result = index.index_document(*document("unfinished"))
        assert not result.ok and not index.ready
        assert index.search(query()).error.code == "INTERNAL_ERROR"
    with QdrantIndex(tmp_path, compact(embedder)) as reopened:
        assert reopened.index_revision == 1 and reopened.document_count == 1
        assert (
            reopened.read_sources(SourcesInput(document_id="unfinished")).error.code == "NOT_FOUND"
        )
        assert reopened.search(query()).data.hits[0].document.document_id == "guide"


def test_closed_index_and_second_writer_are_explicit(tmp_path, embedder):
    index = QdrantIndex(tmp_path, compact(embedder))
    with pytest.raises(RuntimeError, match="already"):
        QdrantIndex(tmp_path, compact(embedder))
    index.close()
    assert not index.ready and index.search(query()).error.code == "INTERNAL_ERROR"
    index.close()


def test_sources_survive_an_actual_python_process_restart(tmp_path, embedder):
    with QdrantIndex(tmp_path, compact(embedder)) as index:
        assert index.index_document(*document()).ok
    code = """
import json, sys
from evidencedesk.contracts.models import SourcesInput
from evidencedesk.retrieval.index import QdrantIndex
from evidencedesk.retrieval.projection import CompactEmbeddings
embedder = CompactEmbeddings(lambda _: None, source_dimensions=4, dimensions=3)
with QdrantIndex(sys.argv[1], embedder) as index:
    source = index.read_sources(SourcesInput(document_id='guide')).data
    print(json.dumps({'revision': index.index_revision, 'text': source.passages[0].text}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    assert data == {"revision": 1, "text": document()[1][0].text}
