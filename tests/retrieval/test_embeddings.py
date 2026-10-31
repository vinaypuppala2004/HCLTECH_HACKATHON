"""Simulated HTTP responses test the adapter without downloading a model."""

import json
from threading import Lock

import httpx
import pytest

from evidencedesk.contracts.models import EmbeddingInput
from evidencedesk.retrieval.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    OllamaEmbeddings,
)

DIGEST = "a" * 64


def vector(value=0.25):
    return [value] * EMBEDDING_DIMENSIONS


def model_tags(digest=DIGEST):
    return {"models": [{"name": EMBEDDING_MODEL, "digest": digest}]}


@pytest.fixture
def request_data():
    return EmbeddingInput(texts=["Reset my password", "Account access"], kind="query")


def call_adapter(request_data, embed_response, *, tags=None):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=model_tags() if tags is None else tags)
        return embed_response

    with httpx.Client(
        base_url="http://ollama.test:11434", transport=httpx.MockTransport(handler), timeout=1
    ) as client:
        return OllamaEmbeddings(client)(request_data)


@pytest.mark.parametrize(
    ("kind", "prefix"), [("query", "search_query: "), ("document", "search_document: ")]
)
def test_embeds_in_order_with_task_prefix_and_model_identity(request_data, kind, prefix):
    request_data.kind = kind
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=model_tags())
        assert json.loads(request.content) == {
            "model": EMBEDDING_MODEL,
            "input": [prefix + text for text in request_data.texts],
            "truncate": False,
        }
        return httpx.Response(
            200, json={"model": EMBEDDING_MODEL, "embeddings": [vector(0.1), vector(0.2)]}
        )

    with httpx.Client(
        base_url="http://ollama.test:11434", transport=httpx.MockTransport(handler), timeout=1
    ) as client:
        response = OllamaEmbeddings(client)(request_data)
        assert not client.is_closed

    assert response.ok and response.error is None
    result = response.data
    assert result is not None
    assert result.model == EMBEDDING_MODEL
    assert result.model_digest == DIGEST
    assert result.dimensions == 768
    assert result.vectors == [vector(0.1), vector(0.2)]
    assert calls == [("GET", "/api/tags"), ("POST", "/api/embed"), ("GET", "/api/tags")]


@pytest.mark.parametrize("texts", [[], [""], ["  \n"], ["valid", " "]])
def test_empty_input_is_rejected_without_http_calls(texts):
    def handler(request):
        pytest.fail("Invalid input must not reach Ollama.")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OllamaEmbeddings(client)(EmbeddingInput(texts=texts, kind="document"))

    assert not response.ok and response.data is None
    assert response.error.code == "BAD_INPUT"


def test_missing_model_is_explicit_and_does_not_embed_or_pull(request_data):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"models": [{"name": "qwen3:4b", "digest": DIGEST}]})

    with httpx.Client(
        base_url="http://ollama.test:11434", transport=httpx.MockTransport(handler)
    ) as client:
        response = OllamaEmbeddings(client)(request_data)

    assert not response.ok and response.data is None
    assert response.error.code == "EMBEDDING_UNAVAILABLE"
    assert not response.error.retryable
    assert calls == ["/api/tags"]


@pytest.mark.parametrize(
    ("payload", "raw"),
    [
        ({"model": "another-model", "embeddings": [vector(), vector()]}, None),
        ({"model": EMBEDDING_MODEL, "embeddings": [vector()]}, None),
        ({"model": EMBEDDING_MODEL, "embeddings": [vector(), vector()[:-1]]}, None),
        ({"model": EMBEDDING_MODEL, "embeddings": [vector(), vector(0)]}, None),
        ({"model": EMBEDDING_MODEL, "embeddings": [vector(), ["0.25"] * 768]}, None),
        ({"model": EMBEDDING_MODEL, "embeddings": [vector(), [True] * 768]}, None),
        ({"model": EMBEDDING_MODEL}, None),
        pytest.param(
            None,
            json.dumps(
                {"model": EMBEDDING_MODEL, "embeddings": [vector(float("nan")), vector()]}
            ).encode(),
            id="nan",
        ),
        pytest.param(
            None,
            json.dumps(
                {"model": EMBEDDING_MODEL, "embeddings": [vector(float("inf")), vector()]}
            ).encode(),
            id="infinity",
        ),
        (None, b"not-json"),
    ],
)
def test_malformed_vectors_and_responses_are_rejected(request_data, payload, raw):
    upstream = httpx.Response(200, content=raw) if raw else httpx.Response(200, json=payload)

    response = call_adapter(request_data, upstream)

    assert not response.ok and response.data is None
    assert response.error.code == "INVALID_MODEL_OUTPUT"


@pytest.mark.parametrize("tags", [{}, {"models": [{}]}, {"models": "invalid"}])
def test_invalid_model_inventory_is_rejected(request_data, tags):
    response = call_adapter(request_data, httpx.Response(200), tags=tags)

    assert not response.ok
    assert response.error.code == "INVALID_MODEL_OUTPUT"


def test_changed_model_digest_discards_vectors(request_data):
    reads = 0

    def handler(request):
        nonlocal reads
        if request.url.path == "/api/tags":
            reads += 1
            return httpx.Response(200, json=model_tags(DIGEST if reads == 1 else "b" * 64))
        return httpx.Response(
            200, json={"model": EMBEDDING_MODEL, "embeddings": [vector(), vector()]}
        )

    with httpx.Client(
        base_url="http://ollama.test:11434", transport=httpx.MockTransport(handler)
    ) as client:
        response = OllamaEmbeddings(client)(request_data)

    assert not response.ok and response.data is None
    assert response.error.code == "INVALID_MODEL_OUTPUT"
    assert "changed" in response.error.message
    assert response.error.retryable


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "BAD_INPUT", False),
        (404, "EMBEDDING_UNAVAILABLE", False),
        (429, "BUSY", True),
        (500, "EMBEDDING_UNAVAILABLE", True),
    ],
)
def test_upstream_http_errors_have_explicit_envelopes(request_data, status, code, retryable):
    response = call_adapter(request_data, httpx.Response(status))

    assert not response.ok and response.data is None
    assert response.error.code == code
    assert response.error.retryable is retryable


@pytest.mark.parametrize(
    ("error_type", "code"),
    [(httpx.ConnectError, "EMBEDDING_UNAVAILABLE"), (httpx.ReadTimeout, "MODEL_TIMEOUT")],
)
@pytest.mark.parametrize("failed_path", ["/api/tags", "/api/embed"])
def test_transport_errors_release_the_shared_lock(request_data, error_type, code, failed_path):
    request_lock = Lock()

    def handler(request):
        if request.url.path == failed_path:
            raise error_type("simulated failure", request=request)
        return httpx.Response(200, json=model_tags())

    with httpx.Client(
        base_url="http://ollama.test:11434", transport=httpx.MockTransport(handler)
    ) as client:
        response = OllamaEmbeddings(client, request_lock=request_lock)(request_data)

    assert not response.ok and response.data is None
    assert response.error.code == code
    assert response.error.retryable
    assert not request_lock.locked()


def test_busy_lock_prevents_a_second_model_request(request_data):
    request_lock = Lock()

    def handler(request):
        pytest.fail("A busy model must not receive another request.")

    with request_lock, httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OllamaEmbeddings(client, request_lock=request_lock)(request_data)
        assert request_lock.locked()

    assert not response.ok and response.data is None
    assert response.error.code == "BUSY"
    assert response.error.retryable
