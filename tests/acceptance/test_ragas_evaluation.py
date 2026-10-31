"""Evaluation must preserve observed failures, split integrity, and local providers."""

import json

import httpx
import pytest
from pydantic import BaseModel

from evaluation.reporting import aggregate, custom_metrics
from evaluation.run import POLICY, load_labels, save


def test_current_utf8_snapshot_matches_the_original_freeze():
    cases, provenance, warnings = load_labels()
    assert len(cases) == 25 and len(provenance["sources"]) == 16
    assert sum(c["split"] == "heldout" for c in cases) == 8
    assert warnings == []


def test_abstentions_and_judge_errors_are_not_perfect_scores_or_silently_dropped():
    metrics = {n: {"value": None, "status": "not_applicable"} for n in POLICY["metrics"]}
    metrics["context_recall"] = {"value": None, "status": "metric_error"}
    result = aggregate(
        [
            {
                "draft_status": "not_found",
                "response": "",
                "latency_ms": 100,
                "ragas": metrics,
                "checks": {
                    "source_recall_at_5": 0.0,
                    "exact_evidence_recall_at_5": None,
                    "citation_count": 0,
                    "valid_citation_count": 0,
                },
            }
        ]
    )
    assert result["answer_coverage"] == 0
    assert result["cases"] == 1 and result["ragas"]["faithfulness"]["mean"] is None
    assert result["ragas"]["context_recall"]["statuses"] == {"metric_error": 1}
    assert result["checks"]["citation_integrity"]["value"] is None


def test_reference_mapping_uses_source_hash_and_exact_evidence_not_gold_ids():
    case = {"evidence": [{"source_sha256": "source", "page": None, "quote": "Exact quote."}]}
    document = {"sha256": "source"}
    passage = {"passage_id": "actual", "page": None, "text": "Intro. Exact quote. More."}
    hit = {"document": document, "passage": passage, "applicable": True}
    observed = {"retrieval": {"hits": [hit]}, "raw_api_response": {"ok": False}}
    metrics = custom_metrics(case, observed, [(document, passage)])
    assert metrics["reference_mapping"] == [["actual"]]
    assert metrics["exact_evidence_recall_at_5"] == 1
    passage["text"] = "Different passage."
    assert (
        custom_metrics(case, observed, [(document, passage)])["exact_evidence_recall_at_5"] is None
    )


def test_json_outputs_are_atomic_and_reject_fake_nan(tmp_path):
    output = tmp_path / "nested" / "row.json"
    save(output, {"score": None})
    assert json.loads(output.read_text()) == {"score": None}
    with pytest.raises(ValueError):
        save(output, {"score": float("nan")})
    assert json.loads(output.read_text()) == {"score": None}


def test_local_judge_caches_valid_structured_json_without_cloud_fallback(tmp_path):
    pytest.importorskip("ragas")
    from evaluation.providers import LocalJudge, local_client

    class Output(BaseModel):
        value: int

    calls = []

    def serve(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "done": True,
                "done_reason": "stop",
                "message": {"content": '{"value":1}'},
            },
        )

    with httpx.Client(
        base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(serve)
    ) as client:
        judge = LocalJudge(client, tmp_path, "fixture-digest")
        assert judge.generate("Synthetic scoring input.", Output).value == 1
        assert judge.generate("Synthetic scoring input.", Output).value == 1
    assert len(calls) == 1 and calls[0]["model"] == "qwen3:4b"
    assert calls[0]["think"] is False
    with pytest.raises(ValueError, match="loopback"):
        local_client("https://example.com")
