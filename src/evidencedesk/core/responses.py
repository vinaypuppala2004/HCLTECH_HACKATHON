"""Construct the same response envelope in every module."""

from uuid import uuid4

from evidencedesk.contracts.models import Envelope, ErrorCode, T, ToolError


def success(data: T) -> Envelope[T]:
    return Envelope(ok=True, request_id=f"req_{uuid4().hex}", data=data, error=None)


def failure(code: ErrorCode, message: str, *, retryable: bool = False) -> Envelope:
    return Envelope(
        ok=False,
        request_id=f"req_{uuid4().hex}",
        data=None,
        error=ToolError(code=code, message=message, retryable=retryable),
    )
