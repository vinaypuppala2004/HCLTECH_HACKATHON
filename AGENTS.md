# Agent rules

## Project summary and design principle
EvidenceDesk is a local document Q&A assistant: FastAPI, Streamlit, Ollama
`qwen3:4b`, Qdrant local persistence, and Ragas evaluation.
Build mock-first behind frozen contracts; cite evidence, expose conflicts, and
label mocks. Live adapters are not implemented yet.

## Read first
- `plan.md` for scope, ownership, milestones, and the task board.
- `docs/contracts.md` for every tool and API JSON contract.

## Folder ownership
| Folder or file | Owner |
|---|---|
| `ui/`, `tests/ui/`, `README.md` (frontend) | Person A |
| `src/evidencedesk/ingestion/`, `corpus/`, `tests/ingestion/` (chunking) | Person B |
| `src/evidencedesk/retrieval/`, `tests/retrieval/` | Person C |
| `src/evidencedesk/assistant/`, `api/`, `core/`, `contracts/`, `mocks/` | Person C |
| `tests/assistant/`, `docs/`, root configuration, `AGENTS.md` | Person C |
| `evaluation/`, `tests/acceptance/` | Person D |
| `progress/member-a.md` through `member-d.md` | Matching person |
The abbreviated C paths above are under `src/evidencedesk/`.
Each person edits only their labelled section of `plan.md`; C owns shared sections.

## Git rules
- Never work on `main`; use `feat/<task>` branches and separate clones/worktrees.
- Stay in your own folders; ask the owner before editing another person's files.
- Ask before editing shared files: `package.json` (if introduced), requirements,
  lock files, `pyproject.toml`, contracts, `.env.example`, and `AGENTS.md`.
  An explicit user request for those changes already authorizes them.
- Make small commits; run tests and lint before committing. Never force-push.
- Do not commit secrets, uploads, model files, or Qdrant runtime storage.
- Show `git diff --stat` and `git status --short --branch` before finishing.

## Commands
Run from the repository root. Use Python 3.13 with the pinned dependency lock.
PowerShell setup:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```
Do not overwrite an existing `.env`. Start servers in separate terminals:
```powershell
.\.venv\Scripts\python.exe -m uvicorn evidencedesk.api.app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```
Tests and lint:
```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```
On macOS/Linux substitute `.venv/bin/python` and `cp .env.example .env`.
Mock mode needs no Ollama, Qdrant server, documents, or external API keys.

## Definition of done
- Meet the owned task's acceptance criterion without changing contracts silently.
- End-to-end mock startup, smoke test, and lint pass; errors are explicit.
- Update only your plan section and progress file; record checks and limitations.
- Cite source identifiers and exact excerpts; never fabricate evaluation scores.
- Do not claim live features complete while they still return mock data.
- When unsure, ask; don't guess contracts.
