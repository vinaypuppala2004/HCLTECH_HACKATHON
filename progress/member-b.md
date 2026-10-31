# Person B progress

- Role: chunking, including ingestion and source preparation.
- Branch: `feat/chunking-phase-4`, isolated worktree rebased onto main at `91067d6`.
- Scope: phase 4 validation portion, after phase 3 was merged in PR #8. The user
  explicitly selected "Finish validation; keep indexing pending" because neither
  main nor C's branch defined an indexing port. B4 is not marked complete; B5 is
  not started. No indexing contract was invented or changed.
- Completed: internal, in-memory parsers for PDF, HTML/HTM, Markdown/MD, and TXT.
  PDF retains original 1-based page numbers; HTML/Markdown retain heading paths;
  text formats retain inclusive source line ranges. Markdown/TXT preserve source
  spelling and whitespace apart from BOM/newline normalization. HTML preserves
  static text and PDF preserves extracted text; neither invents headings/pages.
- Failures: existing error codes for unsupported, empty, invalidly encoded,
  corrupt, encrypted, and oversized inputs. Parser-local limits: 10 MiB/file and
  100 PDF pages. No partial result after a failed PDF page. Blank pages warn
  without renumbering subsequent pages; image-only PDFs need OCR.
- Phase 2 dependencies: user approved shared dependency edits for phase 2. Added
  pypdf 6.21.4, markdown-it-py 4.2.0, and transitive mdurl 0.1.2 to the lock;
  declared the two direct parser dependencies in `pyproject.toml`.
- Phase 2 verification (Python 3.13): 49 tests passed (48 parser cases plus the existing
  API/Streamlit smoke test). `ruff check .`, `ruff format --check .`,
  `git diff --check`, installation from the updated lock, and `pip check` passed.
  Temporary FastAPI and Streamlit processes started on localhost; their health
  endpoints and an HTTP query with exact evidence quotes passed. Both processes
  were stopped afterward. The suite reports one dependency deprecation warning
  from Starlette's existing httpx test-client integration; no dependency changes
  outside the approved parser additions were made.
- Limitations: no OCR, JavaScript rendering, CSS visibility evaluation, or PDF
  heading inference. Text accepts UTF-8 or BOM-marked UTF-16. Strict PDF reading
  rejects malformed files rather than repairing them. See ingestion/README.md.
- Phase 3 implementation: `prepare_document` constructs the existing Document
  and Passage contract objects entirely in memory. `chunk_document` keeps each
  source block's heading/page and exact source slices; size defaults to 1,200
  Unicode characters and overlap to 200. It prefers paragraph/line/whitespace
  boundaries, falling back to hard splits for long unbroken text. No overlap
  crosses source blocks; short HTML blocks remain short.
- Source identity: SHA-256 over raw bytes, parsed format, and complete metadata;
  filenames are excluded. Passage identities include document identity, source
  block, heading/page, exact offsets, and text. Repeated input is stable across
  processes; versions, source identities, and repeated blocks stay distinguishable.
  This is identifier derivation only, not duplicate detection or indexing.
- Citation locations: internal sidecars retain block index and character offsets.
  Markdown/TXT have precise source line ranges; HTML retains the enclosing source
  block's range; PDF keeps original page numbers without fabricated line numbers.
  No extra fields were added to shared contracts. Parser warnings are retained.
- Phase 3 limits: maximum 500 passages per document, rejecting the whole result
  on overflow. The cumulative corpus limit remains an indexing integration task.
  Character sizes are not model-token guarantees or measured quality settings;
  exact character overlap may begin within a word. No new dependencies were added.
- Study handoff: `src/evidencedesk/ingestion/STUDY_PHASE_2.md` lists phase 2 topics,
  a reading order, test commands, and a prompt to reuse in a new chat.
- Phase 3 verification (Python 3.13): 47 new chunking cases and 267 full-suite
  tests passed after integrating the newer team merges through `b73c1ea`.
  Lint, formatting, dependency consistency, and whitespace checks
  passed. Temporary FastAPI/Streamlit processes started; health endpoints and an
  HTTP query with exact evidence quotes passed, and the processes were stopped.
  The existing Starlette/httpx test-client deprecation warning remains.
- Phase 4 validation: `batching.py` decodes strict base64 and prepares each file
  through phases 2–3. Internal results preserve request order and retain either
  a prepared Document/Passage set or an existing-contract ToolError. Failed files
  are excluded from prepared documents. Empty/corrupt/unsupported files retain
  explicit errors; an unexpected file failure becomes a generic INTERNAL_ERROR
  and does not stop later files. No uploads or index state are persisted.
- Phase 4 limits: encoded-length precheck and exact decoded 10 MiB/file check;
  50 MiB decoded/batch before parsing; 500 prepared passages/batch. Batch overflow
  discards otherwise-valid results and preserves existing per-file errors. Corpus
  capacity still requires C's actual index state. Repeated inputs are not deduplicated.
- Phase 4 tool: `validate_documents` fits the frozen IngestTool signature and
  reports per-file rejected results in a successful envelope. Valid files still
  return NOT_IMPLEMENTED; all results have null document IDs, zero passage counts,
  and revision zero. Default mock tools/factory behavior is preserved. An owned
  test injects the tool into the existing API, verifies HTTP 200 per-file errors,
  unchanged health/source state, and absence of falsely indexed documents.
- Study handoff: `STUDY_PHASE_3.md` lists the six phase-3 files, core concepts,
  exercises, commands, and a reusable new-chat prompt.
- Phase 4 verification (Python 3.13): 33 new validation tests and 314 full-suite
  tests passed after integrating team merges through `91067d6`.
  Lint, formatting, dependency consistency, and whitespace checks
  passed. FastAPI/Streamlit startup, health, and an HTTP query with exact evidence
  quotes passed; temporary processes were stopped. The existing Starlette/httpx
  test-client deprecation warning remains. No shared contracts/dependencies or
  other owners' implementation files were edited.
- Next: C must define/provide the agreed index-writing operation; B can then
  connect prepared records, and D owns lifecycle/API wiring. B1 source curation,
  the remaining B4 indexing work, and B5 deduplication/label handoff are pending.

## Live completion integration — 2026-10-31

- B1/B4/B5 application work completed: curated 16-source provenance/license inventory;
  validated uploads call the actual index and return committed per-file receipts.
- Renamed files with identical content/metadata deduplicate; versions stay distinct.
- Layout-aware PDF extraction preserves emphasized text order. Live HTML grouping
  stays within headings; live chunks are 4,096/200. Model length rejection retries
  that file at 1,800/200 without truncation or a different embedding model.
- All 16 public corpus files imported: 420 committed passages. The RFC rejected
  at the first size succeeded at the compact size; earlier files were duplicates
  on rerun. Invalid files never appeared ready. The 500-passage limit is unchanged.
- Runtime `var/corpus-import.json` maps source hashes to actual document/passage IDs,
  pages, headings, raw-source lines and extracted-block offsets; compact IDs were
  checked against source-read results. No raw source files/runtime storage committed.
- Full integration suite: 472 tests passed; lint, format, dependency checks passed.
