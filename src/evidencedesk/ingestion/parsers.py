"""Phase B2: extract located source blocks, without chunking, saving, or indexing.

These records are internal to ingestion, not additions to the frozen JSON API.
Markdown/TXT retain source spelling and whitespace (apart from newline/BOM
normalization). HTML returns decoded visible text; PDF returns extracted text.
Line ranges are inclusive and 1-based in the decoded source, not rendered lines.
"""

import codecs
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from typing import Literal

from markdown_it import MarkdownIt
from pypdf import PdfReader

from evidencedesk.contracts.models import ErrorCode

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
DocumentFormat = Literal["pdf", "html", "markdown", "txt"]
_FORMATS: dict[str, DocumentFormat] = {
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "txt",
}


@dataclass(frozen=True)
class SourceBlock:
    """An extracted structural unit; no chunk-size or overlap policy is applied."""

    text: str
    section_path: tuple[str, ...] = ()
    page: int | None = None
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    format: DocumentFormat
    blocks: tuple[SourceBlock, ...]
    warnings: tuple[str, ...] = ()


class DocumentParseError(ValueError):
    """A parser failure with an existing contract code, for later ingestion wiring."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


def parse_document(filename: str, content: bytes) -> ParsedDocument:
    """Parse decoded upload bytes in memory. Never read a path or fetch a URL.

    Text encodings: UTF-8 (with optional BOM), or UTF-16 with a BOM. Other
    encodings must be converted by the caller; invalid bytes are never replaced.
    PDF has no OCR or inferred headings. Non-PDF page numbers stay None.
    """
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if suffix not in _FORMATS:
        raise DocumentParseError("UNSUPPORTED_FORMAT", "Use PDF, HTML, Markdown, or TXT.")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentParseError("BAD_INPUT", "The decoded file exceeds the 10 MB limit.")
    if not content:
        raise DocumentParseError("EMPTY_DOCUMENT", "The document is empty.")
    document_format = _FORMATS[suffix]
    warnings: tuple[str, ...] = ()
    if document_format == "pdf":
        blocks, warnings = _parse_pdf(content)
    else:
        text = _decode_text(content)
        if document_format == "html":
            parser = _HTMLSourceParser()
            parser.feed(text)
            parser.close()
            blocks = tuple(parser.blocks)
        elif document_format == "markdown":
            blocks = _parse_markdown(text)
        else:
            blocks = (SourceBlock(text, start_line=1, end_line=len(_source_lines(text))),)
    if not blocks or not any(block.text.strip() for block in blocks):
        raise DocumentParseError(
            "EMPTY_DOCUMENT", "No extractable text was found; scanned PDFs require OCR."
        )
    return ParsedDocument(filename, document_format, blocks, warnings)


def _decode_text(content: bytes) -> str:
    encoding = (
        "utf-16" if content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
    )
    try:
        text = content.decode(encoding)
    except UnicodeError as exc:
        raise DocumentParseError("BAD_INPUT", "Text must be UTF-8 or BOM-marked UTF-16.") from exc
    if "\x00" in text:
        raise DocumentParseError("BAD_INPUT", "Text contains NUL bytes; check the file encoding.")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _push_heading(headings: list[tuple[int, str]], level: int, title: str) -> tuple[str, ...]:
    while headings and headings[-1][0] >= level:
        headings.pop()
    headings.append((level, title))
    return tuple(title for _, title in headings)


def _source_lines(text: str) -> list[str]:
    # Match CommonMark's LF boundaries after normalization. str.splitlines()
    # also splits Unicode separators/form feeds, which would shift token maps.
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])


def _parse_markdown(text: str) -> tuple[SourceBlock, ...]:
    # CommonMark tokens distinguish headings from fenced/indented code. Keep
    # source slices, including lists and code, so parsing does not rewrite quotes.
    lines = _source_lines(text)
    blocks: list[SourceBlock] = []
    headings: list[tuple[int, str]] = []
    section_path: tuple[str, ...] = ()
    start = 0
    tokens = MarkdownIt("commonmark").parse(text)
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0 or token.map is None:
            continue
        heading_start, _ = token.map
        if heading_start > start and "".join(lines[start:heading_start]).strip():
            blocks.append(
                SourceBlock(
                    "".join(lines[start:heading_start]),
                    section_path,
                    start_line=start + 1,
                    end_line=heading_start,
                )
            )
        inline = tokens[index + 1]
        # Strip presentation markup from the path only, not the source text.
        title = "".join(
            child.content
            for child in inline.children or []
            if child.type in {"text", "code_inline", "image"}
        ).strip()
        section_path = _push_heading(headings, int(token.tag[1]), title or inline.content)
        start = heading_start
    if "".join(lines[start:]).strip():
        blocks.append(
            SourceBlock(
                "".join(lines[start:]), section_path, start_line=start + 1, end_line=len(lines)
            )
        )
    return tuple(blocks)


def _parse_pdf(content: bytes) -> tuple[tuple[SourceBlock, ...], tuple[str, ...]]:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise DocumentParseError("BAD_INPUT", "Encrypted PDFs are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentParseError("BAD_INPUT", "PDF exceeds the 100-page limit.")
        blocks: list[SourceBlock] = []
        warnings: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text.strip():
                blocks.append(SourceBlock(text, page=page_number))
            else:
                warnings.append(
                    f"Page {page_number} has no extractable text; OCR is not supported."
                )
    except DocumentParseError:
        raise
    except Exception as exc:
        # pypdf can surface different exception types for damaged streams/fonts.
        # Discard all extracted pages if any page fails; never return partial success.
        raise DocumentParseError(
            "BAD_INPUT", "PDF could not be read or contains corrupt data."
        ) from exc
    return tuple(blocks), tuple(warnings)


class _HTMLSourceParser(HTMLParser):
    """Extract static HTML text and h1–h6 ancestry, without executing scripts."""

    _IGNORED = {"head", "script", "style", "template", "noscript"}
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "wbr"}
    _BLOCK = {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[SourceBlock] = []
        self._parts: list[str] = []
        self._headings: list[tuple[int, str]] = []
        self._ignored: list[str] = []
        self._heading_level: int | None = None
        self._start_line: int | None = None
        self._end_line: int | None = None
        self._pre = False

    def _flush(self):
        raw = "".join(self._parts)
        text = raw.strip() if self._pre else " ".join(raw.split())
        if self._heading_level is not None:
            if text:
                _push_heading(self._headings, self._heading_level, text)
            self._heading_level = None
        if text:
            self.blocks.append(
                SourceBlock(
                    text,
                    tuple(title for _, title in self._headings),
                    start_line=self._start_line,
                    end_line=self._end_line,
                )
            )
        self._parts = []
        self._start_line = self._end_line = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        if self._ignored:
            if tag not in self._VOID:
                self._ignored.append(tag)
            return
        if (
            tag in self._IGNORED
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
        ):
            if tag not in self._VOID:
                self._ignored.append(tag)
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self._heading_level = int(tag[1])
        elif tag in self._BLOCK:
            self._flush()
        if tag == "pre":
            self._pre = True
        if tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        if self._ignored:
            if tag in self._ignored:
                reverse_index = self._ignored[::-1].index(tag)
                del self._ignored[len(self._ignored) - reverse_index - 1 :]
            return
        if tag in self._BLOCK or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
        if tag == "pre":
            self._pre = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str):
        if self._ignored:
            return
        line = self.getpos()[0]
        if self._start_line is None:
            self._start_line = line
        self._end_line = line + data.count("\n")
        self._parts.append(data)

    def close(self):
        super().close()
        self._flush()
