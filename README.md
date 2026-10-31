# EvidenceDesk

A mock-first local enterprise-documentation Q&A assistant with a Streamlit frontend.
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
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
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

For A1, expand **Documents** to upload PDF, HTML, Markdown, or TXT files (up to
20 files, 10 MB each, 50 MB per batch). Click **Upload documents** to submit;
each file shows its backend status. The current mock rejects every upload with
`NOT_IMPLEMENTED`; rejected files are not indexed.

Click **Browse / refresh sources**, select a document, and click **Open source**
to see exact passages, source/passage IDs, headings, and PDF page numbers when
available. Synthetic sources are labelled. Refresh the list after live uploads
to see newly indexed documents. Upload and source requests run only on submission.

For A2, set **Product**, **Version**, and **Environment** in the sidebar before
asking a question. Blank fields are sent as null; version identifiers retain
their exact spelling. Conflict responses show evidence side by side with source
context, applicability, and the backend's resolution/selection. **Use this context**
fills the sidebar from that source; submit your question again to request a new
answer. Changing context does not resolve an existing conflict. The current mock
backend ignores context and returns no conflicts; comparison tests use explicitly
synthetic responses matching the frozen contract.

For A3, expand **Citations for claim ...** below each claim to inspect its exact
excerpts, passage/source IDs, and available source locations. Missing or
mismatched citations and inapplicable passages are labelled. **Verification
details** shows backend checks, not evaluation scores. Missing context, no
results, and insufficient evidence have distinct messages; fallback responses
withhold factual claims. Query errors show the backend code, message, request ID,
retryability, and recovery guidance when available. Connection/timeouts and
invalid replies are explicit; failed requests never substitute a mock answer.

For A4, each explicit question creates a new turn with its original context.
Replies, citations, fallback states, and error styling survive Streamlit reruns.
Editing context or browsing sources does not resend chat requests. Submitting
the same question deliberately creates a new request. Interrupted requests are
labelled and require explicit resubmission. History belongs to the current
Streamlit session; a browser reload/new session or server restart is not durable
history storage. The API receives only the latest question and explicit scope.

- [Swagger API documentation](http://127.0.0.1:8000/docs)
- [Health](http://127.0.0.1:8000/v1/health)
- [OpenAPI JSON](http://127.0.0.1:8000/openapi.json)

On macOS/Linux use Python 3.13, `.venv/bin/python` instead of the Windows
executable, and `test -e .env || cp .env.example .env` to preserve an existing
environment file.

## Panel presentation preview

The [frontend demo runbook](ui/DEMO.md) contains a five-minute walkthrough,
preflight checks, and a failure/recovery rehearsal. It complements the shared
team demo in `plan.md`; it does not replace the evaluation report owned by D.

Run the separate preview in another terminal:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/demo.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

Open [the presentation preview](http://127.0.0.1:8502). Seven fixed synthetic
examples show cited answers, version comparison/selection, an unresolved
contradiction, clarification, no support, and failed verification. They reuse
the frontend answer/conflict renderers and require no backend, models, or index.
The preview is labelled on every example and never activates automatically
when the main app encounters an error. Its context controls do not issue queries
or alter fixed results; selecting a different example is an explicit presentation
action. These are not saved live results, benchmark scores, or real product policies.

## Test and lint

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The frontend regression suite covers upload limits/statuses, source browsing,
scope serialization, conflict comparisons, citations, fallback states, structured
service errors, session isolation, interrupted runs, and no request replay on
rerun. Presentation checks validate synthetic provenance, exact excerpt matches,
all seven screens, and independence from backend HTTP calls. The existing smoke
test bridges Streamlit HTTP calls into FastAPI's test client and checks the tool
pipeline and citation integrity; servers need not be running.

These checks verify frontend behavior against mock and contract-shaped responses.
They do not establish live retrieval quality, semantic faithfulness, or Ragas
metrics. The pinned Starlette/httpx combination currently emits a deprecation
warning; no dependency change is required for the passing suite.

Example request to a running backend:

```powershell
$body = '{"question":"How do I reset my password?","context":{"product":null,"version":null,"environment":null}}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/query -ContentType application/json -Body $body
```

## Frontend troubleshooting

| Symptom | What to check |
|---|---|
| `BACKEND_UNREACHABLE` | Start FastAPI in its own terminal; match `BACKEND_URL` to its host and port. Submit again explicitly. |
| `REQUEST_TIMEOUT` or `MODEL_TIMEOUT` | Check backend/service logs and readiness, then retry when ready. The UI does not replace failures with mock data. |
| Upload reports `NOT_IMPLEMENTED` | Expected with the current ingestion stub. The file was rejected and is not indexed. |
| Different questions return the same passage | Expected in mock mode; scope is sent but the backend ignores it. |
| A context edit leaves an old answer unchanged | History retains the context used for that turn. Submit a new question for a new response. |
| History is empty after reload/restart | History is session-local; durable storage is not implemented. |
| Health says ready but no live service is available | `ready=true` describes the mock backend, not Ollama, Qdrant, or live ingestion. |

After dependencies are installed, mock runtime and the presentation preview
operate locally without external API keys or model downloads. First-time
dependency installation still needs access to the pinned packages.

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
