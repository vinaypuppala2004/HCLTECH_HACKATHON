"""D2 lifecycle, shared-port forwarding, and concurrent HTTP request checks."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient

from evidencedesk.api import app as api_module
from evidencedesk.contracts.models import (
    DraftInput,
    IngestInput,
    QueryInput,
    SourcesInput,
    VerifyInput,
)
from evidencedesk.core.factory import Tools, build_tools
from evidencedesk.core.responses import failure
from evidencedesk.core.runtime import BackendBusy, BackendRuntime
from evidencedesk.core.settings import Settings
from evidencedesk.mocks.fixtures import mock_hit

QUERY = {
    "question": "How do I reset my password?",
    "context": {"product": None, "version": None, "environment": None},
}
POST_ROUTES = ["/v1/query", "/v1/search", "/v1/sources:read", "/v1/documents:ingest"]


def payload(path):
    if path == "/v1/sources:read":
        return {"document_id": None}
    if path == "/v1/documents:ingest":
        return {
            "documents": [
                {
                    "filename": "synthetic.txt",
                    "content_base64": "SGVsbG8=",
                    "metadata": mock_hit().document.metadata.model_dump(),
                }
            ]
        }
    return QUERY


def assert_busy(response):
    assert response.status_code == 409
    body = response.json()
    assert body["ok"] is False and body["data"] is None
    assert body["error"]["code"] == "BUSY"
    assert body["error"]["retryable"] is True
    assert body["request_id"]


def test_factory_runs_once_per_lifespan_and_health_tracks_readiness(monkeypatch):
    created = []

    def factory(settings):
        created.append(settings)
        return build_tools(settings)

    monkeypatch.setattr(api_module, "build_tools", factory)
    settings = Settings()
    app = api_module.create_app(settings)
    assert created == []
    assert not app.state.backend.ready
    for count in (1, 2):
        with TestClient(app) as client:
            assert created == [settings] * count
            assert client.get("/v1/health").json()["data"]["ready"] is True
            for _ in range(2):
                assert client.post("/v1/query", json=QUERY).status_code == 200
            assert len(created) == count
        assert not app.state.backend.ready


def test_injected_ports_receive_typed_requests_and_pipeline_outputs(monkeypatch):
    base = build_tools(Settings())
    received = []

    def wrap(name):
        def invoke(request):
            received.append((name, request))
            return getattr(base, name)(request)

        return invoke

    def unexpected_factory(settings):
        pytest.fail("Injected tools must not fall back to the default factory.")

    monkeypatch.setattr(api_module, "build_tools", unexpected_factory)
    tools = Tools(
        **{name: wrap(name) for name in ("ingest", "sources", "search", "draft", "verify")}
    )
    with TestClient(api_module.create_app(Settings(), tools)) as client:
        for path in ("/v1/documents:ingest", "/v1/sources:read", "/v1/search", "/v1/query"):
            assert client.post(path, json=payload(path)).status_code == 200
    assert [name for name, _ in received] == [
        "ingest",
        "sources",
        "search",
        "search",
        "draft",
        "verify",
    ]
    for (_, request), model in zip(
        received,
        [IngestInput, SourcesInput, QueryInput, QueryInput, DraftInput, VerifyInput],
        strict=True,
    ):
        assert isinstance(request, model)
    draft_request = received[4][1]
    verify_request = received[5][1]
    assert draft_request.query is received[3][1]
    assert verify_request.query is draft_request.query
    assert verify_request.retrieval is draft_request.retrieval
    assert (
        verify_request.draft.claims[0].supports[0].quote
        in draft_request.retrieval.hits[0].passage.text
    )


def test_startup_failure_is_explicit_and_never_enables_requests(monkeypatch):
    def broken_factory(settings):
        raise RuntimeError("Adapter initialization failed.")

    monkeypatch.setattr(api_module, "build_tools", broken_factory)
    app = api_module.create_app(Settings())
    with pytest.raises(RuntimeError, match="Adapter initialization failed"):
        with TestClient(app):
            pytest.fail("Failed startup must not serve requests.")
    assert not app.state.backend.ready


@pytest.mark.parametrize("port", ["ingest", "sources", "search", "draft", "verify"])
def test_missing_tool_fails_startup(port):
    tools = replace(build_tools(Settings()), **{port: None})
    app = api_module.create_app(Settings(), tools)
    with pytest.raises(RuntimeError, match=f"Backend tool '{port}' is not callable"):
        with TestClient(app):
            pytest.fail("An incomplete bundle must not become ready.")
    assert not app.state.backend.ready


@pytest.mark.parametrize("started_before", [False, True])
def test_requests_outside_lifespan_are_rejected(started_before):
    app = api_module.create_app(Settings())
    if started_before:
        with TestClient(app) as client:
            assert client.post("/v1/query", json=QUERY).status_code == 200
    # TestClient without a context intentionally skips ASGI lifespan events.
    client = TestClient(app)
    try:
        assert client.get("/v1/health").json()["data"]["ready"] is False
        for path in POST_ROUTES:
            assert_busy(client.post(path, json=payload(path)))
    finally:
        client.close()


@pytest.mark.parametrize("held_port", ["ingest", "search", "draft", "verify"])
def test_overlapping_requests_are_busy_and_health_remains_available(held_port):
    base = build_tools(Settings())
    entered, release = Event(), Event()

    def held(request):
        entered.set()
        assert release.wait(10), "The test must release the active request."
        return getattr(base, held_port)(request)

    tools = replace(base, **{held_port: held})
    active_path = "/v1/documents:ingest" if held_port == "ingest" else "/v1/query"
    with TestClient(api_module.create_app(Settings(), tools)) as client:
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(client.post, active_path, json=payload(active_path))
            try:
                assert entered.wait(5), "The active request did not reach its tool."
                for path in POST_ROUTES:
                    assert_busy(client.post(path, json=payload(path)))
                health = client.get("/v1/health")
                assert health.status_code == 200
                assert health.json()["data"]["ready"] is True
            finally:
                release.set()
            assert active.result(timeout=5).status_code == 200
        # The slot must be available again after the complete operation finishes.
        assert client.post("/v1/query", json=QUERY).status_code == 200


@pytest.mark.parametrize("kind", ["tool_error", "exception", "invalid_envelope"])
def test_failed_operation_always_releases_request_slot(kind):
    base = build_tools(Settings())
    calls = 0

    def search(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            if kind == "tool_error":
                return failure("MODEL_TIMEOUT", "Model timed out.", retryable=True)
            if kind == "invalid_envelope":
                return None
            raise RuntimeError("Unexpected adapter failure.")
        return base.search(request)

    with TestClient(
        api_module.create_app(Settings(), replace(base, search=search)),
        raise_server_exceptions=False,
    ) as client:
        first = client.post("/v1/query", json=QUERY)
        assert first.status_code == (504 if kind == "tool_error" else 500)
        assert client.post("/v1/query", json=QUERY).status_code == 200


def test_shutdown_rejects_new_work_drains_active_request_and_allows_restart():
    built = []

    def factory():
        tools = build_tools(Settings())
        built.append(tools)
        return tools

    backend = BackendRuntime(factory)
    backend.start()
    entered, release = Event(), Event()

    def request():
        with backend.request() as tools:
            entered.set()
            assert release.wait(10)
            # Shutdown must keep the bundle usable until this request exits.
            return tools.search(QueryInput.model_validate(QUERY)).ok

    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(request)
        stopping = None
        try:
            assert entered.wait(5)
            stopping = pool.submit(backend.stop)
            deadline = monotonic() + 5
            while backend.ready and monotonic() < deadline:
                Event().wait(0.01)
            assert not backend.ready
            assert not stopping.done(), "Shutdown must wait for the active request."
            with pytest.raises(BackendBusy, match="not ready"):
                with backend.request():
                    pytest.fail("Shutdown must reject new work.")
        finally:
            release.set()
        assert active.result(timeout=5)
        stopping.result(timeout=5)
    assert not backend.ready
    backend.start()
    try:
        with backend.request() as tools:
            assert len(built) == 2
            assert tools is built[1] and tools is not built[0]
    finally:
        backend.stop()
