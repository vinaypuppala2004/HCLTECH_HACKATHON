"""A3 claim citations, fallback states, and backend verification details."""

import streamlit as st

from evidencedesk.contracts.models import QueryResult

FALLBACK_REASONS = {
    "no_support": "No supporting passages were found.",
    "weak_evidence": "The available passages provide only weak evidence.",
    "failed_verification": "The draft answer failed verification; no factual answer is shown.",
}


def show_answer(result: QueryResult) -> None:
    draft = result.result
    st.caption(f"Answer status: {draft.status}")
    for warning in result.retrieval.warnings:
        st.warning(warning)
    if draft.status == "needs_context":
        st.info("More context is needed before an answer can be given.")
        if draft.clarification is not None:
            st.write(draft.clarification.question)
            st.caption(f"Context field: {draft.clarification.field}")
            for option in draft.clarification.options:
                st.text(option)
        st.caption("Set the requested context in the sidebar, then submit your question again.")
    elif draft.status == "not_found":
        st.info("No supporting documents were found for this question and context.")
        st.caption("Try a different question or broaden the context.")
    elif draft.status == "insufficient_evidence":
        st.warning("There is not enough verified evidence to answer this question.")
    elif draft.status == "conflict":
        st.info("The sources conflict. Compare the evidence below.")
    if draft.fallback_reason is not None:
        st.caption(f"Reason: {FALLBACK_REASONS[draft.fallback_reason]}")
    if draft.status in {"answered", "conflict"}:
        if draft.claims and not result.verification.passed:
            st.warning("The backend did not verify this answer. Review its checks and citations.")
        if draft.status == "answered" and not draft.claims:
            st.warning("The backend returned no answer claims.")
        show_claims(result)
    elif draft.claims:
        st.warning("The backend included claims in a fallback response; those claims are withheld.")
    with st.expander("Verification details"):
        st.caption(
            f"Backend verification: {'passed' if result.verification.passed else 'not passed'} | "
            f"Evidence strength: {result.verification.evidence_strength}"
        )
        for check in result.verification.checks:
            st.caption(
                f"{check.target_type}: {check.target_id} | Verdict: {check.verdict} | "
                f"Exact quote check: {'passed' if check.quote_valid else 'failed'}"
            )
            st.text(check.reason)


def show_claims(result: QueryResult) -> None:
    hits = {hit.passage.passage_id: hit for hit in result.retrieval.hits}
    for claim in result.result.claims:
        st.write(claim.text)
        st.caption(f"Claim: {claim.claim_id}")
        with st.expander(f"Citations for claim {claim.claim_id}"):
            for number, support in enumerate(claim.supports, start=1):
                st.caption(f"Citation {number} | Passage: {support.passage_id}")
                hit = hits.get(support.passage_id)
                exact_match = (
                    hit is not None and bool(support.quote) and support.quote in hit.passage.text
                )
                if hit is None:
                    st.warning("The cited passage is missing from the retrieved evidence.")
                else:
                    st.text(hit.document.metadata.title)
                    st.caption(
                        f"Source: {hit.document.document_id} | File: {hit.document.filename} | "
                        f"Origin: {hit.document.metadata.origin}"
                    )
                    st.caption(" / ".join(hit.passage.section_path) or "No section heading")
                    if hit.passage.page is not None:
                        st.caption(f"Page: {hit.passage.page}")
                    if hit.document.metadata.source_url is not None:
                        st.text(f"Source URL: {hit.document.metadata.source_url}")
                    if hit.document.metadata.origin == "synthetic":
                        st.caption("Synthetic fixture — mock evidence")
                    if not hit.applicable:
                        st.warning("This passage is not applicable to the submitted context.")
                    if not exact_match:
                        st.warning("The reported excerpt is not an exact match in this passage.")
                st.caption("Exact excerpt" if exact_match else "Reported excerpt — unverified")
                st.text(support.quote)
