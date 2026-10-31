"""B3: deterministic, located passages using the frozen Document/Passage models.

Preparation happens entirely in memory. No upload, indexing, or storage port is
called. Sizes count Unicode characters, not model tokens. Each passage is an
exact slice of one parser block, retaining its heading path and PDF page.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass

from evidencedesk.contracts.models import Document, Metadata, Passage
from evidencedesk.ingestion.parsers import (
    DocumentParseError,
    ParsedDocument,
    SourceBlock,
    parse_document,
)

MAX_DOCUMENT_PASSAGES = 500


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 1200
    overlap_chars: int = 200

    def __post_init__(self):
        if type(self.max_chars) is not int or self.max_chars < 1:
            raise ValueError("max_chars must be a positive integer.")
        if type(self.overlap_chars) is not int or not 0 <= self.overlap_chars < self.max_chars:
            raise ValueError("overlap_chars must be an integer from 0 to max_chars - 1.")


@dataclass(frozen=True)
class LocatedPassage:
    """Internal citation sidecar; offsets are 0-based, end-exclusive in a block.

    block_index is 0-based in ParsedDocument.blocks. Line ranges are inclusive
    and 1-based. HTML retains its enclosing source block's range because visible
    text offsets cannot be mapped directly to raw markup. PDF lines remain None.
    """

    passage: Passage
    block_index: int
    start_offset: int
    end_offset: int
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True)
class PreparedDocument:
    document: Document
    chunks: tuple[LocatedPassage, ...]
    warnings: tuple[str, ...]

    @property
    def passages(self) -> tuple[Passage, ...]:
        """The existing contract objects, without internal location fields."""
        return tuple(chunk.passage for chunk in self.chunks)


def prepare_document(
    filename: str,
    content: bytes,
    metadata: Metadata,
    *,
    config: ChunkingConfig | None = None,
) -> PreparedDocument:
    """Parse bytes and construct a document and passages, without indexing them.

    Document identity includes the raw-byte SHA-256, parsed format, and complete
    metadata. Renaming a file preserves IDs; changing source metadata or bytes
    creates a different identity. IDs are independent of Python's randomized hash.
    This derives identifiers only: duplicate detection remains a later phase.
    """
    parsed = parse_document(filename, content)
    metadata_snapshot = metadata.model_copy(deep=True)
    digest = hashlib.sha256(content).hexdigest()
    document_id = _stable_id(
        "doc",
        {
            "schema": "evidencedesk.document.v1",
            "sha256": digest,
            "format": parsed.format,
            "metadata": metadata_snapshot.model_dump(mode="json"),
        },
    )
    chunks = chunk_document(parsed, document_id, config=config)
    document = Document(
        document_id=document_id,
        filename=filename,
        format=parsed.format,
        metadata=metadata_snapshot,
        sha256=digest,
        passage_count=len(chunks),
    )
    return PreparedDocument(document, chunks, parsed.warnings)


def chunk_document(
    parsed: ParsedDocument,
    document_id: str,
    *,
    config: ChunkingConfig | None = None,
) -> tuple[LocatedPassage, ...]:
    """Split blocks independently; never cross a heading, page, or block boundary.

    Prefer paragraph, line, then whitespace boundaries in the later part of a
    window; otherwise split at max_chars. Adjacent windows within a block overlap
    by exactly overlap_chars. That overlap can begin within a word. Whitespace-only
    windows are omitted. Every nonwhitespace character remains covered.
    """
    if not document_id.strip():
        raise ValueError("document_id must be nonblank.")
    policy = config or ChunkingConfig()
    chunks: list[LocatedPassage] = []
    for block_index, block in enumerate(parsed.blocks):
        for start, end in _spans(block.text, policy):
            if not block.text[start:end].strip():
                continue
            if len(chunks) >= MAX_DOCUMENT_PASSAGES:
                raise DocumentParseError(
                    "BAD_INPUT",
                    "Document exceeds 500 passages; increase max_chars or reduce overlap.",
                )
            text = block.text[start:end]
            passage_id = _stable_id(
                "passage",
                {
                    "schema": "evidencedesk.passage.v1",
                    "document_id": document_id,
                    "block_index": block_index,
                    "section_path": block.section_path,
                    "page": block.page,
                    "start_offset": start,
                    "end_offset": end,
                    "text": text,
                },
            )
            passage = Passage(
                passage_id=passage_id,
                document_id=document_id,
                section_path=list(block.section_path),
                page=block.page,
                text=text,
            )
            start_line, end_line = _line_range(parsed, block, start, end)
            chunks.append(LocatedPassage(passage, block_index, start, end, start_line, end_line))
    if not chunks:
        raise DocumentParseError("EMPTY_DOCUMENT", "No nonblank passages could be constructed.")
    return tuple(chunks)


def _spans(text: str, config: ChunkingConfig) -> Iterator[tuple[int, int]]:
    start = 0
    while start < len(text):
        end = min(start + config.max_chars, len(text))
        if end < len(text):
            # A boundary must leave room for overlap AND new text, guaranteeing
            # progress even when overlap is nearly the whole chunk size.
            lower = start + max(config.overlap_chars + 1, config.max_chars // 2)
            boundary = text.rfind("\n\n", lower, end)
            if boundary >= 0:
                end = boundary + 2
            else:
                boundary = text.rfind("\n", lower, end)
                if boundary >= 0:
                    end = boundary + 1
                else:
                    for index in range(end - 1, lower - 1, -1):
                        if text[index].isspace():
                            end = index + 1
                            break
        yield start, end
        if end == len(text):
            break
        start = end - config.overlap_chars


def _line_range(
    parsed: ParsedDocument, block: SourceBlock, start: int, end: int
) -> tuple[int | None, int | None]:
    if parsed.format == "pdf":
        return None, None
    if parsed.format == "html" or block.start_line is None:
        return block.start_line, block.end_line
    return (
        block.start_line + block.text.count("\n", 0, start),
        block.start_line + block.text.count("\n", 0, end - 1),
    )


def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
