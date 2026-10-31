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
    hits = {hit.passage.passage_id: hit for hit in request.retrieval.hits}
    checks = []
    for claim in request.draft.claims:
        quote_valid = all(
            support.passage_id in hits
            and bool(support.quote.strip())
            and support.quote in hits[support.passage_id].passage.text
            for support in claim.supports
        )
        applicable = quote_valid and all(
            hits[support.passage_id].applicable for support in claim.supports
        )
        if not quote_valid:
            reason = (
                "Citation must identify a retrieved passage and contain a nonblank exact quote."
            )
        elif not applicable:
            reason = "Cited evidence is not applicable to the selected context."
        else:
            reason = "Quote and applicability checks only; semantic support is not evaluated."
        checks.append(
            Check(
                target_type="claim",
                target_id=claim.claim_id,
                quote_valid=quote_valid,
                verdict="supported" if applicable else "unsupported",
                reason=reason,
            )
        )
    passed = bool(checks) and all(check.verdict == "supported" for check in checks)
    return success(
        Verification(
            passed=passed,
            evidence_strength="limited" if passed else "insufficient",
            checks=checks,
        )
    )
