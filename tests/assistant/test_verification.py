"""Citation checks reject evidence that cannot support the selected context."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from evidencedesk.api.app import create_app
from evidencedesk.assistant.tools import draft_answer, verify_answer
from evidencedesk.contracts.models import (
    DraftInput,
    QueryInput,
    Scope,
    SearchResult,
    Support,
    VerifyInput,
)
from evidencedesk.core.factory import build_tools
from evidencedesk.core.responses import success
from evidencedesk.core.settings import Settings
from evidencedesk.mocks.fixtures import DEMO_QUESTION, mock_hit


@pytest.fixture
def request_data():
    query = QueryInput(
        question=DEMO_QUESTION,
        context=Scope(product="Demo", version="v1", environment="demo"),
    )
    retrieval = SearchResult(index_revision=1, hits=[mock_hit()], warnings=[])
    draft = draft_answer(DraftInput(query=query, retrieval=retrieval)).data
    assert draft is not None
    return VerifyInput(query=query, retrieval=retrieval, draft=draft)


def test_applicable_exact_citation_passes_with_limited_strength(request_data):
    response = verify_answer(request_data)

    assert response.ok
    assert response.error is None
    result = response.data
    assert result is not None
    assert result.passed
    assert result.evidence_strength == "limited"
    assert result.checks[0].quote_valid
    assert result.checks[0].verdict == "supported"
    assert "semantic support is not evaluated" in result.checks[0].reason


def test_inapplicable_exact_citation_fails_without_invalidating_quote(request_data):
    request_data.retrieval.hits[0].applicable = False

    result = verify_answer(request_data).data

    assert result is not None
    assert not result.passed
    assert result.evidence_strength == "insufficient"
    assert result.checks[0].quote_valid
    assert result.checks[0].verdict == "unsupported"
    assert "not applicable" in result.checks[0].reason


def test_exact_excerpt_passes_with_unrelated_inapplicable_hit(request_data):
    request_data.draft.claims[0].supports[0].quote = "account portal"
    unrelated = mock_hit()
    unrelated.passage.passage_id = "uncited_passage"
    unrelated.applicable = False
    request_data.retrieval.hits.append(unrelated)

    result = verify_answer(request_data).data

    assert result is not None
    assert result.passed
    assert result.checks[0].quote_valid


@pytest.mark.parametrize("applicable", [True, False])
def test_version_counterpart_uses_applicability_flag(request_data, applicable):
    hit = request_data.retrieval.hits[0]
    hit.selection = "version_counterpart"
    hit.applicable = applicable

    result = verify_answer(request_data).data

    assert result is not None
    assert result.passed is applicable
    assert result.checks[0].quote_valid


@pytest.mark.parametrize(
    ("passage_id", "quote"),
    [
        ("missing_passage", "Use the account portal"),
        ("passage_mock_reset", ""),
        ("passage_mock_reset", " "),
        ("passage_mock_reset", "Reset passwords by email."),
        ("passage_mock_reset", "use the account portal"),
    ],
)
def test_invalid_citations_fail(request_data, passage_id, quote):
    request_data.draft.claims[0].supports = [Support(passage_id=passage_id, quote=quote)]

    result = verify_answer(request_data).data

    assert result is not None
    assert not result.passed
    assert result.evidence_strength == "insufficient"
    assert not result.checks[0].quote_valid
    assert result.checks[0].verdict == "unsupported"


def test_all_citations_on_a_claim_must_be_applicable(request_data):
    other_hit = mock_hit()
    other_hit.passage.passage_id = "other_version"
    other_hit.applicable = False
    other_hit.selection = "version_counterpart"
    request_data.retrieval.hits.append(other_hit)
    request_data.draft.claims[0].supports.append(
        Support(passage_id=other_hit.passage.passage_id, quote=other_hit.passage.text)
    )

    result = verify_answer(request_data).data

    assert result is not None
    assert not result.passed
    assert result.checks[0].quote_valid
    assert result.checks[0].verdict == "unsupported"


def test_one_unsupported_claim_fails_the_answer(request_data):
    unsupported = request_data.draft.claims[0].model_copy(deep=True)
    unsupported.claim_id = "claim_without_evidence"
    unsupported.supports[0].passage_id = "missing_passage"
    request_data.draft.claims.append(unsupported)

    result = verify_answer(request_data).data

    assert result is not None
    assert not result.passed
    assert [check.target_id for check in result.checks] == [
        "claim_mock_1",
        "claim_without_evidence",
    ]
    assert [check.verdict for check in result.checks] == ["supported", "unsupported"]


def test_empty_claims_do_not_pass_verification(request_data):
    request_data.draft.claims = []

    result = verify_answer(request_data).data

    assert result is not None
    assert not result.passed
    assert result.evidence_strength == "insufficient"
    assert result.checks == []


def test_inapplicable_citation_triggers_api_fallback(request_data):
    request_data.retrieval.hits[0].applicable = False
    settings = Settings(app_mode="mock")
    tools = replace(build_tools(settings), search=lambda _: success(request_data.retrieval))

    with TestClient(create_app(settings, tools)) as client:
        response = client.post("/v1/query", json=request_data.query.model_dump())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"]
    data = payload["data"]
    assert data["result"]["status"] == "insufficient_evidence"
    assert data["result"]["fallback_reason"] == "failed_verification"
    assert data["result"]["claims"] == []
    assert not data["verification"]["passed"]
    assert data["verification"]["checks"][0]["quote_valid"]
