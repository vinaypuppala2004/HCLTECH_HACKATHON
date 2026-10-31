"""A4 persists session outcomes and scopes without replaying HTTP requests."""

from copy import deepcopy
from pathlib import Path

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from evidencedesk.api.app import create_app
from evidencedesk.core.settings import Settings
from evidencedesk.mocks.fixtures import PASSAGE_TEXT

UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "app.py"
BACKEND_URL = "http://127.0.0.1:8000"


def click(ui, label):
    return next(button for button in ui.button if button.label == label).click().run()


def submit(ui, question="How do I reset my password?"):
    ui.chat_input[0].set_value(question).run()
    assert not ui.exception


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("BACKEND_URL", BACKEND_URL)
    calls = []
    with TestClient(create_app(Settings())) as client:

        def response(url, *, json, **kwargs):
            route = url.removeprefix(BACKEND_URL)
            calls.append((route, deepcopy(json)))
            return client.post(route, json=json)

        monkeypatch.setattr(httpx, "post", response)
        yield AppTest.from_file(UI_PATH, default_timeout=15), calls, client


def query_calls(calls):
    return [body for route, body in calls if route == "/v1/query"]


def test_multiple_turns_keep_order_citations_and_history_on_rerun(frontend):
    ui, calls, _ = frontend
    ui.run()
    questions = ["First question?", "Second question?", "Third question?"]
    for question in questions:
        submit(ui, question)
    saved = deepcopy(ui.session_state.messages)
    for _ in range(3):
        ui.run()
        assert not ui.exception
    assert len(query_calls(calls)) == 3
    assert ui.session_state.messages == saved
    assert [message["role"] for message in saved] == ["user", "assistant"] * 3
    assert [message["text"] for message in saved if message["role"] == "user"] == questions
    assert len([e for e in ui.expander if e.label == "Citations for claim claim_mock_1"]) == 3
    assert [
        m["result"]["retrieval"]["hits"][0]["passage"]["text"] for m in saved if "result" in m
    ] == [PASSAGE_TEXT] * 3


def test_submitted_context_is_snapshot_and_only_latest_question_is_sent(frontend):
    ui, calls, _ = frontend
    ui.run()
    for field, value in {
        "product": " Product A ",
        "version": " v1 ",
        "environment": " prod ",
    }.items():
        ui.text_input(key=f"scope_{field}").set_value(value).run()
    submit(ui, "Original scope question?")
    saved = deepcopy(ui.session_state.messages)
    for field, value in {"product": "Product B", "version": "v2", "environment": "test"}.items():
        ui.text_input(key=f"scope_{field}").set_value(value).run()
    assert ui.session_state.messages == saved
    assert len(query_calls(calls)) == 1
    assert any(
        c.value == "Submitted context — Product: Product A | Version: v1 | Environment: prod"
        for c in ui.caption
    )
    submit(ui, "New scope question?")
    assert query_calls(calls) == [
        {
            "question": "Original scope question?",
            "context": {"product": "Product A", "version": "v1", "environment": "prod"},
        },
        {
            "question": "New scope question?",
            "context": {"product": "Product B", "version": "v2", "environment": "test"},
        },
    ]
    assert ui.session_state.messages[:2] == saved


def test_deliberately_resubmitting_same_question_creates_one_new_turn(frontend):
    ui, calls, _ = frontend
    ui.run()
    submit(ui)
    ui.run()
    submit(ui)
    ui.run()
    assert len(query_calls(calls)) == 2
    assert len(ui.session_state.messages) == 4


@pytest.mark.parametrize("failure", ["offline", "timeout", "backend_error", "bad_input"])
def test_failures_keep_error_style_without_automatic_retry(frontend, monkeypatch, failure):
    ui, calls, _ = frontend
    attempts = []

    def failed_response(url, *, json, **kwargs):
        attempts.append(json)
        if failure == "offline":
            raise httpx.ConnectError("offline")
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(
            503,
            json={
                "ok": False,
                "request_id": "req_history_failure",
                "data": None,
                "error": {
                    "code": "MODEL_UNAVAILABLE",
                    "message": "Model offline.",
                    "retryable": True,
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", failed_response)
    ui.run()
    submit(ui, "   " if failure == "bad_input" else "Help?")
    assert len(ui.error) == 1
    error = ui.error[0].value
    saved = deepcopy(ui.session_state.messages)
    ui.run()
    ui.text_input(key="scope_version").set_value("v2").run()
    assert not ui.exception
    assert len(ui.error) == 1
    assert ui.error[0].value == error
    assert ui.session_state.messages == saved
    assert len(attempts) == (0 if failure == "bad_input" else 1)
    assert not calls


def test_new_submission_after_failure_does_not_retry_the_failed_turn(frontend, monkeypatch):
    ui, calls, client = frontend
    attempts = []

    def first_fails(url, *, json, **kwargs):
        attempts.append(json)
        if len(attempts) == 1:
            raise httpx.ConnectError("offline")
        return client.post("/v1/query", json=json)

    monkeypatch.setattr(httpx, "post", first_fails)
    ui.run()
    submit(ui, "Failed question?")
    submit(ui, "New question?")
    ui.run()
    assert len(attempts) == 2
    assert [attempt["question"] for attempt in attempts] == ["Failed question?", "New question?"]
    assert len(ui.error) == 1
    assert len(ui.session_state.messages) == 4
    assert PASSAGE_TEXT in [element.value for element in ui.markdown]
    assert not calls


def test_source_and_empty_upload_actions_do_not_resubmit_chat(frontend):
    ui, calls, _ = frontend
    ui.run()
    submit(ui)
    saved = deepcopy(ui.session_state.messages)
    click(ui, "Browse / refresh sources")
    click(ui, "Open source")
    click(ui, "Upload documents")
    ui.run()
    assert not ui.exception
    assert len(query_calls(calls)) == 1
    assert ui.session_state.messages == saved


def test_separate_sessions_have_separate_history(frontend):
    ui, calls, _ = frontend
    ui.run()
    submit(ui, "Session one?")
    other = AppTest.from_file(UI_PATH, default_timeout=15).run()
    assert not other.exception
    assert other.session_state.messages == []
    assert not other.chat_message
    submit(other, "Session two?")
    assert len(query_calls(calls)) == 2
    assert ui.session_state.messages[0]["text"] == "Session one?"
    assert other.session_state.messages[0]["text"] == "Session two?"


def test_interrupted_request_is_not_replayed_on_rerun(frontend, monkeypatch):
    ui, calls, _ = frontend
    attempts = []
    original_post = httpx.post

    def interrupted(url, *, json, **kwargs):
        attempts.append(json)
        st.rerun()

    monkeypatch.setattr(httpx, "post", interrupted)
    ui.run()
    submit(ui)
    assert len(attempts) == 1
    assert len(ui.session_state.messages) == 2
    assert any("REQUEST_INTERRUPTED" in warning.value for warning in ui.warning)
    ui.run()
    assert not ui.exception
    assert len(attempts) == 1
    assert not calls
    monkeypatch.setattr(httpx, "post", original_post)
    submit(ui)
    assert len(query_calls(calls)) == 1, "An explicit resubmission is a new request."
    assert len(ui.session_state.messages) == 4
    assert "result" in ui.session_state.messages[3]


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("needs_context", None),
        ("not_found", "no_support"),
        ("insufficient_evidence", "failed_verification"),
    ],
)
def test_saved_fallback_responses_are_not_refetched_or_reinterpreted(
    frontend, monkeypatch, status, reason
):
    ui, calls, _ = frontend
    original_post = httpx.post

    def fallback_response(url, *, json, **kwargs):
        response = original_post(url, json=json, **kwargs)
        body = response.json()
        body["data"]["result"].update(
            status=status,
            claims=[],
            fallback_reason=reason,
            clarification={
                "field": "version",
                "question": "Which version?",
                "options": ["v1", "v2"],
            }
            if status == "needs_context"
            else None,
        )
        body["data"]["verification"].update(passed=False, checks=[])
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fallback_response)
    ui.run()
    submit(ui)
    saved = deepcopy(ui.session_state.messages)
    ui.text_input(key="scope_version").set_value("v2").run()
    ui.run()
    assert not ui.exception
    assert len(query_calls(calls)) == 1
    assert ui.session_state.messages == saved
    assert ui.session_state.messages[1]["result"]["result"]["status"] == status
    assert any(caption.value == f"Answer status: {status}" for caption in ui.caption)
    if status == "needs_context":
        assert "Which version?" in [element.value for element in ui.markdown]


def test_response_is_saved_before_rendering_and_not_refetched_after_render_failure(
    frontend, monkeypatch
):
    ui, calls, _ = frontend
    ui.run()
    original_write = st.write

    def broken_render(value, *args, **kwargs):
        if value == PASSAGE_TEXT:
            raise RuntimeError("Synthetic render failure")
        return original_write(value, *args, **kwargs)

    monkeypatch.setattr(st, "write", broken_render)
    ui.chat_input[0].set_value("Question before render failure?").run()
    assert ui.exception
    assert len(query_calls(calls)) == 1
    assert "result" in ui.session_state.messages[1]
    monkeypatch.setattr(st, "write", original_write)
    ui.run()
    assert not ui.exception
    assert len(query_calls(calls)) == 1
    assert len(ui.session_state.messages) == 2
    assert PASSAGE_TEXT in [element.value for element in ui.markdown]


def test_legacy_history_is_displayed_without_requests(frontend):
    ui, calls, client = frontend
    result = client.post(
        "/v1/query",
        json={
            "question": "Older question?",
            "context": {"product": None, "version": None, "environment": None},
        },
    ).json()["data"]
    legacy = [
        {"role": "user", "text": "Older question?"},
        {"role": "assistant", "result": result},
        {"role": "user", "text": "Older failed question?"},
        {"role": "assistant", "text": "MODEL_UNAVAILABLE: Previously recorded failure."},
    ]
    ui.session_state.messages = deepcopy(legacy)
    ui.run()
    assert not ui.exception
    assert ui.session_state.messages == legacy
    assert not calls
    assert len(ui.chat_message) == 4
    assert "Previously recorded failure" in ui.error[0].value
