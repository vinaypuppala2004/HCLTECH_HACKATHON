# EvidenceDesk

A local document Q&A assistant. Upload PDF, HTML, Markdown, or TXT files and ask
questions with cited excerpts. Supports scope filters, conflicting evidence,
and clarification when context is missing.

## Built with

- **Streamlit** — chat, uploads, and source browsing.
- **FastAPI / Python 3.13** — API and request orchestration.
- **Ollama `qwen3:4b`** — answer generation and verification.
- **Nomic `nomic-embed-text:v1.5`** — document and query embeddings.
- **Qdrant + BM25** — local persistence and hybrid retrieval.
- **Ragas** — evaluation outside interactive requests.

## Setup

Run from the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

For live mode, install [Ollama](https://ollama.com/) and pull the models:

```powershell
ollama pull qwen3:4b
ollama pull nomic-embed-text:v1.5
```

Keep Ollama running at `http://127.0.0.1:11434`. Edit `.env`:

```dotenv
APP_MODE=live
BACKEND_URL=http://127.0.0.1:8000
QDRANT_PATH=./var/qdrant
```

Use `APP_MODE=mock` for a fixed synthetic demo without models or documents.
Live mode needs uploaded documents; a fresh clone has no populated index.

## Start

Open two terminals at the repository root.

**Terminal 1 — backend:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn evidencedesk.api.app:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open [the application](http://127.0.0.1:8501), upload documents, and ask a question.
[API docs](http://127.0.0.1:8000/docs) · [Health](http://127.0.0.1:8000/v1/health)

To reuse this machine's existing corpus, set the index path in the backend
terminal before starting it (if the directory exists):

```powershell
$env:QDRANT_PATH = (Resolve-Path -LiteralPath .worktrees/live-completion/var/qdrant).Path
```

Run only one backend per index path. See the [live runbook](docs/live-runbook.md)
for details. On macOS/Linux, use `.venv/bin/python` and the same `.env` settings.
