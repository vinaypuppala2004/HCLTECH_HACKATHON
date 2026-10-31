# Phase 2 study checklist

Start with `parsers.py`, then `tests/ingestion/test_parsers.py` from the repository
root. These implement B2: parsing only. The app's upload/indexing tools still use
the mock implementation. Phase 3 adds passage construction separately.

| Topic | What to understand | Code to read |
|---|---|---|
| Python building blocks | Functions, classes, type hints, `Literal`, optional values, tuples, and frozen dataclasses | `SourceBlock`, `ParsedDocument` |
| Bytes versus text | Why uploaded content is bytes; decoding, UTF-8/UTF-16, BOMs, and LF/CRLF normalization | `_decode_text` |
| Format dispatch | Filename suffixes, supported aliases, and selecting a parser without reading paths | `parse_document` |
| Markdown | CommonMark tokens, ATX/Setext headings, heading levels, code fences, and token line maps | `_parse_markdown`, `_push_heading` |
| HTML | Start/end/data callbacks, inline text, entities, ignored/hidden content, and preformatted text | `_HTMLSourceParser` |
| PDF | `BytesIO`, `PdfReader`, text layers versus scanned pages, original page numbers, and warnings | `_parse_pdf` |
| Citation locations | `section_path`, 1-based PDF pages and source lines, and why non-PDF pages are `None` | `SourceBlock`, `_source_lines` |
| Failure handling | Custom exceptions, existing contract error codes, empty/corrupt files, and discarding partial extraction | `DocumentParseError`, `_parse_pdf` |
| Input limits | Why file size and PDF page counts are checked | `MAX_FILE_BYTES`, `MAX_PDF_PAGES` |
| Testing | pytest assertions and parametrization, synthetic fixtures, real in-memory PDF construction, and monkeypatching failures | `tests/ingestion/test_parsers.py` |
| Team boundaries | Parser output versus public Document/Passage contracts; why parsing is not successful indexing | `README.md`, `docs/contracts.md`, ingestion `tools.py` |

Suggested reading order:

1. Trace a small TXT file through `parse_document` and `_decode_text`.
2. Explain each field in the returned `SourceBlock`.
3. Trace Markdown heading ancestry with one h1 and two h2 headings.
4. Trace HTML callbacks for `<p>Reset <b>your</b> password.</p>`.
5. Explain why an empty PDF page must not renumber later pages.
6. Run one relevant test at a time, then the full ingestion test suite.

Run from the phase-3 worktree with its pinned Python 3.13 virtual environment:

```sh
.venv/bin/python -m pytest -q tests/ingestion/test_parsers.py
.venv/bin/python -m pytest -q tests/ingestion
```

Prompt to paste into a new chat, with the repository open:

> Teach me EvidenceDesk phase 2 from
> `src/evidencedesk/ingestion/parsers.py` and
> `tests/ingestion/test_parsers.py`. Use `STUDY_PHASE_2.md` as the checklist.
> Explain one topic at a time, show a small example, then ask me a short question
> before continuing. Start with bytes versus text and the TXT parsing flow.
