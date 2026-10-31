# Person D progress

- Role: FastAPI backend and evaluation.
- Completed: API routes, configuration/factory, mock orchestration, and acceptance smoke test.
- D1 completed (2026-10-31): verified all five public endpoints against contract v1;
  documented error envelopes in OpenAPI; normalized HTTP errors to the frozen status
  table while preserving headers; rejected inconsistent tool envelopes; logged
  unexpected failures without exposing backend details in responses.
- Health/readiness: explicitly describes mock readiness and fixture counts; rejects
  unsupported modes even when tools are injected. No live readiness is claimed.
- D2 completed (2026-10-31): the ASGI lifespan builds and validates one tool bundle
  per startup using the existing B/C factory and shared ports. Injected bundles are
  used without fallback; failed startup stays unready and fails explicitly.
- Request concurrency: one slot per application process covers ingestion, source
  reads, search, and the entire retrieve/draft/verify query. Overlapping work returns
  HTTP 409 `BUSY` with `retryable=true`; health remains available. The slot is released
  after successes and failures. Shutdown marks the backend unready, rejects new work,
  waits for active work, and releases its bundle; a new lifespan builds afresh.
- Scope: this change implements only D2. B/C implementations, the factory, shared
  contracts, dependencies, and D1 tests are unchanged. D3 has not been started.
- Next: D3 labelled questions and held-out split when requested.
- Blockers: none recorded.
- Verification: the 92-test baseline passed before D2 changes. Python 3.13.5;
  `python -m pytest tests/api/test_backend_runtime.py -q` passed (18 D2 cases), and
  `python -m pytest -q` passed (110 tests, including D1 regression checks and the
  existing API/Streamlit acceptance smoke test);
  `python -m ruff check .`, `python -m ruff format --check .`, and
  `git diff --check` passed.
- Test environment: sandboxed Windows TestClient stalled creating its asyncio
  socket pair; the approved run outside the sandbox passed. One dependency
  deprecation warning from FastAPI/Starlette TestClient remains; dependencies were
  not changed.
- Limitations: mock ingestion still rejects files with `NOT_IMPLEMENTED`; retrieval
  and answers still use the fixed synthetic fixture. No live adapters or evaluation
  results were added. The limiter is per process; it is not coordination across
  multiple server workers. Current ports expose no resource-close hooks and current
  mock tools open no Ollama/Qdrant clients; live resource ownership remains pending
  those adapters.
