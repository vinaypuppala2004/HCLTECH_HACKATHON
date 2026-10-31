# Person A progress

- Role: frontend.
- Completed: HTTP-backed Streamlit chat and supporting-evidence display; A1 upload
  controls and source browsing; A2 context controls and conflict comparisons.
- A1 uploads: PDF/HTML/Markdown/TXT, in-memory base64 payloads with all required
  metadata keys, explicit submission, and 20-file / 10 MB per-file / 50 MB batch
  checks. Each ready/duplicate/rejected result is shown separately. Mock
  NOT_IMPLEMENTED rejections are never described as successful indexing.
- A1 sources: refresh the document list, select by document ID, and open exact
  passages with source/passage IDs, headings, and PDF pages when present.
  Synthetic sources, empty results, and request errors are explicit. A rerun
  does not resubmit uploads or source requests; switching sources hides stale
  passages. README includes A1 usage.
- Scope: A1 and A2 are complete; A3–A5 remain pending. A2 adds conflict rendering
  and sidebar context selection without changing the existing claim, fallback,
  or service-error presentation. No backend, contract, or dependency files changed.
- Blockers: none recorded.
- A1 verification (2026-10-31, Python 3.13.13, pinned requirements):
  - `python -m pytest -v tests/ui tests/acceptance/test_smoke.py`: 19 passed,
    including 18 A1 cases and the existing chat/HTTP/rerun smoke test.
  - `python -m ruff check .` and `python -m ruff format --check .`: passed.
  - Started temporary FastAPI and Streamlit servers, checked both health
    endpoints, listed/read sources, and confirmed upload rejection over real
    local HTTP; both servers stopped after the check.
- Limitations: live ingestion/indexing is still owned by B/D and unimplemented;
  ready/duplicate responses and PDF pages were verified with synthetic test
  responses. Streamlit's test API does not upload files, so upload UI tests
  supply in-memory file objects to the picker while exercising the real form
  submission and API. The pinned Starlette/httpx combination emits one
  deprecation warning. Integration tests required an approved run outside the
  sandbox after the sandboxed run stalled.
- A2 controls: product/version/environment inputs have stable keys and help;
  whitespace is trimmed, blanks remain explicit nulls, and version spelling is
  preserved. Each conflict side offers Use this context to populate the next
  query's controls. This action sends no request and changes no resolution.
- A2 comparisons: both conflict kinds render two sides per row, with exact quotes,
  passage/source IDs, product/version/environment, origin, location, API
  applicability, and backend selection markers. Unresolved conflicts remain
  visible. Missing source metadata retains the quote without inventing details.
  Controls have unique keys across multiple conflicts and historical replies.
- A2 verification (2026-10-31, Python 3.13.13, unchanged pinned requirements):
  - `python -m pytest -q -o faulthandler_timeout=30`: 33 passed (14 A2 cases,
    18 A1 cases, and the existing acceptance smoke test); one pre-existing
    Starlette/httpx deprecation warning. Ran outside the sandbox, as required
    by the integration-test limitation recorded above.
  - `python -m ruff check .`, `python -m ruff format --check .`, and
    `git diff --check`: passed.
  - Temporary FastAPI and Streamlit servers started successfully. Both health
    endpoints and a scoped query passed over real local HTTP; processes stopped
    after the check.
- A2 limitation: the current mock ignores context and produces no conflicts.
  Conflict behavior was verified with explicitly synthetic, contract-valid
  responses in mock/live modes, without claiming live retrieval or resolution.
