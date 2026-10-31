"""Opt-in Ollama embedding port; mock search does not call this adapter."""

from threading import Lock

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evidencedesk.contracts.models import EmbeddingInput, EmbeddingOutput, Envelope
from evidencedesk.core.responses import failure, success

EMBEDDING_MODEL = "nomic-embed-text:v1.5"
EMBEDDING_DIMENSIONS = 768
_DEFAULT_REQUEST_LOCK = Lock()


class _ModelTag(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    digest: str = Field(min_length=1)


class _TagsResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    models: list[_ModelTag]


class _EmbedResponse(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    model: str
    embeddings: list[list[float]]


class OllamaEmbeddings:
    """Implement EmbeddingPort using a caller-owned HTTP client and shared lock.

    The client supplies the Ollama base URL and timeout. Pass the same request_lock
    to future generation adapters to share the single-model request limit.
    """

    def __init__(self, client: httpx.Client, *, request_lock: Lock | None = None):
        self._client = client
        self._request_lock = request_lock if request_lock is not None else _DEFAULT_REQUEST_LOCK

    def __call__(self, request: EmbeddingInput) -> Envelope[EmbeddingOutput]:
        if not request.texts or any(not text.strip() for text in request.texts):
            return failure("BAD_INPUT", "Embedding requires at least one nonblank text.")
        if not self._request_lock.acquire(blocking=False):
            return failure("BUSY", "Another local model request is running.", retryable=True)
        try:
            digest = self._model_digest()
            if digest is None:
                return failure(
                    "EMBEDDING_UNAVAILABLE",
                    f"Required local model {EMBEDDING_MODEL} is not installed.",
                )
            prefix = "search_query: " if request.kind == "query" else "search_document: "
            response = self._client.post(
                "/api/embed",
                json={
                    "model": EMBEDDING_MODEL,
                    "input": [prefix + text for text in request.texts],
                    "truncate": False,
                },
            )
            response.raise_for_status()
            result = _EmbedResponse.model_validate(response.json())
            if result.model != EMBEDDING_MODEL:
                return failure(
                    "INVALID_MODEL_OUTPUT", "Ollama returned a different embedding model."
                )
            if len(result.embeddings) != len(request.texts) or any(
                len(vector) != EMBEDDING_DIMENSIONS or not any(vector)
                for vector in result.embeddings
            ):
                return failure(
                    "INVALID_MODEL_OUTPUT", "Expected one nonzero 768-dimensional vector per text."
                )
            if self._model_digest() != digest:
                return failure(
                    "INVALID_MODEL_OUTPUT",
                    "Embedding model changed during the request; retry it.",
                    retryable=True,
                )
            return success(
                EmbeddingOutput(
                    model=EMBEDDING_MODEL,
                    model_digest=digest,
                    dimensions=EMBEDDING_DIMENSIONS,
                    vectors=result.embeddings,
                )
            )
        except httpx.TimeoutException:
            return failure("MODEL_TIMEOUT", "Local embedding request timed out.", retryable=True)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 400:
                return failure(
                    "BAD_INPUT", "Ollama rejected the embedding input; check text length."
                )
            if status == 429:
                return failure("BUSY", "Ollama is busy.", retryable=True)
            return failure(
                "EMBEDDING_UNAVAILABLE",
                f"Ollama embedding request failed with HTTP {status}.",
                retryable=status >= 500,
            )
        except httpx.RequestError:
            return failure("EMBEDDING_UNAVAILABLE", "Cannot reach local Ollama.", retryable=True)
        except (ValidationError, ValueError):
            return failure("INVALID_MODEL_OUTPUT", "Ollama returned invalid embedding data.")
        finally:
            self._request_lock.release()

    def _model_digest(self) -> str | None:
        response = self._client.get("/api/tags")
        response.raise_for_status()
        tags = _TagsResponse.model_validate(response.json())
        return next((tag.digest for tag in tags.models if tag.name == EMBEDDING_MODEL), None)
