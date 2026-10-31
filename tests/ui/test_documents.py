"""A1 controls use the frozen API without claiming mock uploads were indexed."""

from base64 import b64decode
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from evidencedesk.api.app import create_app
from evidencedesk.contracts.models import IngestResult
from evidencedesk.core.settings import Settings
from evidencedesk.mocks.fixtures import PASSAGE_TEXT, mock_hit
from ui.documents import build_upload_request, post_document_request

UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "app.py"
BACKEND_URL = "http://127.0.0.1:8000"


def uploaded_file(name="sample.txt", content=b"Sample text", size=None):
    return SimpleNamespace(
        name=name, size=len(content) if size is None else size, getvalue=lambda: content
    )


def click(ui, label):
    return next(button for button in ui.button if button.label == label).click().run()


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("BACKEND_URL", BACKEND_URL)
    calls = []
    with TestClient(create_app(Settings())) as client:

        def route_to_backend(url, *, json, **kwargs):
            route = url.removeprefix(BACKEND_URL)
            calls.append((route, json))
            return client.post(route, json=json)

        monkeypatch.setattr(httpx, "post", route_to_backend)
        yield AppTest.from_file(UI_PATH, default_timeout=15), calls


def test_upload_body_has_base64_and_all_metadata_keys():
    raw = b"\x00\xffPDF and non-ASCII bytes"
    request = build_upload_request([uploaded_file("guide.PDF", raw)])
    document = request.model_dump()["documents"][0]
    assert document["filename"] == "guide.PDF"
    assert b64decode(document["content_base64"]) == raw
    assert document["metadata"] == {
        "title": "guide.PDF",
        "source_url": None,
        "product": None,
        "version": None,
        "environment": None,
        "family_id": None,
        "published_at": None,
        "origin": "user",
    }


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "between 1 and 20"),
        ([uploaded_file()] * 21, "between 1 and 20"),
        ([uploaded_file(size=10 * 1024 * 1024 + 1)], "at most 10 MB"),
        ([uploaded_file(size=10 * 1024 * 1024)] * 6, "at most 50 MB"),
        ([uploaded_file("script.exe")], "Unsupported file format"),
    ],
)
def test_invalid_uploads_are_rejected_before_request(files, message):
    with pytest.raises(ValueError, match=message):
        build_upload_request(files)


def test_sources_list_and_passages_use_api_and_do_not_repeat_on_rerun(frontend):
    ui, calls = frontend
    ui.run()
    assert not ui.exception
    assert not calls
    click(ui, "Browse / refresh sources")
    assert not ui.exception
    assert calls == [("/v1/sources:read", {"document_id": None})]
    assert any("doc_mock_guide" in caption.value for caption in ui.caption)
    assert any("synthetic" in caption.value for caption in ui.caption)
    assert any("Synthetic fixture" in warning.value for warning in ui.warning)
    assert "Mock Support Guide" in [element.value for element in ui.text]
    click(ui, "Open source")
    assert not ui.exception
    assert calls[-1] == ("/v1/sources:read", {"document_id": "doc_mock_guide"})
    assert PASSAGE_TEXT in [element.value for element in ui.text]
    assert any("passage_mock_reset" in caption.value for caption in ui.caption)
    assert any("Account access / Password reset" in caption.value for caption in ui.caption)
    assert not any(caption.value.startswith("Page:") for caption in ui.caption)
    ui.run()
    assert len(calls) == 2
    click(ui, "Browse / refresh sources")
    assert PASSAGE_TEXT not in [element.value for element in ui.text]


def test_upload_mock_rejection_is_visible_and_is_not_repeated(frontend, monkeypatch):
    ui, calls = frontend
    files = [uploaded_file(), uploaded_file("guide.md", b"# Guide")]
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: files)
    ui.run()
    click(ui, "Upload documents")
    assert not ui.exception
    assert len(calls) == 1
    assert calls[0][0] == "/v1/documents:ingest"
    assert len(calls[0][1]["documents"]) == 2
    assert len(ui.error) == 2
    assert all("NOT_IMPLEMENTED" in error.value for error in ui.error)
    assert all("rejected; not indexed" in error.value for error in ui.error)
    assert not ui.success
    ui.run()
    assert len(calls) == 1
    assert len(ui.error) == 2


def test_empty_upload_selection_does_not_call_api(frontend):
    ui, calls = frontend
    ui.run()
    click(ui, "Upload documents")
    assert not ui.exception
    assert not calls
    assert "between 1 and 20 files" in ui.error[0].value


def test_empty_source_list_is_explicit(frontend, monkeypatch):
    ui, _ = frontend
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_empty",
                "data": {"documents": [], "passages": []},
                "error": None,
            },
            request=httpx.Request("POST", BACKEND_URL),
        ),
    )
    ui.run()
    click(ui, "Browse / refresh sources")
    assert not ui.exception
    assert any("No documents are available" in info.value for info in ui.info)
    assert not ui.selectbox


@pytest.mark.parametrize("state", ["ready", "duplicate"])
def test_upload_success_and_duplicate_results(frontend, monkeypatch, state):
    ui, _ = frontend
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: [uploaded_file()])
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_ingest",
                "data": {
                    "index_revision": 2,
                    "results": [
                        {
                            "filename": "sample.txt",
                            "state": state,
                            "document_id": "doc_uploaded",
                            "passage_count": 3,
                            "error": None,
                        }
                    ],
                },
                "error": None,
            },
            request=httpx.Request("POST", BACKEND_URL),
        ),
    )
    ui.run()
    click(ui, "Upload documents")
    assert not ui.exception
    assert not ui.error
    messages = ui.success if state == "ready" else ui.info
    assert any(f"sample.txt: {state}" in message.value for message in messages)
    assert any("doc_uploaded | Passages: 3" in caption.value for caption in ui.caption)


def test_selected_source_loads_its_own_passages_with_pdf_page(frontend, monkeypatch):
    ui, _ = frontend
    hit = mock_hit()
    second_document = hit.document.model_copy(
        update={"document_id": "doc_pdf", "filename": "guide.pdf", "format": "pdf"}
    )
    second_passage = hit.passage.model_copy(
        update={
            "document_id": "doc_pdf",
            "passage_id": "pdf_page_3",
            "page": 3,
            "text": "A different document's exact text.",
        }
    )
    selected_ids = []

    def sources_response(url, *, json, **kwargs):
        selected_ids.append(json["document_id"])
        return httpx.Response(
            200,
            json={
                "ok": True,
                "request_id": "req_sources",
                "data": {
                    "documents": [hit.document.model_dump(), second_document.model_dump()],
                    "passages": [second_passage.model_dump()] if json["document_id"] else [],
                },
                "error": None,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", sources_response)
    ui.run()
    click(ui, "Browse / refresh sources")
    ui.selectbox[0].select("doc_pdf").run()
    click(ui, "Open source")
    assert not ui.exception
    assert selected_ids == [None, "doc_pdf"]
    assert second_passage.text in [element.value for element in ui.text]
    assert any(caption.value == "Page: 3" for caption in ui.caption)
    ui.selectbox[0].select(hit.document.document_id).run()
    assert second_passage.text not in [element.value for element in ui.text]


def test_missing_source_clears_previous_passages(frontend, monkeypatch):
    ui, _ = frontend
    ui.run()
    click(ui, "Browse / refresh sources")
    click(ui, "Open source")
    assert PASSAGE_TEXT in [element.value for element in ui.text]
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            404,
            json={
                "ok": False,
                "request_id": "req_missing",
                "data": None,
                "error": {"code": "NOT_FOUND", "message": "Source removed.", "retryable": False},
            },
            request=httpx.Request("POST", BACKEND_URL),
        ),
    )
    click(ui, "Open source")
    assert not ui.exception
    assert "NOT_FOUND: Source removed." in ui.error[0].value
    assert PASSAGE_TEXT not in [element.value for element in ui.text]


@pytest.mark.parametrize("operation", ["Browse / refresh sources", "Upload documents"])
def test_unavailable_backend_has_no_mock_fallback(frontend, monkeypatch, operation):
    ui, _ = frontend
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: [uploaded_file()])

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("Backend offline")

    monkeypatch.setattr(httpx, "post", unavailable)
    ui.run()
    click(ui, operation)
    assert not ui.exception
    assert "Backend offline" in ui.error[0].value
    assert not ui.success
    assert not ui.selectbox


@pytest.mark.parametrize("body", ["not JSON", '{"ok":true}'])
def test_malformed_document_response_is_rejected(monkeypatch, body):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, text=body, request=httpx.Request("POST", BACKEND_URL)
        ),
    )
    with pytest.raises(ValueError):
        post_document_request(
            BACKEND_URL,
            "/v1/documents:ingest",
            build_upload_request([uploaded_file()]),
            IngestResult,
        )
