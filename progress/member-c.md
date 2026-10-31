# Person C progress

- Role: retrieval, answer generation, and shared contracts.
- Completed: retrieval stub, typed contracts, and mock answer/verification tools.
- C1 increment: opt-in `OllamaEmbeddings` implements the existing embedding port
  for `nomic-embed-text:v1.5`. It validates vector count, dimensions, finite values,
  and model identity; adds query/document prefixes; and accepts a shared model lock.
  D's integration instructions and the error table are in `docs/embeddings.md`.
- C4 increment: claim verification rejects inapplicable evidence and blank or invalid
  quotes. Exact quotes from inapplicable sources retain `quote_valid=true` with an
  `unsupported` verdict, triggering the existing API fallback.
- Next: add Qdrant persistence, then hybrid ranking and local grounded generation.
- Handoff: D owns FastAPI, configuration, dependency wiring, and API orchestration.
- Local setup: installed `nomic-embed-text:v1.5` in Ollama storage; model files
  are outside Git. Verified the missing-model error before installation.
- Live check: generated two synthetic passage vectors and one query vector, all
  768-dimensional, using model digest
  `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
  The first 60-second call timed out during cold start; a retry using a 180-second
  client timeout succeeded. D should manage warmup/readiness and timeout policy.
- Verification: Python 3.13.18 with the pinned lock; `pytest -q` passed all 45
  tests (30 embedding cases, 14 citation/fallback cases, and the mock chat smoke test).
  `ruff check .`, `ruff format --check .`, and `git diff --check` passed.
  Pytest reported one dependency deprecation warning about Starlette's httpx client.
- Limitations: semantic support and conflict verification remain unimplemented;
  passing citation checks still report only `limited` evidence strength. The API
  remains in mock mode; Qdrant persistence, ranking, and D's live wiring are pending.
