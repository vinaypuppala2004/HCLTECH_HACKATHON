# Source parsing, chunking, and upload validation

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
Phase 4 adds opt-in batch validation and per-file errors. Indexing integration
and deduplication remain pending. No file is reported as indexed by these parsers.

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

## Phase 4: validation portion; indexing connection pending

`prepare_uploads(IngestInput(...), config=...)` in `batching.py` decodes and
prepares uploads using phases 2–3. It returns an internal `PreparedBatch` with
one `PreparedUpload` per input record, in original order. Each upload contains
either a `PreparedDocument` or an existing-contract `ToolError`.
`batch.documents` selects only successfully prepared documents; these are in
memory and have never been indexed. Parser warnings and citation locations remain
available in each prepared document.

- Input uses the unchanged `IngestInput` and `Upload` models; they enforce
  1–20 files. Base64 must be ASCII, padded when required, and contain no whitespace
  or data-URL prefix. Decoding is strict; invalid bytes are not repaired.
- The decoded per-file limit is 10 MiB, checked by encoded length before allocating
  the byte buffer and by exact decoded size afterward. Empty, unsupported,
  invalidly encoded, corrupt, and encrypted files retain their parser errors.
  Unexpected preparation errors become generic per-file `INTERNAL_ERROR` records;
  the remaining files continue independently.
- The decoded batch limit is 50 MiB. If exceeded, parsing never starts and every
  otherwise-valid file gets `BAD_INPUT`. Individual decoding errors are retained.
  Earlier decoded buffers are released once the limit is crossed. The byte total
  counts all successfully decoded files within the per-file limit, even if a later
  parser would reject a file's format or text.
- The prepared batch limit is 500 passages. Overflow discards prepared results
  for all otherwise-valid files and reports `BAD_INPUT`; existing per-file errors
  are retained. The cumulative corpus limit still requires C's index state.
- Duplicate filenames and repeated bytes remain separate records. No duplicate
  detection or `duplicate` result is implemented in this phase.

`validate_documents` in `tools.py` implements the existing `IngestTool` signature
and returns per-file results in a successful `Envelope[IngestResult]`. Invalid
files report the validation error. Files that pass validation are still
`rejected` / `NOT_IMPLEMENTED`: the indexing port is not connected. All results
have `document_id=None` and `passage_count=0`, with `index_revision=0`. A prepared
document is never described as ready or indexed merely because parsing succeeded.
Batch rejections remain HTTP 200 when this tool is injected into D's existing API.

The default factory still uses the unchanged mock `ingest_documents` and
`read_sources`; default API behavior remains explicitly mocked. D can inspect or
inject the validation tool through the existing tool bundle. No API/core files
or shared contracts were edited. C's branch and main currently define no
index-writing port. At the user's direction, that connection remains pending
rather than inventing a signature or silently substituting a fake index.

The remaining handoff is concrete: C needs an agreed indexing operation that
accepts these existing Document/Passage records and reports actual committed
revision/success/failure; D owns lifecycle and API wiring. The batch records are
internal preparation output, not an agreed indexing contract. B4 stays unchecked
until that integration is implemented and tested. B5 is not started.

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
For phase 3's changed files, learning topics, exercises, and new-chat prompt, see
[STUDY_PHASE_3.md](STUDY_PHASE_3.md).
