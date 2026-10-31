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
- Initial D3 fixture (2026-10-31): `evaluation/data/synthetic-v1/` contains 24 labelled
  questions: 8 direct, 6 paraphrase, 4 conflict/version, 3 ambiguous, 3 unsupported.
  Each label includes explicit scope, a gold Draft, exact excerpts, passage IDs,
  relevant evidence, and a rationale. The 16 development and 8 held-out cases have
  disjoint topic families, including related direct/paraphrase questions.
- Initial D3 provenance/freeze: before the archive was supplied, 6 explicitly synthetic,
  evaluation-only source snapshots (19 passages) support the labels. The 8 held-out
  cases and complete source set were frozen before tuning or model evaluation.
  Canonical JSON hashes, ordered membership, and an independent manifest hash in
  the acceptance test detect changes. Default loading reads development only.
- Scope: this change implements only D3. Application code, B/C folders, shared
  contracts, dependencies, and existing tests are unchanged. D4 has not been started;
  no model calls, Ragas integration, scores, or result report were added.
- Next: D4 local Ragas integration when requested.
- Real-corpus D3 update (2026-10-31): the supplied `enterprise-document-corpus.zip`
  now supports `evaluation/data/enterprise-v1/`: 25 answerable questions and gold
  answers across all 16 public documents (4 HTML, 4 Markdown, 4 PDF, 4 TXT).
  Delivery is dataset-only, per user instruction: readable Q&A, Ragas JSONL,
  canonical evidence labels, source provenance, and a freeze manifest. There are
  17 development and 8 held-out cases with disjoint topics. The synthetic fixture
  remains unchanged. No pipeline evaluation or D4 integration was performed.
- Real-corpus preparation checks: archive and all 16 source hashes verified;
  every cited excerpt and extracted-text location rechecked against the archive;
  selected PDF pages visually inspected; JSONL projections and split membership
  checked. The user will test these labels with the pipeline later.
- Blockers: real ingestion passage IDs still need mapping from the recorded source
  hashes and locations before ID-based retrieval evaluation.
- Earlier synthetic-fixture verification: Python 3.13.5; `python -m evaluation.dataset` passed;
  `python -m pytest tests/acceptance/test_evaluation_dataset.py -q` passed (24 D3
  integrity cases); `python -m pytest -q` passed (134 tests, including D1/D2
  regressions and the existing API/Streamlit acceptance smoke test);
  `python -m ruff check .`, `python -m ruff format --check .`, and
  `git diff --check` passed.
- Test environment: sandboxed Windows TestClient stalled creating its asyncio
  socket pair in earlier tasks; D3's sandboxed pytest run could not create its
  temporary directories. Approved runs outside the sandbox passed. One dependency
  deprecation warning from FastAPI/Starlette TestClient remains; dependencies were
  not changed.
- Limitations: mock ingestion still rejects files with `NOT_IMPLEMENTED`; retrieval
  and answers still use the fixed synthetic fixture. No live adapters or evaluation
  results were added. Neither golden set is indexed by the running API. The synthetic
  fixture is not a real-product benchmark; its held-out cases cover 6 topic families.
  The real-corpus set is assistant-authored and has not had independent human review;
  automatic integrity checks do not replace human semantic review. The limiter is
  per process; it is not coordination across
  multiple server workers. Current ports expose no resource-close hooks and current
  mock tools open no Ollama/Qdrant clients; live resource ownership remains pending
  those adapters.

## Live completion integration — 2026-10-31

- User authorized remaining application work across ownership boundaries, excluding
  Ragas evaluation. D4–D6 remain pending; no scoring, held-out tuning, or report added.
- FastAPI explicitly supports mock/live mode. The live factory wires actual ingestion,
  source reads, hybrid retrieval, grounded Qwen drafting, and semantic verification.
- Health uses real committed counts and model availability; invalid configuration
  fails explicitly. Backend shutdown drains requests and closes model/index clients.
- A complete 16-document / 420-passage corpus imported through HTTP. Source hash/
  location-to-passage mapping is available in ignored `var/corpus-import.json`.
- Python 3.13.5 with the pinned lock: 472 automated tests passed (including mock
  UI/API smoke, live wiring with synthetic Ollama responses, adaptive chunking,
  version scope, invalid-quote/semantic fallback, outages, close/reopen, and restart).
  Ruff lint, format, pip check, and git diff --check passed. Existing Starlette
  TestClient dependency deprecation warning remains. No lock pins were changed.
- Live model request repetition was stopped at the user's direction. All remaining
  behavior checks use deterministic fixtures; optional model checks are opt-in.
