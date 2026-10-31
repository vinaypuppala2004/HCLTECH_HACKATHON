"""Validate D3 labels and the frozen synthetic holdout without running evaluation."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from evidencedesk.contracts.models import Draft, QueryInput, SourcesResult

DATA_ROOT = Path(__file__).parent / "data" / "synthetic-v1"
CATEGORY_COUNTS = {
    "direct": 8,
    "paraphrase": 6,
    "conflict_version": 4,
    "ambiguous": 3,
    "unsupported": 3,
}


class LabelledCase(BaseModel):
    """An evaluation-local label, not a change to any public API contract."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    category: Literal["direct", "paraphrase", "conflict_version", "ambiguous", "unsupported"]
    query: QueryInput
    expected: Draft
    relevant_passage_ids: list[str]
    rationale: str = Field(min_length=1)


class Freeze(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: Literal["synthetic-v1"]
    origin: Literal["synthetic"]
    frozen_on: Literal["2026-10-31"]
    heldout_case_ids: list[str]
    heldout_family_ids: list[str]
    heldout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def content_hash(value) -> str:
    """Hash JSON content independently of indentation and checkout line endings."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_cases(
    split: Literal["development", "heldout"] = "development", root: Path = DATA_ROOT
) -> list[LabelledCase]:
    if split not in ("development", "heldout"):
        raise ValueError("Select development or heldout explicitly.")
    if split == "heldout":
        _check_freeze(root)
    return TypeAdapter(list[LabelledCase]).validate_python(read_json(root / f"{split}.json"))


def _check_freeze(root: Path) -> Freeze:
    freeze = Freeze.model_validate(read_json(root / "freeze.json"))
    for filename, expected in (
        ("heldout.json", freeze.heldout_sha256),
        ("sources.json", freeze.sources_sha256),
    ):
        if content_hash(read_json(root / filename)) != expected:
            raise ValueError(f"Frozen content changed: {filename}. Create a new dataset version.")
    return freeze


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _applicable(metadata, scope) -> bool:
    return all(
        selected is None
        or (
            actual is not None
            and (
                actual == selected
                if field == "version"
                else actual.casefold() == selected.casefold()
            )
        )
        for field in ("product", "version", "environment")
        for selected, actual in [(getattr(scope, field), getattr(metadata, field))]
    )


def _validate_case(case, documents, passages):
    prefix = f"{case.case_id}: "
    expected = case.expected
    relevant = case.relevant_passage_ids
    _require(len(relevant) == len(set(relevant)), prefix + "duplicate relevant passage")
    _require(all(pid in passages for pid in relevant), prefix + "unknown relevant passage")
    supports = [support for claim in expected.claims for support in claim.supports]
    sides = [side for conflict in expected.conflicts for side in conflict.sides]
    for support in [*supports, *sides]:
        _require(support.passage_id in passages, prefix + "unknown quoted passage")
        _require(
            bool(support.quote) and support.quote in passages[support.passage_id].text,
            prefix + "quote must be an exact nonempty excerpt",
        )
    for claim in expected.claims:
        _require(
            any(
                _applicable(
                    documents[passages[s.passage_id].document_id].metadata, case.query.context
                )
                for s in claim.supports
            ),
            prefix + "claim needs applicable evidence",
        )
    for conflict in expected.conflicts:
        side_ids = {side.passage_id for side in conflict.sides}
        _require(len(side_ids) >= 2, prefix + "conflict needs distinct passages")
        _require(
            set(conflict.selected_passage_ids) <= side_ids,
            prefix + "selected evidence is not a side",
        )
        if conflict.resolution == "resolved_by_context":
            _require(
                bool(conflict.selected_passage_ids), prefix + "resolution needs selected evidence"
            )
            _require(
                all(
                    _applicable(documents[passages[pid].document_id].metadata, case.query.context)
                    for pid in conflict.selected_passage_ids
                ),
                prefix + "selected conflict evidence is outside scope",
            )
        else:
            _require(
                not conflict.selected_passage_ids, prefix + "unresolved conflict selects no side"
            )
    if case.category in ("direct", "paraphrase"):
        _require(expected.status == "answered", prefix + "answer label required")
    elif case.category == "conflict_version":
        _require(bool(expected.conflicts), prefix + "conflict label required")
    elif case.category == "ambiguous":
        _require(expected.status == "needs_context", prefix + "clarification label required")
    else:
        _require(expected.status == "not_found", prefix + "unsupported label must decline")
    if expected.status == "answered":
        _require(bool(expected.claims), prefix + "answer needs claims")
    elif expected.status == "conflict":
        _require(bool(expected.conflicts) and not expected.claims, prefix + "expose conflict only")
    else:
        _require(not expected.claims, prefix + "fallback/clarification must not assert facts")
    if expected.status == "needs_context":
        clarification = expected.clarification
        _require(clarification is not None, prefix + "missing clarification")
        _require(
            getattr(case.query.context, clarification.field) is None,
            prefix + "scope already supplied",
        )
        options = {
            getattr(documents[passages[pid].document_id].metadata, clarification.field)
            for pid in relevant
        }
        _require(
            None not in options and len(options) >= 2 and set(clarification.options) == options,
            prefix + "clarification options must match relevant source metadata",
        )
    else:
        _require(expected.clarification is None, prefix + "unexpected clarification")
        _require(
            set(relevant) == {s.passage_id for s in [*supports, *sides]},
            prefix + "relevant passages must match labelled evidence",
        )
    if expected.status == "not_found":
        _require(
            expected.fallback_reason == "no_support" and not relevant and not expected.conflicts,
            prefix + "unsupported cases must have no fabricated evidence",
        )
    else:
        _require(expected.fallback_reason is None, prefix + "unexpected fallback reason")


def validate_dataset(root: Path = DATA_ROOT) -> dict[str, int]:
    freeze = _check_freeze(root)
    sources = SourcesResult.model_validate(read_json(root / "sources.json"))
    documents = {doc.document_id: doc for doc in sources.documents}
    passages = {passage.passage_id: passage for passage in sources.passages}
    _require(len(documents) == len(sources.documents), "Duplicate document IDs")
    _require(len(passages) == len(sources.passages), "Duplicate passage IDs")
    for passage in sources.passages:
        _require(passage.document_id in documents, "Passage references an unknown document")
        _require(passage.page is None, "Synthetic TXT passages must not invent PDF page locations")
    for doc in sources.documents:
        _require(doc.metadata.origin == "synthetic", "Source must be explicitly synthetic")
        _require(doc.metadata.source_url is None, "Synthetic sources must not claim public URLs")
        texts = [p.text for p in sources.passages if p.document_id == doc.document_id]
        _require(bool(texts) and doc.passage_count == len(texts), "Incorrect source passage count")
        _require(
            doc.sha256 == hashlib.sha256("\n".join(texts).encode()).hexdigest(),
            "Source text hash mismatch",
        )
    development = load_cases(root=root)
    heldout = load_cases("heldout", root)
    _require(
        len(development) == 16 and len(heldout) == 8, "Expected 16 development and 8 held-out cases"
    )
    all_cases = development + heldout
    _require(len({case.case_id for case in all_cases}) == 24, "Case IDs must be unique")
    _require(
        len({" ".join(case.query.question.casefold().split()) for case in all_cases}) == 24,
        "Duplicate questions",
    )
    _require(
        Counter(case.category for case in all_cases) == CATEGORY_COUNTS, "Category counts differ"
    )
    dev_families = {case.family_id for case in development}
    heldout_families = {case.family_id for case in heldout}
    _require(not dev_families & heldout_families, "Question families leak across splits")
    _require(
        [case.case_id for case in heldout] == freeze.heldout_case_ids,
        "Held-out membership or order changed",
    )
    _require(heldout_families == set(freeze.heldout_family_ids), "Held-out families changed")
    for case in all_cases:
        _validate_case(case, documents, passages)
    return {"development": len(development), "heldout": len(heldout)}


if __name__ == "__main__":
    counts = validate_dataset()
    print(f"Validated synthetic labels: {counts}. Frozen content intact; no model evaluation run.")
