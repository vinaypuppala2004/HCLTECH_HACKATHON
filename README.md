# EvidenceDesk

A mock-first skeleton for a local enterprise-documentation Q&A assistant.
The planned product uses Ollama `qwen3:4b`, local embeddings, Qdrant local
persistence, and Ragas evaluation. **Live integrations are not implemented.**

Every question currently returns the same synthetic password-reset passage.
The app requires no running Ollama, Qdrant, downloaded documents, or API keys.
Ingestion returns per-file `NOT_IMPLEMENTED` rejections and never saves uploads.

## Install — Windows PowerShell

Use Python 3.13 with the pinned dependency lock. Run from the repository root;
activation is unnecessary. Copy the environment file only if `.env` does not exist.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Keep `APP_MODE=mock`. Dependency installation needs internet; mock runtime does not.

## Run — two terminals

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn evidencedesk.api.app:app --host 127.0.0.1 --port 8000
```

Chat:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open [the chat](http://127.0.0.1:8501), submit **How do I reset my password?**, and
expand the supporting evidence. The UI visibly identifies mock behavior.

- [Swagger API documentation](http://127.0.0.1:8000/docs)
- [Health](http://127.0.0.1:8000/v1/health)
- [OpenAPI JSON](http://127.0.0.1:8000/openapi.json)

On macOS/Linux use `python3 -m venv .venv`, `.venv/bin/python` instead of the
Windows executable, and `cp .env.example .env`.

## Test and lint

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

One smoke test covers health, the typed tool/API pipeline, citation integrity,
validation errors, a submitted Streamlit message, and no repeat request on rerun.
It bridges the UI HTTP call into FastAPI's test client; servers need not be running.

Example request to a running backend:

```powershell
$body = '{"question":"How do I reset my password?","context":{"product":null,"version":null,"environment":null}}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/query -ContentType application/json -Body $body
```

## Team handoff

Read `AGENTS.md`, `plan.md`, and `docs/contracts.md`. Work in assigned `feat/<task>`
branches using separate clones/worktrees, and edit only your section of the plan.

```text
src/evidencedesk/
  ingestion/     B: parsing, chunking, and source tools
  retrieval/     C: embeddings, Qdrant, search
  assistant/     C: answers and verification
  api/           D: FastAPI HTTP routes and orchestration
  core/          D: configuration and dependency factory
  contracts/     C: models and callable ports
  mocks/         C: shared synthetic source
ui/              A: frontend / Streamlit
evaluation/      D: future Ragas dataset/report
corpus/          B: future curated documents
tests/           Owned module folders and D's acceptance smoke test
progress/        One file per person
```

No Node app or `package.json` is needed. Shared Python dependency files are
`pyproject.toml`, `requirements.txt`, and `requirements.lock`.

Do not commit `.env`, uploads, models, or Qdrant runtime data. Only the backend
should open the future Qdrant local store. `APP_MODE=live` deliberately fails
until real adapters exist. Mock checks and timings are not Ragas quality scores.
