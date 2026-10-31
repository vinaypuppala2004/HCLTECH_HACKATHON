"""A3 query failures retain useful envelope details and never return mock data."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from evidencedesk.api.app import create_app
from evidencedesk.contracts.models import QueryInput, Scope
from evidencedesk.core.settings import Settings
from ui.query_client import QueryServiceError, request_query

UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "app.py"
BACKEND_URL = "http://127.0.0.1:8000"
QUERY = QueryInput(
    question="How do I get help?", context=Scope(product=None, version=None, environment=None)
)


@pytest.fixture
def mock_post(monkeypatch):
    calls = []

    def install(*, status=503, body=None, text=None, error=None):
        def response(url, *, json, **kwargs):
            calls.append((url, json))
            if error is not None:
                raise error
            return httpx.Response(
                status,
                json=body,
                text=text,
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", response)

    return install, calls


def failure(code, *, retryable=True):
    return {
        "ok": False,
        "request_id": "req_a3_failure",
        "data": None,
        "error": {"code": code, "message": "Synthetic backend failure.", "retryable": retryable},
    }


@pytest.mark.parametrize(
    ("code", "status", "guidance"),
    [
        ("BAD_INPUT", 422, "Check your question and context"),
        ("UNSUPPORTED_FORMAT", 422, "supported PDF, HTML, Markdown, or TXT"),
        ("EMPTY_DOCUMENT", 422, "readable text"),
        ("NOT_FOUND", 404, "Refresh the sources"),
        ("INDEX_EMPTY", 409, "No documents are indexed"),
        ("BUSY", 409, "Wait briefly"),
        ("EMBEDDING_UNAVAILABLE", 503, "configured embedding model"),
        ("MODEL_UNAVAILABLE", 503, "configured generation model"),
        ("MODEL_TIMEOUT", 504, "model took too long"),
        ("INVALID_MODEL_OUTPUT", 502, "model returned an invalid answer"),
        ("NOT_IMPLEMENTED", 501, "not implemented in the current backend"),
        ("INTERNAL_ERROR", 500, "Check its logs using the request ID"),
    ],
)
def test_api_error_codes_keep_message_request_id_retryability_and_guidance(
    mock_post, code, status, guidance
):
    install, calls = mock_post
    install(status=status, body=failure(code))
    with pytest.raises(QueryServiceError) as caught:
        request_query(BACKEND_URL, QUERY)
    message = str(caught.value)
    assert f"{code}: Synthetic backend failure." in message
    assert "Request ID: req_a3_failure | Retryable: yes" in message
    assert guidance in message
    assert len(calls) == 1, "Failures must not trigger retries or hidden mock requests."


def test_unsuccessful_http_200_envelope_is_not_treated_as_an_answer(mock_post):
    install, _ = mock_post
    install(status=200, body=failure("BAD_INPUT", retryable=False))
    with pytest.raises(QueryServiceError, match="Retryable: no"):
        request_query(BACKEND_URL, QUERY)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ReadTimeout("private timeout details"), "REQUEST_TIMEOUT"),
        (httpx.ConnectError("private connection details"), "BACKEND_UNREACHABLE"),
        (httpx.ReadError("private transport details"), "CONNECTION_ERROR"),
        (httpx.InvalidURL("private URL details"), "BACKEND_UNREACHABLE"),
    ],
)
def test_transport_errors_are_clear_without_exposing_raw_details(mock_post, error, expected):
    install, calls = mock_post
    install(error=error)
    with pytest.raises(QueryServiceError) as caught:
        request_query(BACKEND_URL, QUERY)
    assert expected in str(caught.value)
    assert "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [200, 502])
@pytest.mark.parametrize("body", [None, {"ok": True, "unexpected": "PRIVATE_RESPONSE_BODY"}])
def test_unreadable_or_malformed_response_does_not_leak_body(mock_post, status, body):
    install, _ = mock_post
    install(status=status, body=body, text="PRIVATE_RESPONSE_BODY" if body is None else None)
    with pytest.raises(QueryServiceError) as caught:
        request_query(BACKEND_URL, QUERY)
    message = str(caught.value)
    assert "INVALID_RESPONSE" in message
    assert "PRIVATE_RESPONSE_BODY" not in message
    if status != 200:
        assert "HTTP 502" in message


@pytest.mark.parametrize(
    "body",
    [
        {"ok": True, "request_id": "req_empty", "data": None, "error": None},
        {"ok": False, "request_id": "req_empty", "data": None, "error": None},
        {**failure("INTERNAL_ERROR"), "ok": True},
    ],
)
def test_inconsistent_envelopes_fail_explicitly(mock_post, body):
    install, _ = mock_post
    install(status=200, body=body)
    with pytest.raises(QueryServiceError, match="INVALID_RESPONSE"):
        request_query(BACKEND_URL, QUERY)


def test_failed_http_status_cannot_return_success_data(mock_post):
    from fastapi.testclient import TestClient

    with TestClient(create_app(Settings())) as client:
        body = client.post("/v1/query", json=QUERY.model_dump()).json()
    install, _ = mock_post
    install(status=503, body=body)
    with pytest.raises(QueryServiceError, match="HTTP 503"):
        request_query(BACKEND_URL, QUERY)


@pytest.mark.parametrize(
    "scenario", ["model_unavailable", "timeout", "offline", "invalid_response"]
)
def test_service_error_is_visible_in_chat_with_no_factual_reply(mock_post, monkeypatch, scenario):
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("BACKEND_URL", BACKEND_URL)
    install, calls = mock_post
    if scenario == "model_unavailable":
        install(body=failure("MODEL_UNAVAILABLE"))
        expected = "MODEL_UNAVAILABLE"
    elif scenario == "timeout":
        install(error=httpx.ReadTimeout("private error"))
        expected = "REQUEST_TIMEOUT"
    elif scenario == "offline":
        install(error=httpx.ConnectError("private error"))
        expected = "BACKEND_UNREACHABLE"
    else:
        install(status=200, text="PRIVATE_RESPONSE_BODY")
        expected = "INVALID_RESPONSE"
    ui = AppTest.from_file(UI_PATH, default_timeout=15).run()
    ui.chat_input[0].set_value(QUERY.question).run()
    assert not ui.exception
    assert len(ui.error) == 1
    assert expected in ui.error[0].value
    if scenario == "model_unavailable":
        assert "req_a3_failure" in ui.error[0].value
        assert "Retryable: yes" in ui.error[0].value
    assert not any(element.label.startswith("Citations for claim") for element in ui.expander)
    assert not any("MOCK MODE" in warning.value for warning in ui.warning)
    assert "private" not in ui.error[0].value
    assert "PRIVATE_RESPONSE_BODY" not in ui.error[0].value
    assert len(calls) == 1


def test_blank_question_has_readable_validation_error_without_api_call(mock_post, monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    install, calls = mock_post
    install()
    ui = AppTest.from_file(UI_PATH, default_timeout=15).run()
    ui.chat_input[0].set_value("   ").run()
    assert not ui.exception
    assert "BAD_INPUT: Enter a question" in ui.error[0].value
    assert not calls
