# Run the live application

Use Python 3.13 and `pip install -r requirements.txt`. Install the exact local
models once with `ollama pull qwen3:4b` and `ollama pull nomic-embed-text:v1.5`.
Ollama must serve localhost port 11434. No external generation provider or Qdrant
server is used. Nomic's native 768 dimensions reduce to the stored 512-dimensional
MRL profile; Qwen is used for drafting and verification.

Set these values in your existing `.env` without overwriting other settings:

```dotenv
APP_MODE=live
OLLAMA_BASE_URL=http://127.0.0.1:11434
GENERATION_MODEL=qwen3:4b
EMBEDDING_MODEL=nomic-embed-text:v1.5
QDRANT_PATH=./var/qdrant
BACKEND_URL=http://127.0.0.1:8000
```

Start the backend and frontend in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn evidencedesk.api.app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Use one backend worker. Its lifespan owns one Qdrant writer and one timed Ollama
HTTP client, drains in-flight work, then closes both. A second writer to the same
path fails explicitly. Health reports model availability and actual committed
document/revision counts. An empty healthy index accepts ingestion; search returns
INDEX_EMPTY until the first document commits. Missing models make readiness false.
Health probes model presence, while requests verify actual model responses/digests.
An incompatible stored embedding profile requires a new index path, not deletion
or automatic replacement of the existing index.

Upload PDF/HTML/Markdown/TXT in the Documents panel. Files receive independent
ready/duplicate/rejected receipts. Invalid files never appear indexed. Limits are
20 files, 10 MiB each, 50 MiB per batch, 100 PDF pages, and 500 corpus passages.
Corpus imports use metadata from the archive manifest; ordinary UI uploads use
user origin and unspecified scope. Product/environment filters ignore case;
versions match exactly. Comparison hits from another version are labelled
nonapplicable and cannot support factual claims for the selected version.

The public JSON shapes are unchanged. Live requests run hybrid BM25/semantic
retrieval with RRF, grounded drafting, deterministic quote/context gates, then
independent semantic verification using Qwen. Unsupported/unclear judgments
withhold facts. Unresolved conflicts retain both excerpts; missing scope asks for
context. Model/network/timeouts stay explicit errors; live failures never switch
to mocks. Model judgments can still be wrong: quotation integrity is deterministic,
but semantic entailment and conflict identification are model-dependent.

Use the corpus inventory and source-ID mapping instructions in `corpus/README.md`.
Do not tune against held-out questions. Ragas integration, grading, quality metrics,
and an evaluation report are deliberately excluded.

Run `python -m evidencedesk.core.check_live` for a real local integration smoke:
it creates a temporary index with labelled synthetic sources, checks one direct
answer and restart. Additional model scenarios require explicit `--all-cases`;
automated tests exercise those behaviors without local model calls.
Results go to ignored `var/live-check.json`; these are operational examples, not
an evaluation score. `pytest -q`, Ruff lint/format, and `pip check` cover automated
regressions. No raw uploads or runtime storage belong in Git.
