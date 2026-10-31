"""Scope policy and conservative version-counterpart selection for hybrid search."""

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evidencedesk.contracts.models import Document, Hit, Passage, QueryInput, Scope
from evidencedesk.retrieval.bm25 import tokenize


@dataclass(frozen=True)
class Evidence:
    document: Document
    passage: Passage

    @property
    def passage_id(self) -> str:
        return self.passage.passage_id

    @property
    def lexical_text(self) -> str:
        return "\n".join([
            self.document.metadata.title,
            *self.passage.section_path,
            self.passage.text,
        ])


def matches_scope(document: Document, scope: Scope) -> bool:
    """Product/environment ignore case; an explicitly selected version is exact."""
    for field in ("product", "version", "environment"):
        wanted = getattr(scope, field)
        if wanted is None:
            continue
        actual = getattr(document.metadata, field)
        if actual is None:
            return False
        if field == "version":
            if actual != wanted:
                return False
        elif actual.casefold() != wanted.casefold():
            return False
    return True


def make_hit(
    evidence: Evidence,
    *,
    rank: int,
    bm25_score: float | None = None,
    cosine_score: float | None = None,
    rrf_score: float = 0.0,
    counterpart: bool = False,
    scope: Scope,
) -> Hit:
    return Hit(
        document=evidence.document.model_copy(deep=True),
        passage=evidence.passage.model_copy(deep=True),
        rank=rank,
        bm25_score=bm25_score,
        cosine_score=cosine_score,
        rrf_score=rrf_score,
        selection="version_counterpart" if counterpart else "ranked",
        applicable=matches_scope(evidence.document, scope),
    )


def _heading(passage: Passage) -> tuple[str, ...]:
    return tuple(
        unicodedata.normalize("NFKC", part).strip().casefold()
        for part in passage.section_path
        if part.strip()
    )


def _same_optional_scope(left: str | None, right: str | None) -> bool:
    return left is right if left is None or right is None else left.casefold() == right.casefold()


def _version_section(evidence: Evidence) -> tuple:
    metadata = evidence.document.metadata
    return (
        metadata.family_id,
        metadata.version,
        metadata.product.casefold() if metadata.product is not None else None,
        metadata.environment.casefold() if metadata.environment is not None else None,
        _heading(evidence.passage),
    )


def _is_counterpart(anchor: Evidence, candidate: Evidence) -> bool:
    left, right = anchor.document.metadata, candidate.document.metadata
    if (
        anchor.document.document_id == candidate.document.document_id
        or not left.family_id
        or left.family_id != right.family_id
        or not left.version
        or not right.version
        or left.version == right.version
        or not _same_optional_scope(left.product, right.product)
        or not _same_optional_scope(left.environment, right.environment)
    ):
        return False
    heading = _heading(anchor.passage)
    if heading:
        return heading == _heading(candidate.passage)
    return (
        not _heading(candidate.passage)
        and anchor.document.passage_count == 1
        and candidate.document.passage_count == 1
    )


def select_version_counterparts(
    ranked: Sequence[Hit],
    corpus: Mapping[str, Evidence],
    query: QueryInput,
    *,
    max_hits: int = 6,
    max_counterparts: int = 2,
) -> tuple[list[Hit], list[str]]:
    """Reserve comparison slots while always retaining their highest-ranked anchors.

    Counterparts require explicit family/version metadata plus matching headings
    (or two single-passage documents). No newest-version assumption is made.
    """
    if max_hits < 1 or not 0 <= max_counterparts < max_hits:
        raise ValueError("Counterpart budget must leave at least one ranked evidence slot.")
    anchors = list(ranked[: max_hits - max_counterparts])
    protected = {hit.passage.passage_id for hit in anchors}
    protected_versions = {
        _version_section(corpus[hit.passage.passage_id]) for hit in anchors
    }
    original = {hit.passage.passage_id: hit for hit in ranked}
    query_terms = set(tokenize(query.question))
    candidates = []
    for anchor_rank, hit in enumerate(anchors, start=1):
        anchor = corpus[hit.passage.passage_id]
        anchor_terms = set(tokenize(anchor.passage.text))
        for candidate_id, candidate in corpus.items():
            if candidate_id in protected or not _is_counterpart(anchor, candidate):
                continue
            terms = set(tokenize(candidate.passage.text))
            shared = len(anchor_terms & terms) / max(1, len(anchor_terms | terms))
            query_overlap = len(query_terms & terms) / max(1, len(query_terms))
            signature = _version_section(candidate)
            if signature in protected_versions:
                continue
            candidates.append((
                (anchor_rank, -(shared + query_overlap), candidate_id), signature, candidate,
            ))
    candidates.sort(key=lambda item: item[0])
    chosen: list[Evidence] = []
    chosen_ids: set[str] = set()
    represented = set()
    available = set()
    for _, signature, candidate in candidates:
        available.add(signature)
        if signature in represented or candidate.passage_id in chosen_ids:
            continue
        if len(chosen) < max_counterparts:
            chosen.append(candidate)
            chosen_ids.add(candidate.passage_id)
            represented.add(signature)
    results = [
        hit.model_copy(deep=True)
        for hit in ranked
        if hit.passage.passage_id not in chosen_ids
    ][: max_hits - len(chosen)]
    for candidate in chosen:
        previous = original.get(candidate.passage_id)
        results.append(make_hit(
            candidate,
            rank=len(results) + 1,
            bm25_score=previous.bm25_score if previous else None,
            cosine_score=previous.cosine_score if previous else None,
            rrf_score=previous.rrf_score if previous else 0.0,
            counterpart=True,
            scope=query.context,
        ))
    for rank, hit in enumerate(results, start=1):
        hit.rank = rank
        hit.applicable = matches_scope(hit.document, query.context)
    warnings = []
    if any(hit.selection == "version_counterpart" and not hit.applicable for hit in results):
        warnings.append(
            "Other-version evidence is included for comparison and is not applicable to "
            "the selected version. It must not support factual answer claims."
        )
    if len(available) > len(represented):
        warnings.append("Additional matching version passages were omitted by the comparison budget.")
    return results, warnings
