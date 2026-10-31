"""A3 citations and fallback presentation, using explicitly synthetic responses."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from evidencedesk.contracts.models import (
    Check,
    Claim,
    Clarification,
    Draft,
    QueryResult,
    SearchResult,
    Support,
    Verification,
)
from evidencedesk.mocks.fixtures import mock_hit

UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "app.py"


def answer_result():
    first = mock_hit().model_copy(deep=True)
    first.document.document_id = "doc_synthetic_pdf"
    first.document.filename = "synthetic-guide.pdf"
    first.document.format = "pdf"
    first.document.metadata.title = "Synthetic PDF Guide"
    first.passage.document_id = first.document.document_id
    first.passage.passage_id = "passage_pdf"
    first.passage.page = 4
    first.passage.text = "Before the excerpt. Use the account portal. After the excerpt."
    second = mock_hit().model_copy(deep=True)
    second.passage.text = "First sentence. Contact the support desk. Last sentence."
    second.rank = 2
    return QueryResult(
        mode="mock",
        result=Draft(
            status="answered",
            claims=[
                Claim(
                    claim_id="claim_synthetic_steps",
                    text="Use the portal or contact support.",
                    supports=[
                        Support(
                            passage_id=second.passage.passage_id, quote="Contact the support desk."
                        ),
                        Support(
                            passage_id=first.passage.passage_id, quote="Use the account portal."
                        ),
                    ],
                ),
                Claim(
                    claim_id="claim_synthetic_portal",
                    text="The portal is an option.",
                    supports=[
                        Support(
                            passage_id=first.passage.passage_id, quote="Use the account portal."
                        )
                    ],
                ),
            ],
            conflicts=[],
            clarification=None,
            fallback_reason=None,
        ),
        retrieval=SearchResult(index_revision=1, hits=[first, second], warnings=[]),
        verification=Verification(
            passed=True,
            evidence_strength="limited",
            checks=[
                Check(
                    target_type="claim",
                    target_id="claim_synthetic_steps",
                    quote_valid=True,
                    verdict="supported",
                    reason="Synthetic exact-quote check; semantic support was not evaluated.",
                )
            ],
        ),
        trace=[],
    )


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("BACKEND_URL", "http://127.0.0.1:8000")
    result = answer_result()
    calls = []

    def response(url, *, json, **kwargs):
        assert url == "http://127.0.0.1:8000/v1/query"
        calls.append(json)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_answer",
                "data": result.model_dump(),
                "error": None,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", response)
    yield AppTest.from_file(UI_PATH, default_timeout=15), calls, result


def submit(ui):
    ui.run()
    ui.chat_input[0].set_value("How do I get account support?").run()
    assert not ui.exception


def expander(ui, label):
    return next(element for element in ui.expander if element.label == label)


@pytest.mark.parametrize("mode", ["mock", "live"])
def test_each_claim_has_its_own_citations_and_exact_excerpts(frontend, mode):
    ui, calls, result = frontend
    result.mode = mode
    submit(ui)
    first = expander(ui, "Citations for claim claim_synthetic_steps")
    second = expander(ui, "Citations for claim claim_synthetic_portal")
    assert [text.value for text in first.text] == [
        "Mock Support Guide",
        "Contact the support desk.",
        "Synthetic PDF Guide",
        "Use the account portal.",
    ]
    assert [text.value for text in second.text] == [
        "Synthetic PDF Guide",
        "Use the account portal.",
    ]
    assert any(
        "Citation 1 | Passage: passage_mock_reset" == caption.value for caption in first.caption
    )
    assert any("Citation 2 | Passage: passage_pdf" == caption.value for caption in first.caption)
    assert any(
        "Source: doc_synthetic_pdf | File: synthetic-guide.pdf" in c.value for c in first.caption
    )
    assert any(c.value == "Account access / Password reset" for c in first.caption)
    assert any(c.value == "Page: 4" for c in first.caption)
    assert any(c.value == "Synthetic fixture — mock evidence" for c in first.caption)
    assert not any("http" in text.value for text in first.text), "Do not invent source URLs."
    assert any(f"Mode: {mode}" in c.value for c in ui.caption)
    assert len(calls) == 1


def test_verification_details_are_backend_checks_not_quality_scores(frontend):
    ui, _, _ = frontend
    submit(ui)
    details = expander(ui, "Verification details")
    assert any(
        "Backend verification: passed | Evidence strength: limited" == c.value
        for c in details.caption
    )
    assert any(
        "claim_synthetic_steps | Verdict: supported | Exact quote check: passed" in c.value
        for c in details.caption
    )
    assert "Synthetic exact-quote check; semantic support was not evaluated." in [
        t.value for t in details.text
    ]


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        ("not_found", "no_support", "No supporting documents were found"),
        ("insufficient_evidence", "no_support", "No supporting passages were found"),
        ("insufficient_evidence", "weak_evidence", "only weak evidence"),
        ("insufficient_evidence", "failed_verification", "draft answer failed verification"),
        ("insufficient_evidence", None, "not enough verified evidence"),
    ],
)
def test_fallback_states_explain_reason_and_withhold_factual_claims(
    frontend, status, reason, expected
):
    ui, _, result = frontend
    result.result.status = status
    result.result.fallback_reason = reason
    result.verification.passed = False
    submit(ui)
    messages = [element.value for group in [ui.info, ui.warning, ui.caption] for element in group]
    assert any(expected in message for message in messages)
    assert not any(
        claim.text in element.value for claim in result.result.claims for element in ui.markdown
    )
    assert not any(element.label.startswith("Citations for claim") for element in ui.expander)
    assert any("those claims are withheld" in warning.value for warning in ui.warning)


@pytest.mark.parametrize("field", ["product", "version", "environment"])
def test_needs_context_shows_question_and_options_without_submitting(frontend, field):
    ui, calls, result = frontend
    result.result.status = "needs_context"
    result.result.claims = []
    result.result.clarification = Clarification(
        field=field, question=f"Which {field} do you use?", options=["Option A", "Option B"]
    )
    submit(ui)
    assert f"Which {field} do you use?" in [element.value for element in ui.markdown]
    assert "Option A" in [element.value for element in ui.text]
    assert "Option B" in [element.value for element in ui.text]
    assert any(c.value == f"Context field: {field}" for c in ui.caption)
    assert len(calls) == 1


def test_needs_context_without_clarification_is_still_explicit(frontend):
    ui, _, result = frontend
    result.result.status = "needs_context"
    result.result.claims = []
    submit(ui)
    assert any("More context is needed" in info.value for info in ui.info)
    assert any("sidebar" in caption.value for caption in ui.caption)


@pytest.mark.parametrize("problem", ["missing_passage", "mismatched_quote", "inapplicable"])
def test_citation_problems_are_labelled_without_substituting_evidence(frontend, problem):
    ui, _, result = frontend
    support = result.result.claims[0].supports[0]
    if problem == "missing_passage":
        support.passage_id = "passage_missing"
    elif problem == "mismatched_quote":
        support.quote = "This excerpt does not occur in the passage."
    else:
        result.retrieval.hits[1].applicable = False
    submit(ui)
    citations = expander(ui, "Citations for claim claim_synthetic_steps")
    assert support.quote in [element.value for element in citations.text]
    if problem == "missing_passage":
        assert any("missing from the retrieved evidence" in w.value for w in citations.warning)
        assert not any("Mock Support Guide" == t.value for t in citations.text)
    elif problem == "mismatched_quote":
        assert any("not an exact match" in w.value for w in citations.warning)
    else:
        assert any("not applicable" in w.value for w in citations.warning)


def test_unverified_answer_and_retrieval_warnings_are_visible(frontend):
    ui, _, result = frontend
    result.verification.passed = False
    result.verification.checks[0].quote_valid = False
    result.verification.checks[0].verdict = "unsupported"
    result.retrieval.warnings = ["Synthetic warning: the scope was ignored."]
    submit(ui)
    assert any("backend did not verify" in warning.value for warning in ui.warning)
    assert any("scope was ignored" in warning.value for warning in ui.warning)
    assert any("Verdict: unsupported | Exact quote check: failed" in c.value for c in ui.caption)


def test_empty_answer_is_explicit(frontend):
    ui, _, result = frontend
    result.result.claims = []
    submit(ui)
    assert any("returned no answer claims" in warning.value for warning in ui.warning)


def test_provided_source_url_is_shown_verbatim(frontend):
    ui, _, result = frontend
    result.retrieval.hits[0].document.metadata.source_url = "https://example.org/synthetic-guide"
    submit(ui)
    citations = expander(ui, "Citations for claim claim_synthetic_portal")
    assert "Source URL: https://example.org/synthetic-guide" in [
        text.value for text in citations.text
    ]
