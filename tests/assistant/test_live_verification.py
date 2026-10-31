"""Conflict structure and semantic judgments must pass before exposing facts."""

import json

import pytest

from evidencedesk.assistant.verification import GroundedVerifier
from evidencedesk.contracts.models import (
    Conflict,
    Draft,
    GenerationOutput,
    QueryInput,
    Scope,
    SearchResult,
    Support,
    VerifyInput,
)
from evidencedesk.core.responses import success
from evidencedesk.mocks.fixtures import mock_hit


def evidence():
    left, right = mock_hit(), mock_hit()
    for hit, identifier, text in [
        (left, "left", "Audit logs are retained for 30 days."),
        (right, "right", "Audit logs are retained for 90 days."),
    ]:
        hit.document.document_id = identifier
        hit.document.metadata.product = "Demo"
        hit.document.metadata.version = "v1"
        hit.document.metadata.environment = "production"
        hit.document.metadata.family_id = "retention"
        hit.passage.document_id = identifier
        hit.passage.passage_id = identifier
        hit.passage.text = text
    return left, right


def request(hits):
    return VerifyInput(
        query=QueryInput(
            question="How long are audit logs retained?",
            context=Scope(
                product="Demo",
                version="v1",
                environment="production",
            ),
        ),
        retrieval=SearchResult(index_revision=1, hits=list(hits), warnings=[]),
        draft=Draft(
            status="conflict",
            claims=[],
            conflicts=[
                Conflict(
                    conflict_id="retention",
                    kind="contradiction",
                    topic="Audit log retention",
                    sides=[
                        Support(passage_id=h.passage.passage_id, quote=h.passage.text) for h in hits
                    ],
                    resolution="unresolved",
                    selected_passage_ids=[],
                )
            ],
            clarification=None,
            fallback_reason=None,
        ),
    )


def judge(verdict="supported"):
    def generate(payload):
        targets = json.loads(payload.messages[-1].content)["targets"]
        return success(
            GenerationOutput(
                model="qwen3:4b",
                model_digest="synthetic",
                prompt_tokens=10,
                completion_tokens=10,
                duration_ms=1,
                content={
                    "checks": [
                        {
                            "target_type": t["target_type"],
                            "target_id": t["target_id"],
                            "quote_valid": True,
                            "verdict": verdict,
                            "reason": "Synthetic judgment.",
                        }
                        for t in targets
                    ]
                },
            )
        )

    return generate


@pytest.mark.parametrize("verdict", ["supported", "unsupported", "unclear"])
def test_conflicts_require_semantic_support(verdict):
    result = GroundedVerifier(judge(verdict))(request(evidence())).data
    assert result.passed == (verdict == "supported")
    assert result.checks[0].quote_valid


@pytest.mark.parametrize("fault", ["quote", "context", "false_resolution", "same_passage"])
def test_invalid_conflicts_fail_before_model_call(fault):
    payload = request(evidence())
    conflict = payload.draft.conflicts[0]
    if fault == "quote":
        conflict.sides[0].quote = "Invented quote."
    elif fault == "context":
        payload.retrieval.hits[1].document.metadata.product = "Different"
    elif fault == "false_resolution":
        conflict.resolution = "resolved_by_context"
        conflict.selected_passage_ids = ["left"]
    else:
        conflict.sides[1] = conflict.sides[0]

    def forbidden(_):
        pytest.fail("Structurally invalid conflicts must not call the model.")

    assert not GroundedVerifier(forbidden)(payload).data.passed


def test_version_comparison_keeps_nonapplicable_evidence_without_supporting_claims():
    payload = request(evidence())
    payload.retrieval.hits[1].document.metadata.version = "v2"
    payload.retrieval.hits[1].applicable = False
    conflict = payload.draft.conflicts[0]
    conflict.kind = "version_difference"
    conflict.resolution = "resolved_by_context"
    conflict.selected_passage_ids = ["left"]
    assert GroundedVerifier(judge())(payload).data.passed
