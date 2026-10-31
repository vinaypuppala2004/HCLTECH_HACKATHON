# Person C progress

- Role: retrieval, answer generation, and shared contracts.
- Current model policy: user requires only `qwen3:4b`. The earlier Nomic experiment
  is superseded and is not a completed Qwen embedding feature.
- C1 increment: `OllamaEmbeddings` is locked to `qwen3:4b` and checks advertised
  embedding support before sending input. It never selects another installed model.
  Vector validation, model identity checks, and shared request locking remain.
- Live check: local Qwen advertises `completion`, `tools`, and `thinking`, with no
  `embedding` capability. A direct embedding request returned HTTP 501. The guarded
  adapter returned `EMBEDDING_UNAVAILABLE`; successful Qwen vectors are pending.
- C4 increment: claim verification rejects inapplicable evidence and blank or invalid
  quotes. Valid quotes from inapplicable sources retain `quote_valid=true` with an
  `unsupported` verdict, triggering the existing API fallback.
- Next: implement BM25 lexical retrieval, then grounded Qwen drafting. Semantic
  retrieval and Qdrant vector persistence need working embeddings under this policy.
- Handoff: D owns FastAPI, configuration, dependency wiring, and API orchestration.
  `.env.example` uses Qwen for both model fields; D must align the two legacy
  embedding defaults in `core/settings.py`. C has not edited D's files.
- Verification: Python 3.13.18; all 54 tests passed, including the no-substitution
  regression and existing mock chat smoke test. Ruff lint, format, and diff checks
  passed. The live capability guard returned the expected explicit error.
  Pytest reported one existing Starlette/httpx dependency deprecation warning.
- Limitations: API tools still use mocks; semantic answer support, conflict
  verification, live generation, and evaluation are not complete. Existing Nomic
  weights have not been deleted, and no Nomic model calls are made by the new adapter.
