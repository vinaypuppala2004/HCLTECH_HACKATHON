# Person B progress

- Role: chunking, including ingestion and source preparation.
- Branch: `feat/chunking-phase-3`, isolated worktree rebased onto main at `b73c1ea`.
- Scope: phase 3 (B3), after phase 2 was merged in PR #4. Phase 4 is not started.
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
- Next: B1 public-source curation, B4 batch failure reporting/indexing handoff,
  and B5 deduplication/label handoff remain unimplemented. The public tools still
  return mock data; uploads are never reported as indexed.
