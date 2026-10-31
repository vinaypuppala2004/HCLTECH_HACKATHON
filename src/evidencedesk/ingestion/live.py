"""Connect validated uploads to the backend's single committed index."""

import logging

from evidencedesk.contracts.models import Envelope, IngestInput, IngestItem, IngestResult, ToolError
from evidencedesk.core.responses import success
from evidencedesk.ingestion.batching import prepare_uploads
from evidencedesk.ingestion.chunking import COMPACT_CHUNKING, LIVE_CHUNKING
from evidencedesk.retrieval.index import QdrantIndex

logger = logging.getLogger(__name__)


class LiveIngestion:
    def __init__(self, index: QdrantIndex):
        self.index = index

    def __call__(self, request: IngestInput) -> Envelope[IngestResult]:
        results = []
        batch = prepare_uploads(request, config=LIVE_CHUNKING)
        for original, upload in zip(request.documents, batch.uploads, strict=True):
            value = upload.value
            if isinstance(value, ToolError):
                error = value
            else:
                try:
                    receipt = self.index.index_document(value.document, value.passages)
                    if (
                        not receipt.ok
                        and receipt.error is not None
                        and receipt.error.code == "BAD_INPUT"
                        and receipt.error.message
                        == "Ollama rejected the embedding input; check text length."
                    ):
                        # Some code/ASCII-heavy passages exceed Nomic's token context.
                        # Rechunk the whole file deterministically; never truncate evidence.
                        logger.info("Retrying document with the compact chunking profile.")
                        retry = (
                            prepare_uploads(
                                IngestInput(documents=[original]), config=COMPACT_CHUNKING
                            )
                            .uploads[0]
                            .value
                        )
                        if isinstance(retry, ToolError):
                            error = retry
                            receipt = None
                        else:
                            receipt = self.index.index_document(retry.document, retry.passages)
                    if receipt is None:
                        results.append(
                            IngestItem(
                                filename=upload.filename,
                                state="rejected",
                                document_id=None,
                                passage_count=0,
                                error=error,
                            )
                        )
                        continue
                    if receipt.ok and receipt.data is not None:
                        item = receipt.data.results[0].model_copy(
                            update={"filename": upload.filename}
                        )
                        results.append(item)
                        continue
                    error = receipt.error
                except Exception:
                    logger.exception("Document indexing failed.")
                    error = ToolError(
                        code="INTERNAL_ERROR", message="Document indexing failed.", retryable=False
                    )
            results.append(
                IngestItem(
                    filename=upload.filename,
                    state="rejected",
                    document_id=None,
                    passage_count=0,
                    error=error,
                )
            )
        return success(IngestResult(index_revision=self.index.index_revision, results=results))
