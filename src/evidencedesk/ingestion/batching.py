"""B4 upload validation and in-memory preparation; indexing is not connected.

These internal records retain either a prepared document or a per-file error in
request order. They are not additions to the frozen tool/API JSON contracts.
"""

import base64
import binascii
import logging
from dataclasses import dataclass

from evidencedesk.contracts.models import ErrorCode, IngestInput, ToolError
from evidencedesk.ingestion.chunking import ChunkingConfig, PreparedDocument, prepare_document
from evidencedesk.ingestion.parsers import MAX_FILE_BYTES, DocumentParseError

MAX_BATCH_BYTES = 50 * 1024 * 1024
MAX_BATCH_PASSAGES = 500
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedUpload:
    filename: str
    value: PreparedDocument | ToolError


@dataclass(frozen=True)
class PreparedBatch:
    uploads: tuple[PreparedUpload, ...]
    decoded_bytes: int

    @property
    def documents(self) -> tuple[PreparedDocument, ...]:
        """Only successfully prepared documents; none has been indexed."""
        return tuple(
            upload.value for upload in self.uploads if isinstance(upload.value, PreparedDocument)
        )

    @property
    def passage_count(self) -> int:
        return sum(document.document.passage_count for document in self.documents)


def prepare_uploads(request: IngestInput, *, config: ChunkingConfig | None = None) -> PreparedBatch:
    """Decode and prepare uploads independently, without writing files or an index.

    The existing IngestInput enforces 1–20 records. Decode all records before
    parsing, so an oversized batch cannot produce a partial prepared result.
    Existing per-file errors survive a batch rejection; otherwise-valid files
    get BAD_INPUT for the batch limit. No file is marked ready or duplicate.
    """
    decoded: list[bytes | ToolError] = []
    decoded_bytes = 0
    batch_error = _error(
        "BAD_INPUT", "Decoded batch exceeds the 50 MB limit; no files were prepared."
    )
    for upload in request.documents:
        try:
            content = _decode_upload(upload.content_base64)
        except DocumentParseError as exc:
            decoded.append(_error(exc.code, str(exc)))
        else:
            decoded_bytes += len(content)
            if decoded_bytes > MAX_BATCH_BYTES:
                # Release previously retained bytes once the batch is rejected,
                # while continuing to validate the remaining records separately.
                decoded = [
                    value if isinstance(value, ToolError) else batch_error for value in decoded
                ]
                decoded.append(batch_error)
            else:
                decoded.append(content)
    if decoded_bytes > MAX_BATCH_BYTES:
        return PreparedBatch(
            tuple(
                PreparedUpload(
                    upload.filename, content if isinstance(content, ToolError) else batch_error
                )
                for upload, content in zip(request.documents, decoded, strict=True)
            ),
            decoded_bytes,
        )

    results: list[PreparedUpload] = []
    for upload, content in zip(request.documents, decoded, strict=True):
        if isinstance(content, ToolError):
            results.append(PreparedUpload(upload.filename, content))
            continue
        try:
            value = prepare_document(upload.filename, content, upload.metadata, config=config)
        except DocumentParseError as exc:
            value = _error(exc.code, str(exc))
        except Exception:
            logger.exception("Unexpected error while preparing an upload.")
            value = _error("INTERNAL_ERROR", "Unexpected document preparation error.")
        results.append(PreparedUpload(upload.filename, value))
    batch = PreparedBatch(tuple(results), decoded_bytes)
    if batch.passage_count > MAX_BATCH_PASSAGES:
        error = _error(
            "BAD_INPUT", "Batch exceeds 500 passages; no files were prepared for indexing."
        )
        return PreparedBatch(
            tuple(
                PreparedUpload(
                    upload.filename, upload.value if isinstance(upload.value, ToolError) else error
                )
                for upload in batch.uploads
            ),
            decoded_bytes,
        )
    return batch


def _decode_upload(encoded: str) -> bytes:
    # A valid base64 string above this bound cannot fit the decoded file limit.
    # Check before decoding to avoid allocating an arbitrarily large byte buffer.
    if len(encoded) > 4 * ((MAX_FILE_BYTES + 2) // 3):
        raise DocumentParseError("BAD_INPUT", "Encoded file exceeds the 10 MB decoded-file limit.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentParseError(
            "BAD_INPUT", "content_base64 must be strict, padded base64."
        ) from exc
    if len(content) > MAX_FILE_BYTES:
        raise DocumentParseError("BAD_INPUT", "Decoded file exceeds the 10 MB limit.")
    return content


def _error(code: ErrorCode, message: str) -> ToolError:
    return ToolError(code=code, message=message, retryable=False)
