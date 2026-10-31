# Person D progress

- Role: FastAPI backend and evaluation.
- Completed: API routes, configuration/factory, mock orchestration, and acceptance smoke test.
- D1 completed (2026-10-31): verified all five public endpoints against contract v1;
  documented error envelopes in OpenAPI; normalized HTTP errors to the frozen status
  table while preserving headers; rejected inconsistent tool envelopes; logged
  unexpected failures without exposing backend details in responses.
- Health/readiness: explicitly describes mock readiness and fixture counts; rejects
  unsupported modes even when tools are injected. No live readiness is claimed.
- Scope: only D1 implemented. D2 integration, startup lifecycle, and concurrency are
  not started; existing mock tools, factory, and shared contracts are unchanged.
- Next: D2 backend integration when requested, then labelled dataset, local Ragas,
  report, and demo examples.
- Blockers: none recorded.
- Verification: Python 3.13.5; `python -m pytest -q` passed (92 tests, including 91
  API cases and the existing API/Streamlit acceptance smoke test);
  `python -m ruff check .`, `python -m ruff format --check .`, and
  `git diff --check` passed.
- Test environment: sandboxed Windows TestClient stalled creating its asyncio
  socket pair; the approved run outside the sandbox passed. One dependency
  deprecation warning from FastAPI/Starlette TestClient remains; dependencies were
  not changed.
- Limitations: mock ingestion still rejects files with `NOT_IMPLEMENTED`; retrieval
  and answers still use the fixed synthetic fixture. No live adapters or evaluation
  results were added.
