"""Run with: python -m uvicorn evidencedesk.api.app:app --host 127.0.0.1."""

import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from evidencedesk.contracts.models import (
    Draft,
    DraftInput,
    Envelope,
    Health,
    IngestInput,
    IngestResult,
    QueryInput,
    QueryResult,
    SearchResult,
    SourcesInput,
    SourcesResult,
    ToolError,
    TraceStep,
    VerifyInput,
)
from evidencedesk.core.factory import Tools, build_tools
from evidencedesk.core.responses import failure, success
from evidencedesk.core.settings import Settings, get_settings

ERROR_STATUS = {
    "BAD_INPUT": 422,
    "NOT_FOUND": 404,
    "INDEX_EMPTY": 409,
    "BUSY": 409,
    "UNSUPPORTED_FORMAT": 422,
    "EMPTY_DOCUMENT": 422,
    "EMBEDDING_UNAVAILABLE": 503,
    "MODEL_UNAVAILABLE": 503,
    "MODEL_TIMEOUT": 504,
    "INVALID_MODEL_OUTPUT": 502,
    "NOT_IMPLEMENTED": 501,
    "INTERNAL_ERROR": 500,
}
ERROR_RESPONSES = {
    status: {
        "model": Envelope[None],
        "description": " / ".join(code for code, value in ERROR_STATUS.items() if value == status),
    }
    for status in sorted(set(ERROR_STATUS.values()))
}
logger = logging.getLogger(__name__)


class ToolFailure(Exception):
    def __init__(self, error: ToolError):
        self.error = error


def unwrap(response: Envelope):
    if response.ok and response.data is not None and response.error is None:
        return response.data
    if not response.ok and response.data is None and response.error is not None:
        raise ToolFailure(response.error)
    raise ToolFailure(
        ToolError(code="INTERNAL_ERROR", message="Invalid tool response envelope.", retryable=False)
    )


def create_app(settings: Settings | None = None, tools: Tools | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.app_mode != "mock":
        raise RuntimeError("Only APP_MODE=mock is implemented; live adapters are not ready.")
    tools = tools or build_tools(settings)
    application = FastAPI(title="EvidenceDesk mock API", version="0.1.0", responses=ERROR_RESPONSES)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=failure("BAD_INPUT", "Request does not match contract v1.").model_dump(),
        )

    @application.exception_handler(ToolFailure)
    async def failed_tool(request: Request, exc: ToolFailure):
        return JSONResponse(
            status_code=ERROR_STATUS[exc.error.code],
            content=failure(
                exc.error.code, exc.error.message, retryable=exc.error.retryable
            ).model_dump(),
        )

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            code, message = "INTERNAL_ERROR", "Unexpected backend error."
            logger.error("HTTP error %s on %s", exc.status_code, request.url.path)
        else:
            code = "NOT_FOUND" if exc.status_code == 404 else "BAD_INPUT"
            message = str(exc.detail)
        return JSONResponse(
            status_code=ERROR_STATUS[code],
            content=failure(code, message).model_dump(),
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unexpected backend error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=failure("INTERNAL_ERROR", "Unexpected backend error.").model_dump(),
        )

    @application.get("/v1/health", response_model=Envelope[Health])
    def health():
        """Report mock readiness and fixture counts; no live services are probed."""
        return success(
            Health(
                mode="mock",
                ready=True,
                ollama_available=False,
                generation_model=settings.generation_model,
                embedding_model=settings.embedding_model,
                index_revision=1,
                document_count=1,
            )
        )

    @application.post("/v1/documents:ingest", response_model=Envelope[IngestResult])
    def ingest(request: IngestInput):
        result = tools.ingest(request)
        unwrap(result)
        return result

    @application.post("/v1/sources:read", response_model=Envelope[SourcesResult])
    def sources(request: SourcesInput):
        result = tools.sources(request)
        unwrap(result)
        return result

    @application.post("/v1/search", response_model=Envelope[SearchResult])
    def search(request: QueryInput):
        result = tools.search(request)
        unwrap(result)
        return result

    @application.post("/v1/query", response_model=Envelope[QueryResult])
    def query(request: QueryInput):
        trace = []
        started = perf_counter()
        retrieval = unwrap(tools.search(request))
        trace.append(_step("retrieve", started))
        started = perf_counter()
        draft = unwrap(tools.draft(DraftInput(query=request, retrieval=retrieval)))
        trace.append(_step("draft", started))
        started = perf_counter()
        verification = unwrap(
            tools.verify(VerifyInput(query=request, retrieval=retrieval, draft=draft))
        )
        trace.append(_step("verify", started))
        if draft.claims and not verification.passed:
            draft = Draft(
                status="insufficient_evidence",
                claims=[],
                conflicts=[],
                clarification=None,
                fallback_reason="failed_verification",
            )
        return success(
            QueryResult(
                mode="mock",
                result=draft,
                retrieval=retrieval,
                verification=verification,
                trace=trace,
            )
        )

    return application


def _step(name, started: float) -> TraceStep:
    return TraceStep(
        step=name, status="ok", duration_ms=max(0, round((perf_counter() - started) * 1000))
    )


app = create_app()
