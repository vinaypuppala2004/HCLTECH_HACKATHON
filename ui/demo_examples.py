"""A5 synthetic presentation data, isolated from the API and its owned mocks."""

from dataclasses import dataclass
from hashlib import sha256

from evidencedesk.contracts.models import (
    Check,
    Claim,
    Clarification,
    Conflict,
    Document,
    Draft,
    Hit,
    Metadata,
    Passage,
    QueryInput,
    QueryResult,
    Scope,
    SearchResult,
    Support,
    Verification,
)


@dataclass(frozen=True)
class DemoExample:
    title: str
    query: QueryInput
    result: QueryResult
    presenter_note: str


def _hit(identifier: str, version: str, minutes: int, rank: int) -> Hit:
    text = f"Password reset links expire after {minutes} minutes."
    return Hit(
        document=Document(
            document_id=f"doc_preview_{identifier}",
            filename=f"synthetic-reset-{identifier}.md",
            format="markdown",
            metadata=Metadata(
                title=f"Synthetic reset guide ({identifier})",
                source_url=None,
                product="DemoPortal",
                version=version,
                environment="sandbox",
                family_id="synthetic-reset-guide",
                published_at=None,
                origin="synthetic",
            ),
            sha256=sha256(text.encode()).hexdigest(),
            passage_count=1,
        ),
        passage=Passage(
            passage_id=f"passage_preview_{identifier}",
            document_id=f"doc_preview_{identifier}",
            section_path=["Account access", "Reset-link expiry"],
            page=None,
            text=text,
        ),
        rank=rank,
        bm25_score=None,
        cosine_score=None,
        rrf_score=0,
        selection="ranked",
        applicable=True,
    )


def _support(hit: Hit) -> Support:
    return Support(passage_id=hit.passage.passage_id, quote=hit.passage.text)


def _draft(status: str, **values) -> Draft:
    return Draft(
        status=status,
        **{"claims": [], "conflicts": [], "clarification": None, "fallback_reason": None, **values},
    )


def _result(draft: Draft, hits: list[Hit]) -> QueryResult:
    passages = {hit.passage.passage_id: hit.passage.text for hit in hits}
    checks = []
    for claim in draft.claims:
        exact = all(
            support.passage_id in passages
            and bool(support.quote)
            and support.quote in passages[support.passage_id]
            for support in claim.supports
        )
        checks.append(
            Check(
                target_type="claim",
                target_id=claim.claim_id,
                quote_valid=exact,
                verdict="supported" if exact else "unsupported",
                reason="Synthetic preview: exact substrings only; no semantic verifier or model.",
            )
        )
    return QueryResult(
        mode="mock",
        result=draft,
        retrieval=SearchResult(index_revision=0, hits=hits, warnings=[]),
        verification=Verification(
            passed=bool(checks) and all(check.quote_valid for check in checks),
            evidence_strength="limited" if hits else "insufficient",
            checks=checks,
        ),
        trace=[],
    )


def demo_examples() -> list[DemoExample]:
    """Return fresh contract-valid examples; nothing is loaded, indexed, or generated."""
    first = _hit("v1", "v1", 15, 1)
    second = _hit("v2", "v2", 30, 2)
    second.selection = "version_counterpart"
    alternate = _hit("v1-alternate", "v1", 30, 2)
    scope_v1 = Scope(product="DemoPortal", version="v1", environment="sandbox")
    scope_v2 = scope_v1.model_copy(update={"version": "v2"})
    no_version = scope_v1.model_copy(update={"version": None})
    question = "When does a password reset link expire?"
    version_conflict = Conflict(
        conflict_id="conflict_preview_versions",
        kind="version_difference",
        topic="Reset-link expiry differs between versions",
        sides=[_support(first), _support(second)],
        resolution="unresolved",
        selected_passage_ids=[],
    )
    resolved = version_conflict.model_copy(
        update={
            "resolution": "resolved_by_context",
            "selected_passage_ids": [second.passage.passage_id],
        }
    )
    selected_first = first.model_copy(
        update={"applicable": False, "selection": "version_counterpart"}
    )
    selected_second = second.model_copy(update={"applicable": True, "selection": "ranked"})
    return [
        DemoExample(
            "1. Cited answer",
            QueryInput(question=question, context=scope_v1),
            _result(
                _draft(
                    "answered",
                    claims=[
                        Claim(
                            claim_id="claim_preview_v1",
                            text=first.passage.text,
                            supports=[_support(first)],
                        )
                    ],
                ),
                [first],
            ),
            "Expand the claim citation. Match its source ID and exact excerpt. The limited check "
            "is a substring check, not a Ragas score or a semantic guarantee.",
        ),
        DemoExample(
            "2. Compare versions",
            QueryInput(question=question, context=no_version),
            _result(_draft("conflict", conflicts=[version_conflict]), [first, second]),
            "Read the 15-minute and 30-minute excerpts side by side. Use this context fills the "
            "preview controls only. Select example 3 to show a separate illustrative resolution.",
        ),
        DemoExample(
            "3. Context selects v2",
            QueryInput(question=question, context=scope_v2),
            _result(
                _draft(
                    "answered",
                    claims=[
                        Claim(
                            claim_id="claim_preview_v2",
                            text=second.passage.text,
                            supports=[_support(second)],
                        )
                    ],
                    conflicts=[resolved],
                ),
                [selected_first, selected_second],
            ),
            "This is a separate fixed example, not the result of a live query. The v2 passage is "
            "marked selected; the v1 counterpart stays visible and is not applicable.",
        ),
        DemoExample(
            "4. Unresolved contradiction",
            QueryInput(question=question, context=scope_v1),
            _result(
                _draft(
                    "conflict",
                    conflicts=[
                        version_conflict.model_copy(
                            update={
                                "conflict_id": "conflict_preview_contradiction",
                                "kind": "contradiction",
                                "topic": "Two sources disagree within v1",
                                "sides": [_support(first), _support(alternate)],
                            }
                        )
                    ],
                ),
                [first, alternate],
            ),
            "Both sources have the same product, version, and environment. The UI keeps the "
            "contradiction unresolved instead of silently choosing one.",
        ),
        DemoExample(
            "5. Missing context",
            QueryInput(question=question, context=no_version),
            _result(
                _draft(
                    "needs_context",
                    clarification=Clarification(
                        field="version",
                        question="Which DemoPortal version do you use?",
                        options=["v1", "v2"],
                    ),
                ),
                [first, second],
            ),
            "Show the clarification question and version options. There is no factual answer "
            "until the required context is supplied to a working backend.",
        ),
        DemoExample(
            "6. No supporting evidence",
            QueryInput(question="What is the lunar deployment policy?", context=scope_v1),
            _result(_draft("not_found", fallback_reason="no_support"), []),
            "The UI says no support was found. It does not invent a policy or a citation.",
        ),
        DemoExample(
            "7. Failed verification",
            QueryInput(question=question, context=scope_v1),
            _result(
                _draft("insufficient_evidence", fallback_reason="failed_verification"), [first]
            ),
            "The answer is withheld because this illustrative result reports failed verification. "
            "No failed claim is promoted into the answer.",
        ),
    ]
