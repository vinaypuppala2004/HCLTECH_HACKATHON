# Phase 2: source parsing

`parse_document(filename, content)` in `parsers.py` accepts file bytes and returns
an internal `ParsedDocument` with immutable `SourceBlock` records. It does not
read paths, fetch URLs, save uploads, create passage IDs, apply chunk sizes or
overlap, or index documents. The frozen API and existing mock tools are unchanged.

```python
from evidencedesk.ingestion.parsers import parse_document

parsed = parse_document("synthetic.md", b"# Setup\n\nUse the Reset control.\n")
for block in parsed.blocks:
    print(block.section_path, block.page, block.start_line, block.end_line, block.text)
```

| Format | Text and location behavior |
|---|---|
| PDF | One extracted block per nonempty page; original 1-based page numbers; no inferred heading hierarchy or source lines. |
| HTML / HTM | Static decoded text with h1–h6 ancestry and inclusive source line ranges; inline text stays joined, normal whitespace collapses, preformatted text keeps internal whitespace. |
| Markdown / MD | CommonMark heading ancestry, including Setext headings; source sections and inclusive line ranges preserve Markdown markup, lists, and code. Headings inside code or nested containers do not change the document heading path. |
| TXT | One complete source block with inclusive line range; no invented headings. |

Text inputs accept strict UTF-8 (optional BOM) and BOM-marked UTF-16. BOMs are
removed and CRLF/CR normalize to LF. Non-PDF `page` values are always `None`.
HTML ignores comments, head/script/style/template/noscript content, and explicitly
hidden subtrees. HTML is parsed with the standard library's tolerant HTML parser;
CSS visibility, JavaScript rendering, and browser layout are outside this phase.
HTML and PDF quotes must be taken from extracted text, not raw markup or bytes.

`DocumentParseError.code` uses existing contract codes: `UNSUPPORTED_FORMAT`,
`EMPTY_DOCUMENT`, or `BAD_INPUT`. Parser-local limits are 10 MiB decoded per file
and 100 PDF pages. Corrupt/encrypted PDFs fail explicitly, and a failed page
discards the whole parse result. Blank/image-only PDF pages produce warnings
without renumbering later pages; a PDF with no extractable text fails. OCR is not
implemented. PDF reading uses strict mode, so malformed PDFs may need repair
outside this parser. Heading paths in PDFs are deliberately empty.

Phase 3 will turn these structural units into passages with stable IDs and
overlap. Batch upload validation, per-file API errors, indexing, and deduplication
remain later-phase work. No file is reported as indexed by these parsers.

Verification from the repository root with the pinned Python 3.13 environment:

```sh
.venv/bin/python -m pytest -q tests/ingestion
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Tests generate explicitly synthetic source text and real PDFs in memory; no
public corpus, network access, external model, or stored upload is required.

Parser references: [pypdf text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
and [markdown-it-py token maps](https://markdown-it-py.readthedocs.io/en/latest/using.html).
