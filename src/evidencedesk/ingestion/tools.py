"""Ingestion stubs: uploads are explicitly not persisted or indexed."""

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
