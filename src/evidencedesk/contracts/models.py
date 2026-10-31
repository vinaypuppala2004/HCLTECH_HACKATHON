"""Contract v1: closed JSON objects shared by tools, API, mocks, and UI."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

ErrorCode = Literal[
    "BAD_INPUT",
    "UNSUPPORTED_FORMAT",
    "EMPTY_DOCUMENT",
    "NOT_FOUND",
    "INDEX_EMPTY",
    "EMBEDDING_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "INVALID_MODEL_OUTPUT",
    "BUSY",
    "NOT_IMPLEMENTED",
    "INTERNAL_ERROR",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Scope(Contract):
    product: str | None
    version: str | None
    environment: str | None


class Metadata(Contract):
    title: str = Field(min_length=1)
    source_url: str | None
    product: str | None
    version: str | None
    environment: str | None
    family_id: str | None
    published_at: str | None
    origin: Literal["public", "synthetic", "user"]


class Document(Contract):
    document_id: str
    filename: str
    format: Literal["pdf", "html", "markdown", "txt"]
    metadata: Metadata
    sha256: str
    passage_count: int = Field(ge=0)


class Passage(Contract):
    passage_id: str
    document_id: str
    section_path: list[str]
    page: int | None = Field(ge=1)
    text: str


class Hit(Contract):
    document: Document
    passage: Passage
    rank: int = Field(ge=1)
    bm25_score: float | None
    cosine_score: float | None
    rrf_score: float
    selection: Literal["ranked", "version_counterpart"]
    applicable: bool


class Support(Contract):
    passage_id: str
    quote: str


class Claim(Contract):
    claim_id: str
    text: str
    supports: list[Support] = Field(min_length=1)


class Conflict(Contract):
    conflict_id: str
    kind: Literal["contradiction", "version_difference"]
    topic: str
    sides: list[Support] = Field(min_length=2)
    resolution: Literal["unresolved", "resolved_by_context"]
    selected_passage_ids: list[str]


class Clarification(Contract):
    field: Literal["product", "version", "environment"]
    question: str
    options: list[str]


class Draft(Contract):
    status: Literal["answered", "conflict", "needs_context", "not_found", "insufficient_evidence"]
    claims: list[Claim]
    conflicts: list[Conflict]
    clarification: Clarification | None
    fallback_reason: Literal["no_support", "weak_evidence", "failed_verification"] | None


class Check(Contract):
    target_type: Literal["claim", "conflict"]
    target_id: str
    quote_valid: bool
    verdict: Literal["supported", "unsupported", "unclear"]
    reason: str


class Verification(Contract):
    passed: bool
    evidence_strength: Literal["strong", "limited", "insufficient"]
    checks: list[Check]


class SearchResult(Contract):
    index_revision: int = Field(ge=0)
    hits: list[Hit] = Field(max_length=6)
    warnings: list[str]


class QueryInput(Contract):
    question: str = Field(min_length=1, max_length=2000)
    context: Scope

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ToolError(Contract):
    code: ErrorCode
    message: str
    retryable: bool


T = TypeVar("T")


class Envelope(Contract, Generic[T]):
    ok: bool
    request_id: str
    data: T | None
    error: ToolError | None


class Upload(Contract):
    filename: str = Field(min_length=1)
    content_base64: str
    metadata: Metadata


class IngestInput(Contract):
    documents: list[Upload] = Field(min_length=1, max_length=20)


class IngestItem(Contract):
    filename: str
    state: Literal["ready", "duplicate", "rejected"]
    document_id: str | None
    passage_count: int = Field(ge=0)
    error: ToolError | None


class IngestResult(Contract):
    index_revision: int = Field(ge=0)
    results: list[IngestItem]


class SourcesInput(Contract):
    document_id: str | None


class SourcesResult(Contract):
    documents: list[Document]
    passages: list[Passage]


class DraftInput(Contract):
    query: QueryInput
    retrieval: SearchResult


class VerifyInput(Contract):
    query: QueryInput
    retrieval: SearchResult
    draft: Draft


class TraceStep(Contract):
    step: Literal["retrieve", "draft", "verify"]
    status: Literal["ok", "skipped", "error"]
    duration_ms: int = Field(ge=0)


class QueryResult(Contract):
    mode: Literal["mock", "live"]
    result: Draft
    retrieval: SearchResult
    verification: Verification
    trace: list[TraceStep]


class Health(Contract):
    mode: Literal["mock", "live"]
    ready: bool
    ollama_available: bool
    generation_model: str
    embedding_model: str
    index_revision: int = Field(ge=0)
    document_count: int = Field(ge=0)


class EmbeddingInput(Contract):
    texts: list[str]
    kind: Literal["query", "document"]


class EmbeddingOutput(Contract):
    model: str
    model_digest: str
    dimensions: int = Field(ge=1)
    vectors: list[list[float]]


class GenerationMessage(Contract):
    role: Literal["system", "user"]
    content: str


class GenerationInput(Contract):
    messages: list[GenerationMessage]
    response_schema: dict[str, object]


class GenerationOutput(Contract):
    model: str
    model_digest: str
    content: dict[str, object]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
