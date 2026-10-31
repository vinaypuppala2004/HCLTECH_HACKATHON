"""D1 HTTP contract checks using the existing mock tools only."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from evidencedesk.api.app import create_app
from evidencedesk.contracts.models import (
    Envelope,
    Health,
    IngestResult,
    QueryResult,
    SearchResult,
    SourcesResult,
    Verification,
)
from evidencedesk.core.factory import build_tools
from evidencedesk.core.responses import failure, success
from evidencedesk.core.settings import Settings

QUERY = {
    "question": "How do I reset my password?",
    "context": {"product": None, "version": None, "environment": None},
}
UPLOAD = {
    "filename": "sample.txt",
    "content_base64": "SGVsbG8=",
    "metadata": {
        "title": "Sample",
        "source_url": None,
        "product": None,
        "version": None,
        "environment": None,
        "family_id": None,
        "published_at": None,
        "origin": "user",
    },
}
POST_ROUTES = {
    "/v1/documents:ingest": {"documents": [UPLOAD]},
    "/v1/sources:read": {"document_id": None},
    "/v1/search": QUERY,
    "/v1/query": QUERY,
}


@pytest.fixture
def tools():
    return build_tools(Settings())


@pytest.fixture
def client():
    with TestClient(create_app(Settings()), raise_server_exceptions=False) as value:
        yield value


def assert_failure(response, status, code, *, retryable=False):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    Envelope[None].model_validate(body)
    assert set(body) == {"ok", "request_id", "data", "error"}
    assert body["ok"] is False
    assert body["data"] is None
    assert body["request_id"]
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["retryable"] is retryable
    return body


def test_health_reports_mock_readiness_and_configured_models():
    settings = Settings(
        generation_model="configured-generator", embedding_model="configured-embedder"
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/health")
        assert response.status_code == 200
        health = Envelope[Health].model_validate(response.json())
        assert health.ok and health.error is None
        assert health.data == Health(
            mode="mock",
            ready=True,
            ollama_available=False,
            generation_model=settings.generation_model,
            embedding_model=settings.embedding_model,
            index_revision=1,
            document_count=1,
        )
        listed = client.post("/v1/sources:read", json={"document_id": None}).json()["data"]
        retrieved = client.post("/v1/search", json=QUERY).json()["data"]
        assert health.data.document_count == len(listed["documents"])
        assert health.data.index_revision == retrieved["index_revision"]


@pytest.mark.parametrize("mode", ["live", "invalid"])
@pytest.mark.parametrize("injected", [False, True])
def test_unsupported_mode_cannot_be_misreported_as_mock_ready(tools, mode, injected):
    with pytest.raises(RuntimeError, match="Only APP_MODE=mock is implemented"):
        create_app(Settings(app_mode=mode), tools=tools if injected else None)


@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("/v1/documents:ingest", IngestResult),
        ("/v1/sources:read", SourcesResult),
        ("/v1/search", SearchResult),
        ("/v1/query", QueryResult),
    ],
)
def test_public_post_endpoints_return_contract_envelopes(client, path, model):
    response = client.post(path, json=POST_ROUTES[path])
    assert response.status_code == 200
    result = Envelope[model].model_validate(response.json())
    assert result.ok and result.data is not None and result.error is None
    assert result.request_id


def test_mock_ingestion_reports_per_file_rejections_without_indexing(client):
    response = client.post("/v1/documents:ingest", json={"documents": [UPLOAD] * 20})
    assert response.status_code == 200
    result = Envelope[IngestResult].model_validate(response.json()).data
    assert len(result.results) == 20
    for item in result.results:
        assert item.state == "rejected"
        assert item.document_id is None and item.passage_count == 0
        assert item.error.code == "NOT_IMPLEMENTED"
    assert client.get("/v1/health").json()["data"]["index_revision"] == result.index_revision


def test_source_listing_reading_and_missing_document(client):
    listing = client.post("/v1/sources:read", json={"document_id": None}).json()["data"]
    assert listing["passages"] == []
    document_id = listing["documents"][0]["document_id"]
    response = client.post("/v1/sources:read", json={"document_id": document_id})
    result = Envelope[SourcesResult].model_validate(response.json()).data
    assert result.documents[0].document_id == document_id
    assert result.passages[0].document_id == document_id
    assert_failure(
        client.post("/v1/sources:read", json={"document_id": "missing"}), 404, "NOT_FOUND"
    )


@pytest.mark.parametrize("path", ["/v1/search", "/v1/query"])
@pytest.mark.parametrize("question", ["  question  ", "x" * 2000])
def test_valid_questions_are_trimmed_and_scope_is_forwarded(tools, path, question):
    received = []

    def search(request):
        received.append(request)
        return tools.search(request)

    scope = {"product": "Example", "version": "1.0", "environment": "local"}
    with TestClient(create_app(Settings(), replace(tools, search=search))) as client:
        response = client.post(path, json={"question": question, "context": scope})
    assert response.status_code == 200
    assert len(received) == 1
    assert received[0].question == question.strip()
    assert received[0].context.model_dump() == scope


INVALID_QUERIES = [
    {},
    None,
    [],
    {"question": "question"},
    {**QUERY, "question": ""},
    {**QUERY, "question": " \t\n "},
    {**QUERY, "question": "x" * 2001},
    {**QUERY, "question": 123},
    {**QUERY, "question": None},
    {**QUERY, "context": None},
    {**QUERY, "context": {}},
    {**QUERY, "context": {**QUERY["context"], "extra": True}},
    {**QUERY, "context": {**QUERY["context"], "version": 1}},
    {**QUERY, "extra": True},
]


@pytest.mark.parametrize("path", ["/v1/search", "/v1/query"])
@pytest.mark.parametrize("payload", INVALID_QUERIES)
def test_invalid_query_requests_are_rejected_before_tool_calls(tools, path, payload):
    def unexpected_call(request):
        pytest.fail("Invalid input must not reach tools.")

    with TestClient(create_app(Settings(), replace(tools, search=unexpected_call))) as client:
        assert_failure(client.post(path, json=payload), 422, "BAD_INPUT")


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/sources:read", {}),
        ("/v1/sources:read", {"document_id": 123}),
        ("/v1/sources:read", {"document_id": None, "extra": True}),
        ("/v1/documents:ingest", {}),
        ("/v1/documents:ingest", {"documents": []}),
        ("/v1/documents:ingest", {"documents": [UPLOAD] * 21}),
        ("/v1/documents:ingest", {"documents": [{**UPLOAD, "filename": ""}]}),
        ("/v1/documents:ingest", {"documents": [{**UPLOAD, "metadata": {}}]}),
        ("/v1/documents:ingest", {"documents": [{**UPLOAD, "extra": True}]}),
        (
            "/v1/documents:ingest",
            {"documents": [{**UPLOAD, "metadata": {**UPLOAD["metadata"], "origin": "unknown"}}]},
        ),
    ],
)
def test_invalid_source_and_ingest_requests_do_not_reach_tools(tools, path, payload):
    def unexpected_call(request):
        pytest.fail("Invalid input must not reach tools.")

    overrides = replace(tools, ingest=unexpected_call, sources=unexpected_call)
    with TestClient(create_app(Settings(), overrides)) as client:
        assert_failure(client.post(path, json=payload), 422, "BAD_INPUT")


@pytest.mark.parametrize("path", POST_ROUTES)
@pytest.mark.parametrize("body", ["{", "", "null"])
def test_malformed_or_missing_json_has_a_contract_error(client, path, body):
    response = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert_failure(response, 422, "BAD_INPUT")


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("BAD_INPUT", 422),
        ("UNSUPPORTED_FORMAT", 422),
        ("EMPTY_DOCUMENT", 422),
        ("NOT_FOUND", 404),
        ("INDEX_EMPTY", 409),
        ("BUSY", 409),
        ("EMBEDDING_UNAVAILABLE", 503),
        ("MODEL_UNAVAILABLE", 503),
        ("MODEL_TIMEOUT", 504),
        ("INVALID_MODEL_OUTPUT", 502),
        ("NOT_IMPLEMENTED", 501),
        ("INTERNAL_ERROR", 500),
    ],
)
def test_tool_errors_follow_the_frozen_status_table(tools, code, status):
    def search(request):
        return failure(code, "Explicit tool failure.", retryable=True)

    with TestClient(create_app(Settings(), replace(tools, search=search))) as client:
        body = assert_failure(client.post("/v1/search", json=QUERY), status, code, retryable=True)
        assert body["error"]["message"] == "Explicit tool failure."


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("ingest", "/v1/documents:ingest"),
        ("sources", "/v1/sources:read"),
        ("search", "/v1/query"),
        ("draft", "/v1/query"),
        ("verify", "/v1/query"),
    ],
)
def test_endpoint_and_query_stage_failures_are_explicit(tools, tool, path):
    called = []

    def broken(request):
        called.append(tool)
        return failure("BUSY", "Try again.", retryable=True)

    def later(request):
        pytest.fail("A failed query stage must stop the request.")

    overrides = {tool: broken}
    if tool == "search":
        overrides.update(draft=later, verify=later)
    elif tool == "draft":
        overrides.update(verify=later)
    with TestClient(create_app(Settings(), replace(tools, **overrides))) as client:
        assert_failure(client.post(path, json=POST_ROUTES[path]), 409, "BUSY", retryable=True)
    assert called == [tool]


@pytest.mark.parametrize("kind", ["exception", "empty", "inconsistent", "wrong_output"])
def test_unexpected_or_invalid_tool_output_is_a_safe_internal_error(tools, kind):
    def broken(request):
        if kind == "exception":
            raise RuntimeError("private backend details")
        if kind == "wrong_output":
            return success(SourcesResult(documents=[], passages=[]))
        if kind == "empty":
            return Envelope(ok=True, request_id="tool", data=None, error=None)
        return Envelope(
            ok=True,
            request_id="tool",
            data=SearchResult(index_revision=0, hits=[], warnings=[]),
            error=failure("BUSY", "Inconsistent success.").error,
        )

    with TestClient(
        create_app(Settings(), replace(tools, search=broken)), raise_server_exceptions=False
    ) as client:
        response = client.post("/v1/search", json=QUERY)
    assert_failure(response, 500, "INTERNAL_ERROR")
    assert "private backend details" not in response.text
    assert "validation errors" not in response.text


def test_failed_verification_returns_no_factual_claims(tools):
    def verify(request):
        return success(Verification(passed=False, evidence_strength="insufficient", checks=[]))

    with TestClient(create_app(Settings(), replace(tools, verify=verify))) as client:
        response = client.post("/v1/query", json=QUERY)
    assert response.status_code == 200
    result = Envelope[QueryResult].model_validate(response.json()).data
    assert result.mode == "mock"
    assert result.result.status == "insufficient_evidence"
    assert result.result.fallback_reason == "failed_verification"
    assert result.result.claims == []
    assert [step.step for step in result.trace] == ["retrieve", "draft", "verify"]


def test_routing_errors_follow_contract_statuses_and_preserve_allow_header(client):
    assert_failure(client.get("/missing"), 404, "NOT_FOUND")
    response = client.get("/v1/query")
    assert_failure(response, 422, "BAD_INPUT")
    assert response.headers["allow"] == "POST"


def test_server_http_exception_does_not_become_bad_input_or_leak_details(tools):
    def search(request):
        raise HTTPException(status_code=500, detail="private backend details")

    with TestClient(create_app(Settings(), replace(tools, search=search))) as client:
        response = client.post("/v1/search", json=QUERY)
    assert_failure(response, 500, "INTERNAL_ERROR")
    assert "private backend details" not in response.text


def test_errors_have_distinct_request_ids(client):
    first = assert_failure(client.post("/v1/query", json={}), 422, "BAD_INPUT")
    second = assert_failure(client.post("/v1/query", json={}), 422, "BAD_INPUT")
    assert first["request_id"] != second["request_id"]


def test_openapi_documents_contract_success_and_error_envelopes(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    for path in ["/v1/health", *POST_ROUTES]:
        operation = schema["paths"][path]["get" if path == "/v1/health" else "post"]
        assert "200" in operation["responses"]
        for status in ["404", "409", "422", "500", "501", "502", "503", "504"]:
            error_schema = operation["responses"][status]["content"]["application/json"]["schema"]
            error_model = schema["components"]["schemas"][error_schema["$ref"].split("/")[-1]]
            assert set(error_model["required"]) == {"ok", "request_id", "data", "error"}
    assert client.get("/docs").status_code == 200
