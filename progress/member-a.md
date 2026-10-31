# Person A progress

- Role: frontend.
- Completed: HTTP-backed Streamlit chat and supporting-evidence display; A1 upload
  controls and source browsing through the frozen API.
- A1 uploads: PDF/HTML/Markdown/TXT, in-memory base64 payloads with all required
  metadata keys, explicit submission, and 20-file / 10 MB per-file / 50 MB batch
  checks. Each ready/duplicate/rejected result is shown separately. Mock
  NOT_IMPLEMENTED rejections are never described as successful indexing.
- A1 sources: refresh the document list, select by document ID, and open exact
  passages with source/passage IDs, headings, and PDF pages when present.
  Synthetic sources, empty results, and request errors are explicit. A rerun
  does not resubmit uploads or source requests; switching sources hides stale
  passages. README includes A1 usage.
- Scope: A2–A5 remain pending; existing context/chat code is unchanged apart
  from mounting the A1 document controls. No backend, contract, or dependency
  files changed.
- Blockers: none recorded.
- Verification (2026-10-31, Python 3.13.13, pinned requirements):
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
