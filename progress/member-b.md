# Person B progress

- Role: chunking, including ingestion and source preparation.
- Branch: `feat/chunking-phase-2`, isolated worktree from `27ea885`.
- Scope: phase 2 (B2) only. Phase 3 has not started.
- Completed: internal, in-memory parsers for PDF, HTML/HTM, Markdown/MD, and TXT.
  PDF retains original 1-based page numbers; HTML/Markdown retain heading paths;
  text formats retain inclusive source line ranges. Markdown/TXT preserve source
  spelling and whitespace apart from BOM/newline normalization. HTML preserves
  static text and PDF preserves extracted text; neither invents headings/pages.
- Failures: existing error codes for unsupported, empty, invalidly encoded,
  corrupt, encrypted, and oversized inputs. Parser-local limits: 10 MiB/file and
  100 PDF pages. No partial result after a failed PDF page. Blank pages warn
  without renumbering subsequent pages; image-only PDFs need OCR.
- Dependencies: user approved shared dependency edits for this phase. Added
  pypdf 6.21.4, markdown-it-py 4.2.0, and transitive mdurl 0.1.2 to the lock;
  declared the two direct parser dependencies in `pyproject.toml`.
- Verification (Python 3.13): 49 tests passed (48 parser cases plus the existing
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
- Next: B1 public-source curation remains pending. B3 chunking/overlap/stable IDs,
  B4 batch failure reporting/indexing handoff, and B5 deduplication/label handoff
  remain unimplemented. The public tools still return the original mock data;
  uploads are never reported as indexed. No frozen contracts were changed.
