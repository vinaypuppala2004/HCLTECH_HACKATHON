# Person A progress

- Role: frontend.
- Completed: HTTP-backed Streamlit chat and supporting-evidence display; A1 upload
  controls and source browsing; A2 context controls and conflict comparisons;
  A3 claim citations, fallback states, and query service errors; A4 session history
  and submission handling across reruns.
- A1 uploads: PDF/HTML/Markdown/TXT, in-memory base64 payloads with all required
  metadata keys, explicit submission, and 20-file / 10 MB per-file / 50 MB batch
  checks. Each ready/duplicate/rejected result is shown separately. Mock
  NOT_IMPLEMENTED rejections are never described as successful indexing.
- A1 sources: refresh the document list, select by document ID, and open exact
  passages with source/passage IDs, headings, and PDF pages when present.
  Synthetic sources, empty results, and request errors are explicit. A rerun
  does not resubmit uploads or source requests; switching sources hides stale
  passages. README includes A1 usage.
- Scope: A1–A4 are complete; A5 remains pending. A4 changes only session history
  and submission handling; A1–A3 controls/presentation modules are unchanged.
  No backend, contract, dependency, or README files changed in A4.
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
- A3 citations: each claim has a dedicated citation expander with reported
  excerpts, source/passage IDs, title, filename, origin, headings, and available
  PDF page/source URL. Missing passages, mismatched excerpts, and inapplicable
  sources are labelled without substituting evidence. Verification details
  show backend checks and reasons, not quality scores or semantic guarantees.
- A3 fallback states: needs_context shows the clarification field, question,
  and options; not_found and insufficient_evidence have distinct messages and
  readable reasons. Factual claims in fallback responses are withheld.
- A3 service errors: query envelopes retain backend error code, message,
  retryability, and request ID even on non-2xx responses. Transport failures,
  timeouts, malformed replies, and inconsistent envelopes have explicit safe
  messages. Raw response bodies/validation inputs are not shown. No automatic
  retries or mock substitution were added. Mode labels and the query spinner
  no longer unconditionally describe live-configured requests as mock.
- A3 verification (2026-10-31, Python 3.13.13, unchanged pinned requirements):
  - `python -m pytest -q -o faulthandler_timeout=30`: 81 passed (48 A3 cases
    and all 33 prior tests), with the existing Starlette/httpx deprecation
    warning. Integration tests ran outside the sandbox for the limitation
    already recorded above.
  - `python -m ruff check .`, `python -m ruff format --check .`, and
    `git diff --check`: passed.
  - Temporary FastAPI/Streamlit servers started; both health endpoints passed.
    The UI displayed a cited mock answer over real local HTTP. After stopping
    that backend, a new UI request displayed BACKEND_UNREACHABLE without an
    answer substitution. All temporary processes stopped after the check.
- A3 limitation: live services remain unimplemented. Additional fallback,
  citation-edge, and service-error cases use synthetic response fixtures;
  local substring inspection does not establish semantic support.
- A4 submissions: a chat-input callback queues each explicit submission with a
  snapshot of its product/version/environment. A queued request is marked
  consumed before validation/HTTP, and its result/error is saved before history
  rendering. Reruns never dispatch completed, failed, or interrupted requests.
  Deliberately submitting the same question again creates a new turn/request.
- A4 history: preserves turn order, original context, cited responses, fallback
  states, and error styling. Context edits, source browsing, and upload controls
  do not resubmit chat. Earlier message shapes remain displayable without
  migration or HTTP. Session state is isolated between browser sessions; v1
  still sends only the latest question and explicit scope to the backend.
- A4 interruptions: a request without a saved outcome remains visible with an
  explicit interruption message and requires a new user submission. Rendering
  failures do not discard saved outcomes or trigger another request.
- A4 verification (2026-10-31, Python 3.13.13, unchanged pinned requirements):
  - `python -m pytest -q -o faulthandler_timeout=30`: 97 passed (16 A4 cases
    and all 81 prior tests), with the existing Starlette/httpx deprecation
    warning. Integration tests ran outside the sandbox for the limitation
    already recorded above.
  - `python -m ruff check .`, `python -m ruff format --check .`, and
    `git diff --check`: passed.
  - Temporary FastAPI/Streamlit startup and health checks passed. Two UI turns
    ran over real HTTP. After stopping the backend, reruns/context edits kept
    both cited replies with zero additional requests. One explicit new
    submission made one attempt; its saved connection error survived another
    rerun. All temporary processes stopped after the check.
- A4 limitation: history is retained within the current Streamlit session.
  Browser reload/new sessions and server restarts are outside this persistence
  scope. No durable storage or backend idempotency was added; live services
  remain unimplemented. Interrupted/rerender-failure cases use synthetic tests.
