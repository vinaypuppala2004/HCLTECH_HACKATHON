"""One smoke test covers the tool pipeline and a submitted Streamlit message."""

from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from evidencedesk.contracts.models import Envelope, QueryResult
from evidencedesk.core.settings import Settings
from evidencedesk.mocks.fixtures import DEMO_QUESTION, PASSAGE_TEXT


def test_mock_chat_smoke(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("BACKEND_URL", "http://127.0.0.1:8000")
    from evidencedesk.api.app import create_app

    with TestClient(create_app(Settings())) as client:
        assert client.get("/v1/health").json()["data"]["mode"] == "mock"
        payload = {
            "question": DEMO_QUESTION,
            "context": {"product": None, "version": None, "environment": None},
        }
        response = client.post("/v1/query", json=payload)
        assert response.status_code == 200
        result = Envelope[QueryResult].model_validate(response.json()).data
        assert result is not None
        assert result.result.claims[0].text == PASSAGE_TEXT
        assert result.result.claims[0].supports[0].quote in result.retrieval.hits[0].passage.text
        assert result.verification.passed
        assert [step.step for step in result.trace] == ["retrieve", "draft", "verify"]

        sources = client.post("/v1/sources:read", json={"document_id": "doc_mock_guide"})
        assert sources.json()["data"]["passages"][0]["text"] == PASSAGE_TEXT
        invalid = client.post("/v1/query", json={**payload, "question": "   "})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "BAD_INPUT"

        sent = []

        def route_to_backend(url, *, json, **kwargs):
            assert url == "http://127.0.0.1:8000/v1/query"
            sent.append(json)
            return client.post("/v1/query", json=json)

        monkeypatch.setattr(httpx, "post", route_to_backend)
        ui_path = Path(__file__).resolve().parents[2] / "ui" / "app.py"
        ui = AppTest.from_file(ui_path, default_timeout=15).run()
        assert not ui.exception
        ui.chat_input[0].set_value(DEMO_QUESTION).run()
        assert not ui.exception
        assert len(sent) == 1
        assert sent[0]["question"] == DEMO_QUESTION
        assert PASSAGE_TEXT in [element.value for element in ui.markdown]
        ui.run()
        assert len(sent) == 1, "A Streamlit rerun must not repeat the request."
