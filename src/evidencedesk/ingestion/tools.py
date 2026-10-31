"""Mock tools and opt-in upload validation; neither persists or indexes uploads."""

from evidencedesk.contracts.models import (
    Envelope,
    IngestInput,
    IngestItem,
    IngestResult,
    SourcesInput,
    SourcesResult,
    ToolError,
)
from evidencedesk.core.responses import failure, success
from evidencedesk.ingestion.batching import prepare_uploads
from evidencedesk.mocks.fixtures import mock_hit


def ingest_documents(request: IngestInput) -> Envelope[IngestResult]:
    return success(
        IngestResult(
            index_revision=1,
            results=[
                IngestItem(
                    filename=document.filename,
                    state="rejected",
                    document_id=None,
                    passage_count=0,
                    error=ToolError(
                        code="NOT_IMPLEMENTED",
                        message="Mock ingestion does not parse, save, or index uploads.",
                        retryable=False,
                    ),
                )
                for document in request.documents
            ],
        )
    )


def read_sources(request: SourcesInput) -> Envelope[SourcesResult]:
    hit = mock_hit()
    if request.document_id not in (None, hit.document.document_id):
        return failure("NOT_FOUND", "The requested mock document does not exist.")
    return success(
        SourcesResult(
            documents=[hit.document],
            passages=[hit.passage] if request.document_id else [],
        )
    )


def validate_documents(request: IngestInput) -> Envelope[IngestResult]:
    """An opt-in IngestTool implementation for B4 validation, without an index.

    Invalid files retain their preparation error. Valid files are rejected with
    NOT_IMPLEMENTED until C provides the agreed indexing port. Index revision is
    zero, and no rejected file is assigned an indexed ID or passage count. The
    default mock factory continues to use ingest_documents above.
    """
    batch = prepare_uploads(request)
    return success(
        IngestResult(
            index_revision=0,
            results=[
                IngestItem(
                    filename=upload.filename,
                    state="rejected",
                    document_id=None,
                    passage_count=0,
                    error=(
                        upload.value
                        if isinstance(upload.value, ToolError)
                        else ToolError(
                            code="NOT_IMPLEMENTED",
                            message="Validated and chunked; indexing port is not connected. "
                            "Nothing was indexed.",
                            retryable=False,
                        )
                    ),
                )
                for upload in batch.uploads
            ],
        )
    )
