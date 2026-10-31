"""Prompt aliases must become real citations; explicit version scope resolves comparisons."""

import json

from evidencedesk.assistant.drafting import GroundedDraftAnswer
from evidencedesk.contracts.models import (
    DraftInput,
    GenerationOutput,
    QueryInput,
    Scope,
    SearchResult,
)
from evidencedesk.core.responses import success
from evidencedesk.mocks.fixtures import mock_hit


def test_aliases_map_to_real_ids_and_version_resolution_uses_explicit_scope():
    left, right = mock_hit(), mock_hit()
    for number, hit in enumerate((left, right), 1):
        hit.document.document_id = f"real-document-{number}"
        hit.document.metadata.family_id = "reset"
        hit.document.metadata.version = f"v{number}"
        hit.passage.document_id = hit.document.document_id
        hit.passage.passage_id = f"real-passage-{number}"
        hit.passage.text = f"The reset link lasts {number * 15} minutes."
        hit.rank = number
        hit.applicable = number == 1
    request = DraftInput(
        query=QueryInput(
            question="How long does the link last?",
            context=Scope(
                product=None,
                version="v1",
                environment=None,
            ),
        ),
        retrieval=SearchResult(index_revision=1, hits=[left, right], warnings=[]),
    )

    def generate(payload):
        data = json.loads(payload.messages[-1].content)
        assert [s["passage_id"] for s in data["sources"]] == ["source_1", "source_2"]
        return success(
            GenerationOutput(
                model="qwen3:4b",
                model_digest="synthetic",
                prompt_tokens=10,
                completion_tokens=10,
                duration_ms=1,
                content={
                    "status": "answered",
                    "claims": [
                        {
                            "claim_id": "duration",
                            "text": left.passage.text,
                            "supports": [{"passage_id": "source_1", "quote": left.passage.text}],
                        }
                    ],
                    "conflicts": [
                        {
                            "conflict_id": "versions",
                            "kind": "version_difference",
                            "topic": "Link duration",
                            "sides": [
                                {"passage_id": f"source_{i}", "quote": h.passage.text}
                                for i, h in enumerate((left, right), 1)
                            ],
                            "resolution": "unresolved",
                            "selected_passage_ids": [],
                        }
                    ],
                    "clarification": None,
                    "fallback_reason": None,
                },
            )
        )

    result = GroundedDraftAnswer(generate)(request).data
    assert result.status == "answered"
    assert result.claims[0].supports[0].passage_id == "real-passage-1"
    assert result.conflicts[0].resolution == "resolved_by_context"
    assert result.conflicts[0].selected_passage_ids == ["real-passage-1"]


def test_model_cannot_invent_a_required_version_when_sources_have_no_versions():
    hit = mock_hit()
    hit.document.metadata.version = None
    request = DraftInput(
        query=QueryInput(
            question="Where is the account portal?",
            context=Scope(
                product=None,
                version=None,
                environment=None,
            ),
        ),
        retrieval=SearchResult(index_revision=1, hits=[hit], warnings=[]),
    )

    def generate(_):
        return success(
            GenerationOutput(
                model="qwen3:4b",
                model_digest="synthetic",
                prompt_tokens=10,
                completion_tokens=10,
                duration_ms=1,
                content={
                    "status": "needs_context",
                    "claims": [],
                    "conflicts": [],
                    "clarification": {
                        "field": "version",
                        "question": "Which version?",
                        "options": [],
                    },
                    "fallback_reason": None,
                },
            )
        )

    result = GroundedDraftAnswer(generate)(request).data
    assert result.status == "insufficient_evidence"
    assert result.clarification is None and not result.claims
