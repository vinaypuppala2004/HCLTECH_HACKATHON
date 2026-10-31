# EvidenceDesk Implementation Plan

## Shared baseline — Person C only

### Goal and architecture
Build a local documentation assistant that answers with cited evidence, exposes
conflicting versions, and asks for missing context or declines when support is
insufficient. The centerpiece is side-by-side evidence and explicit version selection.

Architecture: Streamlit → FastAPI → retrieval → draft → verification → cited reply.
Planned ingestion: PDF/HTML/Markdown/TXT → heading-aware passages → local embeddings
→ Qdrant. Combine BM25 and semantic retrieval through reciprocal rank fusion.

### Tech stack
| Component | Choice | Skeleton status |
|---|---|---|
| Interface | Streamlit | HTTP-backed mock chat |
| Backend | Python / FastAPI / Pydantic | Typed routes and tool wiring |
| Generation | Ollama `qwen3:4b` | Planned; no inference |
| Embeddings | Ollama `nomic-embed-text:v1.5` | Planned; no model calls |
| Vector storage | Qdrant local persistent directory | Planned; no database |
| Retrieval | BM25 + semantic search | One fixed fixture |
| Evaluation | Ragas with local Ollama and labelled checks | Planned; no scores |

### Team and ownership
| Person | Owned folders/files | Branch prefix |
|---|---|---|
| A — Frontend | `ui/`, `tests/ui/`, `README.md` | `feat/frontend-` |
| B — Chunking | `src/evidencedesk/ingestion/`, `corpus/`, `tests/ingestion/` | `feat/chunking-` |
| C — Retrieval and backend | `src/evidencedesk/{retrieval,assistant,api,core,contracts,mocks}/`, `tests/{retrieval,assistant}/`, `docs/`, root configuration | `feat/retrieval-` |
| D — Evaluation | `evaluation/`, `tests/acceptance/` | `feat/eval-` |

Each person edits only their section below and matching progress file. C alone
maintains this shared baseline, milestones, checkpoints, decisions, and demo
script. Use separate branches and working checkouts. Ask before crossing ownership.
Backend orchestration and shared contracts belong to C alongside retrieval;
ingestion and source preparation belong to B alongside chunking.

### Milestones and integration checkpoints
| Time | Gate | Acceptance |
|---|---|---|
| 0:00–0:30 | Mock skeleton | Install, API, UI, smoke test, and lint work |
| 0:30–2:30 | Parallel modules | A/B/C/D replace stubs behind agreed contracts |
| 2:30–3:00 | First live integration | One document → retrieval → answer → UI |
| 3:00–4:00 | Full integration | Corpus, citations, conflicts, and fallback |
| 4:00–5:00 | Evaluation | Review development questions and repair failures |
| 5:00–6:00 | Freeze | Held-out report, five examples, offline restart |
| 6:00–7:00 | Buffer | Demo-breaking fixes and two rehearsals |

At each integration checkpoint C merges small working commits, runs shared
checks, and verifies the vertical slice. Live failures must stay explicit; never
silently substitute mocks. Cut polish before citations, conflicts, or evaluation.

### Decisions log
| Decision | Reason |
|---|---|
| Local FastAPI + Streamlit | Agreed stack; no public deployment |
| Python 3.13 and a pinned dependency lock | Match the verified setup across teammates |
| `qwen3:4b` generation | User-selected; benchmark on the 4 GB GPU |
| Separate local embedding model | Generation and embeddings have different roles |
| Qdrant local directory | User-selected persistence; backend owns the client |
| Ragas outside interactive requests | User-selected evaluation without chat latency |
| Mock-only first skeleton | Parallel work without external services/downloads |
| One explicitly synthetic fixture | No real corpus or RAG claimed yet |
| Required JSON keys and explicit nulls | Consistent tools, API, mocks, and UI |
| `NOT_IMPLEMENTED` for ingestion | Never pretend an upload was indexed |
| Shared plan sections owned by C | Prevent repeated edits to the same lines |
| A frontend, B chunking, C retrieval, D evaluation | User-confirmed final team split |

### Demo script — five minutes
1. 0:00–0:30: Explain scattered documents, conflicting versions, and local operation.
2. 0:30–1:30: Ask a direct question and paraphrase; show cited excerpts.
3. 1:30–3:00: Compare versions, select context, and explain the changed answer.
4. 3:00–4:00: Show an unresolved contradiction and unsupported question.
5. 4:00–5:00: Present measured evaluation, limitations, and team architecture.

Use clearly labelled saved live results if timing requires them. Current skeleton
demo: ask "How do I reset my password?" and show the fixed mock reply/source.
All questions currently return that same fixture; the full script is future work.

## Person A — Frontend — edit only this section
- [x] Streamlit chat sends HTTP requests and displays replies/evidence.
- [ ] A1: Add upload controls and source browsing using the frozen API.
- [ ] A2: Add product/version/environment controls and side-by-side conflicts.
- [ ] A3: Show claim citations, fallback states, and clear service errors.
- [ ] A4: Preserve session history without repeating requests on rerun.
- [ ] A5: Finish frontend checks, README, and panel-facing demo presentation.

Acceptance: UI states work against mocks and live responses without hidden fallback.
Progress: `progress/member-a.md`.

## Person B — Chunking — edit only this section
- [x] Ingestion/source-reader stubs and owned folders exist.
- [ ] B1: Curate public sources and provenance; label synthetic fixtures.
- [ ] B2: Parse PDF, HTML, Markdown, and TXT with location preservation.
- [ ] B3: Segment passages with headings, overlap, and stable source IDs.
- [ ] B4: Report empty/corrupt inputs; send passages to C's indexing port.
- [ ] B5: Verify formats and deduplication; share source IDs with D for labels.

Acceptance: citation locations survive chunking; failed files never appear indexed.
Progress: `progress/member-b.md`.

## Person C — Retrieval and backend — edit only this section
- [x] Shared contracts, configuration, ports, and mock fixtures exist.
- [x] Retrieval stub, FastAPI, and mock retrieve → draft → verify workflow exist.
- [ ] C1: Add local embeddings and backend-owned Qdrant persistence.
- [ ] C2: Add BM25/semantic fusion, scope filters, and version counterparts.
- [ ] C3: Benchmark `qwen3:4b`; add grounded drafting and conflict/clarification logic.
- [ ] C4: Add verification/fallback, wire B's passages, and serialize model requests.
- [ ] C5: Verify restart, share ranking results with D, and integrate at checkpoints.

Acceptance: retrieval respects scope and persists; answers cite evidence and fail clearly.
Progress: `progress/member-c.md`.

## Person D — Evaluation — edit only this section
- [x] One smoke test covers API/tool wiring, chat submission, and rerun behavior.
- [ ] D1: Label 24 questions; freeze 8 held-out cases before tuning.
- [ ] D2: Integrate Ragas with explicitly local model and embedding providers.
- [ ] D3: Measure retrieval, faithfulness, citations, fallback, and latency.
- [ ] D4: Manually review grading; produce a report and five evidence-backed examples.
- [ ] D5: Run acceptance checks and rehearse the five-minute demo with A.

Acceptance: evaluation is reproducible, held-out results are separate, and metrics are real.
Progress: `progress/member-d.md`.
