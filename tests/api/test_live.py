"""Live wiring with real persistent Qdrant and explicitly synthetic Ollama HTTP replies."""

import base64
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from evidencedesk.api.app import create_app
from evidencedesk.core import factory
from evidencedesk.core.settings import Settings

QUERY = {
    "question": "How do I reset my password?",
    "context": {
        "product": "Demo",
        "version": "v1",
        "environment": "production",
    },
}


def upload(filename="guide.txt", text="Reset your password in the account portal.", version="v1"):
    return {
        "filename": filename,
        "content_base64": base64.b64encode(text.encode()).decode(),
        "metadata": {
            "title": "Guide",
            "source_url": None,
            "product": "Demo",
            "version": version,
            "environment": "production",
            "family_id": "guide",
            "published_at": None,
            "origin": "synthetic",
        },
    }


class SyntheticOllama:
    def __init__(self):
        self.online = True
        self.bad_claim = False
        self.bad_quote = False
        self.bad_verification = False
        self.reject_long_inputs = False

    def __call__(self, request):
        if not self.online:
            raise httpx.ConnectError("Synthetic service outage", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": name, "digest": name + "-fixture"}
                        for name in ("qwen3:4b", "nomic-embed-text:v1.5")
                    ]
                },
            )
        body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": ["embedding"],
                    "model_info": {
                        "general.architecture": "nomic-bert",
                        "nomic-bert.embedding_length": 768,
                    },
                },
            )
        if request.url.path == "/api/embed":
            if self.reject_long_inputs and any(len(text) > 1850 for text in body["input"]):
                return httpx.Response(400, json={"error": "Synthetic context overflow"})
            return httpx.Response(
                200,
                json={
                    "model": body["model"],
                    "embeddings": [[1.0, 0.0] + [0.0] * 766 for _ in body["input"]],
                },
            )
        assert request.url.path == "/api/chat"
        data = json.loads(body["messages"][-1]["content"])
        if "targets" in data:
            content = {
                "checks": [
                    {
                        "target_type": t["target_type"],
                        "target_id": t["target_id"],
                        "quote_valid": True,
                        "verdict": "unsupported" if self.bad_claim else "supported",
                        "reason": "Synthetic semantic judgment.",
                    }
                    for t in data["targets"]
                ]
            }
            if self.bad_verification:
                content["checks"][0]["target_id"] = "invented"
        else:
            source = next(s for s in data["sources"] if s["applicable"])
            claim = "Invented factual instruction." if self.bad_claim else source["text"]
            content = {
                "status": "answered",
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "text": claim,
                        "supports": [
                            {
                                "passage_id": source["passage_id"],
                                "quote": "invented excerpt" if self.bad_quote else source["text"],
                            }
                        ],
                    }
                ],
                "conflicts": [],
                "clarification": None,
                "fallback_reason": None,
            }
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": json.dumps(content)},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "eval_count": 50,
                "total_duration": 1000000,
            },
        )


@pytest.fixture
def live(tmp_path, monkeypatch):
    model = SyntheticOllama()
    original = httpx.Client
    clients = []

    def make_client(**kwargs):
        client = original(transport=httpx.MockTransport(model), **kwargs)
        clients.append(client)
        return client

    settings = Settings(app_mode="live", qdrant_path=str(tmp_path / "index"))

    def build():
        with monkeypatch.context() as patch:
            patch.setattr(factory.httpx, "Client", make_client)
            return factory.build_tools(settings)

    return settings, model, clients, build


def test_ingest_query_deduplicate_read_and_restart(live):
    settings, _, clients, build = live
    tools = build()
    with TestClient(create_app(settings, tools)) as client:
        assert client.get("/v1/health").json()["data"]["document_count"] == 0
        assert client.post("/v1/search", json=QUERY).json()["error"]["code"] == "INDEX_EMPTY"
        result = client.post("/v1/documents:ingest", json={"documents": [upload()]}).json()["data"]
        assert result["results"][0]["state"] == "ready" and result["index_revision"] == 1
        renamed = upload(filename="renamed.txt")
        duplicate = client.post("/v1/documents:ingest", json={"documents": [renamed]}).json()[
            "data"
        ]
        assert duplicate["results"][0]["state"] == "duplicate"
        assert duplicate["index_revision"] == 1
        answer = client.post("/v1/query", json=QUERY).json()["data"]
        assert answer["mode"] == "live" and answer["result"]["status"] == "answered"
        assert answer["verification"]["passed"]
        assert answer["retrieval"]["hits"][0]["bm25_score"] > 0
        identifier = result["results"][0]["document_id"]
        sources = client.post("/v1/sources:read", json={"document_id": identifier}).json()["data"]
        assert sources["passages"][0]["text"] == upload_text()
    assert clients[0].is_closed
    with TestClient(create_app(settings, build())) as restarted:
        assert restarted.get("/v1/health").json()["data"]["document_count"] == 1
        assert (
            restarted.post("/v1/query", json=QUERY).json()["data"]["result"]["status"] == "answered"
        )
    assert clients[1].is_closed


def upload_text():
    return "Reset your password in the account portal."


def test_per_file_errors_never_become_indexed(live):
    settings, _, _, build = live
    with TestClient(create_app(settings, build())) as client:
        broken = upload("broken.txt")
        broken["content_base64"] = "bad base64!"
        results = client.post(
            "/v1/documents:ingest",
            json={
                "documents": [broken, upload("empty.txt", ""), upload()],
            },
        ).json()["data"]["results"]
        assert [r["state"] for r in results] == ["rejected", "rejected", "ready"]
        assert [r["error"]["code"] for r in results[:2]] == ["BAD_INPUT", "EMPTY_DOCUMENT"]
        assert client.get("/v1/health").json()["data"]["document_count"] == 1


@pytest.mark.parametrize("fault", ["bad_claim", "bad_quote", "bad_verification"])
def test_invalid_answers_are_withheld(live, fault):
    settings, model, _, build = live
    setattr(model, fault, True)
    with TestClient(create_app(settings, build())) as client:
        client.post("/v1/documents:ingest", json={"documents": [upload()]})
        result = client.post("/v1/query", json=QUERY).json()["data"]["result"]
        assert result["status"] == "insufficient_evidence" and not result["claims"]


def test_scope_version_counterparts_and_clarification(live):
    settings, _, _, build = live
    with TestClient(create_app(settings, build())) as client:
        client.post(
            "/v1/documents:ingest",
            json={
                "documents": [
                    upload(),
                    upload("v2.txt", "Reset your password through the recovery page.", "v2"),
                ]
            },
        )
        result = client.post("/v1/search", json=QUERY).json()["data"]
        assert any(h["applicable"] for h in result["hits"])
        assert any(
            h["selection"] == "version_counterpart" and not h["applicable"] for h in result["hits"]
        )
        unscoped = {**QUERY, "context": {**QUERY["context"], "version": None}}
        result = client.post("/v1/query", json=unscoped).json()["data"]["result"]
        assert result["status"] == "needs_context" and not result["claims"]
        absent = {**QUERY, "context": {**QUERY["context"], "product": "Other"}}
        assert (
            client.post("/v1/query", json=absent).json()["data"]["result"]["status"] == "not_found"
        )


def test_service_loss_updates_readiness_without_mock_fallback(live):
    settings, model, _, build = live
    with TestClient(create_app(settings, build())) as client:
        client.post("/v1/documents:ingest", json={"documents": [upload()]})
        model.online = False
        health = client.get("/v1/health").json()["data"]
        assert not health["ready"] and not health["ollama_available"]
        assert health["document_count"] == 1
        result = client.post("/v1/query", json=QUERY)
        assert (
            result.status_code == 503 and result.json()["error"]["code"] == "EMBEDDING_UNAVAILABLE"
        )
        model.online = True
        assert client.get("/v1/health").json()["data"]["ready"]


def test_live_configuration_rejects_other_models(tmp_path):
    with pytest.raises(RuntimeError, match="requires"):
        factory.build_tools(replace(Settings(app_mode="live"), generation_model="other"))


def test_token_dense_file_is_rechunked_without_truncation(live):
    settings, model, _, build = live
    model.reject_long_inputs = True
    text = "Password reset instructions. " * 180
    with TestClient(create_app(settings, build())) as client:
        response = client.post("/v1/documents:ingest", json={"documents": [upload(text=text)]})
        item = response.json()["data"]["results"][0]
        assert item["state"] == "ready" and item["passage_count"] > 2
        source = client.post("/v1/sources:read", json={"document_id": item["document_id"]}).json()[
            "data"
        ]
        assert all(len(p["text"]) <= 1800 for p in source["passages"])
        assert source["passages"][0]["text"].startswith("Password reset")
        assert source["passages"][-1]["text"].endswith("instructions. ")
