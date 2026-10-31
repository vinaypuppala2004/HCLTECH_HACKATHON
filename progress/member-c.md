# Person C progress

- Role: retrieval, answer generation, and shared contracts.
- Model policy: only `qwen3:4b`. No alternative model is invoked or downloaded.
- C1 fix: the prior capability-list guard was too strict. Ollama's default Qwen
  runner also lacked embedding mode. Added the `embedding_server` launcher with
  process-scoped embedding and last-token pooling flags on loopback port 11435.
  Generation remains on the regular service at port 11434 using the same weights.
- Adapter: validate the real embedding endpoint rather than reject missing static
  capability metadata. Model identity, dimensions, vectors, and locking are checked.
  Use CPU, context 1024, batch 64, no truncation, and one-minute keepalive.
- Live verification: the project launcher and adapter generated two passage vectors
  and one query vector, all 2560-dimensional, for synthetic inputs. Both services
  report digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`.
  The regular service completed a real generation request with HTTP 200 afterward.
- C4 increment: invalid or inapplicable claim citations fail verification and trigger
  the existing API fallback. A valid but inapplicable quote remains quote-valid.
- Next: Qdrant persistence and BM25/semantic retrieval, followed by grounded Qwen
  drafting. D must evaluate the experimental raw-vector profile's retrieval quality.
- Handoff: D owns FastAPI, settings, dependency wiring, startup/readiness, and API
  orchestration. Wire `EMBEDDING_OLLAMA_BASE_URL` separately and align the legacy
  model defaults in `core/settings.py`. C has not edited D's files.
- Verification: Python 3.13.18; all 55 tests passed (40 embedding cases, 14 citation
  cases, and the mock chat smoke test). Ruff lint/format and `git diff --check`
  passed. The real project launcher, adapter vectors, matching model digests, and
  regular-service generation were verified. One existing dependency warning remains.
- Limits: actual raw Qwen vectors are verified; semantic retrieval quality is not.
  The API remains in mock mode; Qdrant, live answer integration, and evaluation
  remain pending. No shared dependency pins or JSON shapes changed.
