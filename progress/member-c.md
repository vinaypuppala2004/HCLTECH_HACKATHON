# Person C progress

- Focus: retrieval. Model split is Qwen `qwen3:4b` for generation and Nomic
  `nomic-embed-text:v1.5` for embeddings, per the latest user instruction.
- C1 implemented: native Nomic adapter, trained MRL reduction to 512 dimensions,
  backend-owned local Qdrant storage, document/source preservation, committed
  revisions, idempotent indexing, scoped semantic search, and restart support.
- Compatibility: stored dimension/transform profile and model digest prevent
  mixing incompatible vectors. Invalid input or embedding failures do not commit
  a ready document; interrupted point writes stay outside committed search results.
- Prior evidence: 65 retrieval tests passed before the no-check instruction.
  A real Nomic run produced the expected first hit for all eight synthetic
  development questions at both 768 and 512 dimensions. Fresh Python processes
  reopened both indexes and performed new live queries with source excerpts intact.
- Dimension choice: 512 float32 components take 2048 bytes instead of 3072 at 768.
  This reduces vector storage/search work, not native model inference. Actual
  measurements and limitations are recorded in `docs/c1-report.md`.
- Removed the experimental raw-Qwen embedding launcher and stopped its task-owned
  helper. The regular Ollama service handles both distinct models on port 11434.
- C4 prior increment: invalid or inapplicable citations fail verification and
  trigger the mock API's existing fallback; semantic verification is pending.
- Handoff: B supplies Document/Passage records to `QdrantIndex.index_document`.
  D owns API integration and one client per backend process. The default API
  remains mock-only. No other person's implementation files were changed.
- Next: C2 BM25 ranking, semantic fusion, and version counterparts. Broader
  corpus/held-out evaluation and live API integration remain separate work.
- Latest edits are unverified: the user requested no further tests, lint,
  formatting, or verification checks. No such checks were run after that request.
