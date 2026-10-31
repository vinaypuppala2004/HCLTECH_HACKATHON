"""Opt-in Ollama embedding port; mock search does not call this adapter."""

from threading import Lock

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evidencedesk.contracts.models import EmbeddingInput, EmbeddingOutput, Envelope
from evidencedesk.core.responses import failure, success

EMBEDDING_MODEL = "qwen3:4b"
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


class _ModelDetails(BaseModel):
    model_config = ConfigDict(strict=True)

    capabilities: list[str]
    model_info: dict[str, object]


class OllamaEmbeddings:
    """Use only qwen3:4b against a configured embedding-mode Ollama runner.

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
            response = self._client.post("/api/show", json={"model": EMBEDDING_MODEL})
            response.raise_for_status()
            details = _ModelDetails.model_validate(response.json())
            # /api/show describes the model file, not runtime flags. A separate
            # runner can enable raw Qwen embeddings without changing this list.
            architecture = details.model_info.get("general.architecture")
            dimensions = details.model_info.get(f"{architecture}.embedding_length")
            if type(dimensions) is not int or dimensions < 1:
                return failure("INVALID_MODEL_OUTPUT", "Model embedding dimensions are invalid.")
            response = self._client.post(
                "/api/embed",
                json={
                    "model": EMBEDDING_MODEL,
                    "input": request.texts,
                    "truncate": False,
                    "keep_alive": "1m",
                    "options": {"num_ctx": 1024, "num_batch": 64, "num_gpu": 0},
                },
            )
            response.raise_for_status()
            result = _EmbedResponse.model_validate(response.json())
            if result.model != EMBEDDING_MODEL:
                return failure(
                    "INVALID_MODEL_OUTPUT", "Ollama returned a different embedding model."
                )
            if len(result.embeddings) != len(request.texts) or any(
                len(vector) != dimensions or not any(vector) for vector in result.embeddings
            ):
                return failure(
                    "INVALID_MODEL_OUTPUT",
                    "Expected one nonzero vector per text with the model's declared dimensions.",
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
                    dimensions=dimensions,
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
            if status == 501:
                return failure(
                    "EMBEDDING_UNAVAILABLE",
                    "The Qwen runner is not in embedding mode. Start "
                    "python -m evidencedesk.retrieval.embedding_server and use "
                    "http://127.0.0.1:11435 for the embedding client.",
                )
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
