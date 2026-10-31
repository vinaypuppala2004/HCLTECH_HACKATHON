# Source parsing and chunking

## Phase 2: source parsing

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

Phase 3's passage builder consumes these structural units, as described below.
Batch upload validation, per-file API errors, indexing, and deduplication remain
later-phase work. No file is reported as indexed by these parsers.

## Phase 3: passage construction

`prepare_document(filename, content, metadata, config=...)` in `chunking.py`
parses bytes and returns a `PreparedDocument`. Its `document` and `passages` use
the existing frozen JSON shapes. Its `chunks` retain internal location records;
its `warnings` retain parser warnings. None of these records are persisted or
indexed, and no public API or mock tool is replaced.

```python
from evidencedesk.contracts.models import Metadata
from evidencedesk.ingestion.chunking import ChunkingConfig, prepare_document

metadata = Metadata(
    title="Synthetic setup guide",
    source_url=None,
    product=None,
    version=None,
    environment=None,
    family_id=None,
    published_at=None,
    origin="synthetic",
)
prepared = prepare_document(
    "synthetic.md",
    b"# Setup\n\nUse the Reset control.\n",
    metadata,
    config=ChunkingConfig(max_chars=1200, overlap_chars=200),
)
print(prepared.document.document_id, prepared.document.passage_count)
for chunk in prepared.chunks:
    print(chunk.passage.model_dump())
    print(chunk.block_index, chunk.start_offset, chunk.end_offset)
    print(chunk.start_line, chunk.end_line)
```

`chunk_document(parsed, document_id, config=...)` can also consume an existing
`ParsedDocument`. Chunking follows these rules:

- Defaults: at most 1,200 Unicode characters with 200 characters of overlap.
  These are character limits, not embedding-token budgets or measured tuning.
  `max_chars` must be a positive integer; `overlap_chars` must be an integer
  between zero and `max_chars - 1`.
- Every passage is an exact slice of one parser block. Blocks are never joined,
  even when their headings match. This preserves source boundaries and can yield
  short passages for HTML headings/paragraphs. PDF passages never cross pages;
  Markdown passages never cross heading sections. Heading paths remain metadata
  and are not prepended to the evidence text.
- Split near the end of a size window, preferring paragraph breaks, line breaks,
  and then whitespace. Long unbroken text is split at the character limit.
  Consecutive windows within a block overlap by exactly `overlap_chars`; the
  next window may therefore begin inside a word. No overlap crosses blocks.
  Whitespace-only windows are omitted; all nonwhitespace source text stays covered.
- Each internal `LocatedPassage` stores its 0-based block index and end-exclusive
  character offsets. Markdown/TXT get precise inclusive source line ranges.
  HTML keeps the enclosing block's source line range because markup-to-visible
  text conversion does not provide exact per-character source lines. PDF lines
  remain `None`. These sidecars add no fields to the shared Passage contract.
- A document exceeding 500 passages fails with `BAD_INPUT`, with no partial
  return. This is a per-document guard; enforcing the cumulative 500-passage
  corpus limit belongs to later indexing integration.

Document IDs are SHA-256 identifiers over a versioned canonical JSON identity:
raw-byte hash, parsed format, and complete metadata. Renaming a file or switching
equivalent extensions (e.g. MD to Markdown) preserves IDs. A raw byte, source URL,
product, version, environment, title, family, date, or origin change creates a new
identity. Changing chunk settings retains document identity. Passage IDs include
document ID, heading/page, block index, exact offsets, and text under a versioned
namespace; repeated identical blocks remain distinct. Reprocessing the same
input/settings is deterministic across Python processes. No duplicate detection
or storage is implied by deriving these IDs.

## Verification and study

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

For phase 2's learning checklist and a prompt to reuse in a new chat, see
[STUDY_PHASE_2.md](STUDY_PHASE_2.md).
