"""Deterministic answer stubs. No Ollama inference or semantic verification."""

from evidencedesk.contracts.models import (
    Check,
    Claim,
    Draft,
    DraftInput,
    Envelope,
    Support,
    Verification,
    VerifyInput,
)
from evidencedesk.core.responses import success


def draft_answer(request: DraftInput) -> Envelope[Draft]:
    if not request.retrieval.hits:
        return success(
            Draft(
                status="not_found",
                claims=[],
                conflicts=[],
                clarification=None,
                fallback_reason="no_support",
            )
        )
    passage = request.retrieval.hits[0].passage
    return success(
        Draft(
            status="answered",
            claims=[
                Claim(
                    claim_id="claim_mock_1",
                    text=passage.text,
                    supports=[Support(passage_id=passage.passage_id, quote=passage.text)],
                )
            ],
            conflicts=[],
            clarification=None,
            fallback_reason=None,
        )
    )


def verify_answer(request: VerifyInput) -> Envelope[Verification]:
    passages = {hit.passage.passage_id: hit.passage.text for hit in request.retrieval.hits}
    checks = []
    for claim in request.draft.claims:
        valid = all(
            support.passage_id in passages
            and bool(support.quote)
            and support.quote in passages[support.passage_id]
            for support in claim.supports
        )
        checks.append(
            Check(
                target_type="claim",
                target_id=claim.claim_id,
                quote_valid=valid,
                verdict="supported" if valid else "unsupported",
                reason="Mock quote check only; semantic support is not evaluated.",
            )
        )
    passed = bool(checks) and all(check.quote_valid for check in checks)
    return success(
        Verification(
            passed=passed,
            evidence_strength="limited" if passed else "insufficient",
            checks=checks,
        )
    )
