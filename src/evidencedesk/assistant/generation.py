"""Qwen generation port with schema-constrained JSON and explicit service errors."""

import json
from threading import Lock
from typing import Literal

import httpx
from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evidencedesk.assistant.model_runtime import MODEL_REQUEST_LOCK
from evidencedesk.contracts.models import Envelope, GenerationInput, GenerationOutput
from evidencedesk.core.responses import failure, success

GENERATION_MODEL = "qwen3:4b"


class _Message(BaseModel):
    model_config = ConfigDict(strict=True)

    role: Literal["assistant"]
    content: str


class _ChatResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    model: str
    message: _Message
    done: Literal[True]
    done_reason: str | None = None
    prompt_eval_count: int = Field(ge=0)
    eval_count: int = Field(ge=0)
    total_duration: int = Field(ge=0)


class _ModelTag(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    digest: str = Field(min_length=1)


class _Tags(BaseModel):
    model_config = ConfigDict(strict=True)

    models: list[_ModelTag]


def _reject_constant(value: str):
    raise ValueError(f"Nonfinite JSON constant {value} is not permitted.")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are not permitted.")
        result[key] = value
    return result


def _local_references_only(value: object) -> bool:
    if isinstance(value, list):
        return all(_local_references_only(item) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("$ref", "$dynamicRef") and (
                not isinstance(item, str) or not item.startswith("#")
            ):
                return False
            if not _local_references_only(item):
                return False
    return True


class OllamaGeneration:
    """Implement GenerationPort using a caller-owned, explicitly timed HTTP client.

    Only the final JSON content is returned. Private thinking text is neither
    exposed nor used as evidence. Timing/token values come from Ollama's response.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        request_lock: Lock | None = None,
        context_tokens: int = 8192,
        max_output_tokens: int = 2048,
    ):
        if (
            type(context_tokens) is not int
            or type(max_output_tokens) is not int
            or max_output_tokens < 1
            or context_tokens <= max_output_tokens + 1024
        ):
            raise ValueError("Context must leave room for output and template overhead.")
        self._client = client
        self._request_lock = request_lock if request_lock is not None else MODEL_REQUEST_LOCK
        self._context_tokens = context_tokens
        self._max_output_tokens = max_output_tokens
        # UTF-8 bytes conservatively upper-bound byte-fallback text tokens.
        self.max_prompt_bytes = context_tokens - max_output_tokens - 1024

    def __call__(self, request: GenerationInput) -> Envelope[GenerationOutput]:
        if (
            not request.messages
            or len(request.messages) > 8
            or any(not message.content.strip() for message in request.messages)
            or not any(message.role == "user" for message in request.messages)
        ):
            return failure("BAD_INPUT", "Generation requires nonblank messages and a user message.")
        if sum(len(message.content.encode("utf-8")) for message in request.messages) > self.max_prompt_bytes:
            return failure("BAD_INPUT", "Prompt exceeds the configured context budget; shorten the evidence.")
        try:
            schema_json = json.dumps(request.response_schema, allow_nan=False)
            if len(schema_json.encode()) > 65536 or not _local_references_only(request.response_schema):
                return failure("BAD_INPUT", "Response schema must be bounded and use only local references.")
            Draft202012Validator.check_schema(request.response_schema)
            validator = Draft202012Validator(request.response_schema)
        except (SchemaError, ValueError, TypeError, RecursionError):
            return failure("BAD_INPUT", "Invalid generation response schema.")
        if not self._request_lock.acquire(blocking=False):
            return failure("BUSY", "Another local model request is running.", retryable=True)
        try:
            digest = self._model_digest()
            if digest is None:
                return failure("MODEL_UNAVAILABLE", f"Required local model {GENERATION_MODEL} is not installed.")
            response = self._client.post(
                "/api/chat",
                json={
                    "model": GENERATION_MODEL,
                    "messages": [message.model_dump(mode="json") for message in request.messages],
                    "format": request.response_schema,
                    "stream": False,
                    "think": True,
                    "keep_alive": "5m",
                    "options": {
                        "temperature": 0,
                        "seed": 42,
                        "num_ctx": self._context_tokens,
                        "num_predict": self._max_output_tokens,
                        "num_batch": 128,
                    },
                },
            )
            response.raise_for_status()
            result = _ChatResponse.model_validate(response.json())
            if result.model != GENERATION_MODEL or result.done_reason in ("length", "max_tokens"):
                return failure("INVALID_MODEL_OUTPUT", "Qwen returned a wrong model or truncated reply.")
            if not result.message.content.strip() or len(result.message.content.encode()) > 65536:
                return failure("INVALID_MODEL_OUTPUT", "Qwen did not return bounded final JSON content.")
            try:
                content = json.loads(
                    result.message.content,
                    parse_constant=_reject_constant,
                    object_pairs_hook=_unique_object,
                )
                if not isinstance(content, dict):
                    raise ValueError("Generation content must be an object.")
                validator.validate(content)
            except Exception:
                return failure("INVALID_MODEL_OUTPUT", "Qwen output does not match the response schema.")
            if self._model_digest() != digest:
                return failure("INVALID_MODEL_OUTPUT", "Qwen changed during generation; retry.", retryable=True)
            return success(GenerationOutput(
                model=GENERATION_MODEL,
                model_digest=digest,
                content=content,
                prompt_tokens=result.prompt_eval_count,
                completion_tokens=result.eval_count,
                duration_ms=result.total_duration // 1_000_000,
            ))
        except httpx.TimeoutException:
            return failure("MODEL_TIMEOUT", "Local Qwen generation timed out.", retryable=True)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                return failure("BUSY", "Ollama is busy.", retryable=True)
            if status == 400:
                return failure("BAD_INPUT", "Ollama rejected the generation request or context settings.")
            return failure(
                "MODEL_UNAVAILABLE", f"Qwen generation failed with HTTP {status}.",
                retryable=status >= 500 and status != 501,
            )
        except httpx.RequestError:
            return failure("MODEL_UNAVAILABLE", "Cannot reach local Ollama.", retryable=True)
        except (ValidationError, ValueError, TypeError, RecursionError):
            return failure("INVALID_MODEL_OUTPUT", "Ollama returned invalid generation metadata.")
        finally:
            self._request_lock.release()

    def _model_digest(self) -> str | None:
        response = self._client.get("/api/tags")
        response.raise_for_status()
        tags = _Tags.model_validate(response.json())
        return next((tag.digest for tag in tags.models if tag.name == GENERATION_MODEL), None)
