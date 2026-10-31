"""Run with: python -m uvicorn evidencedesk.api.app:app --host 127.0.0.1."""

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


class ToolFailure(Exception):
    def __init__(self, error: ToolError):
        self.error = error


def unwrap(response: Envelope):
    if not response.ok or response.data is None:
        raise ToolFailure(
            response.error
            or ToolError(code="INTERNAL_ERROR", message="Empty tool response.", retryable=False)
        )
    return response.data


def create_app(settings: Settings | None = None, tools: Tools | None = None) -> FastAPI:
    settings = settings or get_settings()
    tools = tools or build_tools(settings)
    application = FastAPI(title="EvidenceDesk mock API", version="0.1.0")

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
        code = "NOT_FOUND" if exc.status_code == 404 else "BAD_INPUT"
        return JSONResponse(
            status_code=exc.status_code,
            content=failure(code, str(exc.detail)).model_dump(),
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=failure("INTERNAL_ERROR", "Unexpected backend error.").model_dump(),
        )

    @application.get("/v1/health", response_model=Envelope[Health])
    def health():
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
