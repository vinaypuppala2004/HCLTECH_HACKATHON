# EvidenceDesk frontend presenter runbook

This is Person A's A5 walkthrough, complementing C's shared team script in
`plan.md`. The main app makes real local HTTP calls to a **mock backend**.
The separate presentation preview renders **fixed synthetic examples** of UI
states that the current backend does not produce. Neither surface proves live
RAG, indexing, model inference, or evaluation quality.

## Prepare the room

1. Use the frontend feature checkout and Python 3.13 with the pinned requirements.
   Follow the root README's install instructions, preserving any existing `.env`.
2. Keep `APP_MODE=mock`. Leave `BACKEND_URL=http://127.0.0.1:8000` for the commands
   below. Open each server in its own terminal, from the same checkout.
3. Start FastAPI:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn evidencedesk.api.app:app --host 127.0.0.1 --port 8000
   ```

4. Start the main app:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
   ```

5. Start the presentation preview:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run ui/demo.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
   ```

6. Open [the main app](http://127.0.0.1:8501),
   [the preview](http://127.0.0.1:8502), and
   [mock health](http://127.0.0.1:8000/v1/health).
   Health should identify `mode=mock`; readiness does not imply live model/index
   availability. The preview also runs with the backend stopped.

After installation, the mock app and preview need no internet, Ollama, Qdrant
server, documents, or API keys. Use readable browser zoom with both conflict
columns visible. Start on a clean main-app session if you want an empty history.

## Preflight checks

Run before presenting and record the actual output in `progress/member-a.md`:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

| Action | Expected observation |
|---|---|
| Ask `How do I reset my password?` in the main app | Fixed mock reply, `claim_mock_1`, `doc_mock_guide`, and `passage_mock_reset`. |
| Expand the claim citation | Exact excerpt: `Use the account portal to reset your password.` Origin is synthetic; no public URL is invented. |
| Browse / refresh sources, then Open source | The synthetic mock guide and exact passage are visible. |
| Upload this runbook (`ui/DEMO.md`) as a demonstration input | Per-file `rejected` / `NOT_IMPLEMENTED`; it is not indexed. |
| Edit Version, browse sources, or rerun the app | Existing chat turns and original context remain; no chat request is repeated. |
| Choose each preview example | Synthetic warning stays visible; citations/conflicts/fallbacks render without a backend. |

## Five-minute frontend walkthrough

| Time | Surface and action | Presenter point |
|---|---|---|
| 0:00–0:35 | Main app: show the mock banner | Explain scattered guidance and conflicting versions. The intended path is Streamlit → FastAPI → retrieve → draft → verify; live adapters are future work. |
| 0:35–1:30 | Ask the password question, inspect its citation, browse the guide, show upload rejection | Evidence is inspectable. A rejected upload is never called indexed. Current HTTP-backed replies are fixed fixtures. |
| 1:30–3:20 | Explicitly switch to the preview. Select examples 2, 3, and 4 | Compare 15/30-minute synthetic excerpts. Use this context fills controls only. Example 3 is a separate illustrative v2 resolution, not a newly generated answer. Example 4 stays unresolved despite matching context. |
| 3:20–4:20 | Preview examples 5, 6, and 7 | Show a clarification, a question with no support, and an answer withheld after failed verification. No factual claim is invented to fill a gap. |
| 4:20–5:00 | Show Current implementation and limits | Separate completed frontend behavior from planned live services. Hand off evaluation discussion to D only if a measured report exists. No scores are available from this preview. |

Example 1 is a compact citation screen if the main-app citation was hard to see.
Presenter notes beneath each preview explain the specific state. The synthetic
DemoPortal reset-link policies are invented for UI presentation; they are not
real documentation or operational advice.

## Rehearse failure and recovery

Do this before the panel, or use it as an optional short recovery demonstration:

1. Keep a cited answer in the main-app history. In the terminal for the backend
   you started, press Ctrl+C. Leave Streamlit running.
2. Edit a context field. The saved answer and its submitted context stay visible;
   rerendering does not need a backend query.
3. Explicitly submit a new question. Expect `BACKEND_UNREACHABLE`, with no answer
   substitution. Rerun or edit context again: the saved error remains visible
   without another attempt.
4. Restart FastAPI using the command above, then submit explicitly. The earlier
   error stays in history and the new turn can succeed.
5. Visit the separate preview while FastAPI is stopped. It continues to render
   its fixed examples; identify it to the panel as the presentation preview.

Run the normal walkthrough once and this failure/recovery rehearsal once. If a
live adapter fails in a future integration, present the actual error and name
any separate preview being shown. Never describe synthetic previews as saved
live results.

## Current live integration

The main application now supports live ingestion, persistent Qdrant, hybrid
retrieval, Qwen drafting, and semantic verification. Use `docs/live-runbook.md`
for the real pipeline. This presentation remains an independent synthetic preview;
its examples are not saved live responses or evaluation scores.

## Claims to keep precise

- Frontend behavior is tested against mocks and typed live-shaped responses;
  live mode applies product/version/environment scope to real indexed sources.
- Measured Ragas evaluation remains pending. The preview performs no inference.
- A quotation substring check is not semantic verification. `limited` is an
  evidence-strength label, not a numerical quality score.
- Session history survives reruns within the current Streamlit session. A
  browser reload/new session or server restart is outside that persistence.
- Do not present latency or quality numbers from these examples. D owns any
  measured evaluation report and evidence-backed live examples.
