# EvidenceDesk Implementation Plan

## Shared baseline — Person C only

### Goal and architecture
Build a local documentation assistant that answers with cited evidence, exposes
conflicting versions, and asks for missing context or declines when support is
insufficient. The centerpiece is side-by-side evidence and explicit version selection.

Architecture: Streamlit → FastAPI → retrieval → draft → verification → cited reply.
Planned ingestion: PDF/HTML/Markdown/TXT → heading-aware passages → BM25 and
semantic retrieval. Use `qwen3:4b` for generation and `nomic-embed-text:v1.5` for
embeddings. The C1 adapter stores 512-dimensional Nomic MRL vectors in local
Qdrant, with committed revisions and restart support. Live ingestion, BM25/semantic
fusion, version counterparts, Qwen drafting, semantic verification, and API wiring
are integrated. Ragas scoring and held-out evaluation remain pending.

### Tech stack
| Component | Choice | Skeleton status |
|---|---|---|
| Interface | Streamlit | Live chat/uploads/sources and separate synthetic preview |
| Backend | Python / FastAPI / Pydantic | Explicit mock/live tools, lifecycle, readiness, and concurrency |
| Generation | Ollama `qwen3:4b` | Grounded drafting and semantic verification |
| Embeddings | `nomic-embed-text:v1.5`, 512-dimensional MRL profile | Live adapter wired into API |
| Vector storage | Qdrant local persistent directory | C1 persistence and restart implemented |
| Retrieval | BM25 + semantic RRF, scope filters, version counterparts | Wired into explicit live mode |
| Evaluation | Ragas with local Ollama and labelled checks | Planned; no scores |

### Team and ownership
| Person | Owned folders/files | Branch prefix |
|---|---|---|
| A — Frontend | `ui/`, `tests/ui/`, `README.md` | `feat/frontend-` |
| B — Chunking | `src/evidencedesk/ingestion/`, `corpus/`, `tests/ingestion/` | `feat/chunking-` |
| C — Retrieval and answers | `src/evidencedesk/{retrieval,assistant,contracts,mocks}/`, `tests/{retrieval,assistant}/`, `docs/`, root configuration | `feat/retrieval-` |
| D — FastAPI and evaluation | `src/evidencedesk/{api,core}/`, `evaluation/`, `tests/{api,acceptance}/` | `feat/backend-` |

Each person edits only their section below and matching progress file. C alone
maintains this shared baseline, milestones, checkpoints, decisions, and demo
script. Use separate branches and working checkouts. Ask before crossing ownership.
FastAPI routes, configuration, dependency wiring, and request orchestration belong
to D. C owns retrieval, answer tools, and shared contracts; D calls those tools
through the agreed ports. B owns ingestion and chunking; A owns the frontend.

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

At each integration checkpoint C coordinates merges and D wires backend modules;
the team runs shared checks and verifies the vertical slice. Live failures must stay explicit; never
silently substitute mocks. Cut polish before citations, conflicts, or evaluation.

### Decisions log
| Decision | Reason |
|---|---|
| Local FastAPI + Streamlit | Agreed stack; no public deployment |
| Python 3.13 and a pinned dependency lock | Match the verified setup across teammates |
| `qwen3:4b` generation | User-selected; benchmark on the 4 GB GPU |
| Qwen generation and Nomic embeddings | Latest user-selected model split |
| 512-dimensional Nomic MRL vectors | Smaller storage; eight synthetic development cases matched the full profile |
| Qdrant local directory | User-selected persistence; backend owns the client |
| Ragas outside interactive requests | User-selected evaluation without chat latency |
| Mock-only first skeleton | Parallel work without external services/downloads |
| One explicitly synthetic fixture | No real corpus or RAG claimed yet |
| Required JSON keys and explicit nulls | Consistent tools, API, mocks, and UI |
| `NOT_IMPLEMENTED` for ingestion | Never pretend an upload was indexed |
| Shared plan sections owned by C | Prevent repeated edits to the same lines |
| A frontend, B chunking, C retrieval/answers, D FastAPI/evaluation | User-confirmed team split |

### Demo script — five minutes
1. 0:00–0:30: Explain scattered documents, conflicting versions, and local operation.
2. 0:30–1:30: Ask a direct question and paraphrase; show cited excerpts.
3. 1:30–3:00: Compare versions, select context, and explain the changed answer.
4. 3:00–4:00: Show an unresolved contradiction and unsupported question.
5. 4:00–5:00: Present measured evaluation, limitations, and team architecture.

Use clearly labelled saved live results if timing requires them. Current skeleton
demo: ask "How do I reset my password?" and show the fixed mock reply/source.
Mock questions return that fixture. Live mode indexes real documents; see
`docs/live-runbook.md`. The separate frontend preview is explicitly synthetic.
Ragas measurements/report remain outside this completion task.

## Person A — Frontend — edit only this section
- [x] Streamlit chat sends HTTP requests and displays replies/evidence.
- [x] A1: Add upload controls and source browsing using the frozen API.
- [x] A2: Add product/version/environment controls and side-by-side conflicts.
- [x] A3: Show claim citations, fallback states, and clear service errors.
- [x] A4: Preserve session history without repeating requests on rerun.
- [x] A5: Finish frontend checks, README, and panel-facing demo presentation.

Acceptance: UI states work against mocks and live responses without hidden fallback.
Progress: `progress/member-a.md`.

## Person B — Chunking — edit only this section
- [x] Ingestion/source-reader stubs and owned folders exist.
- [x] B1: Curate public sources and provenance; label synthetic fixtures.
- [x] B2: Parse PDF, HTML, Markdown, and TXT with location preservation.
- [x] B3: Segment passages with headings, overlap, and stable source IDs.
- [x] B4: Report empty/corrupt inputs; send passages to C's indexing port.
  - [x] Add opt-in upload validation, strict base64/limits, and per-file errors.
  - [x] Connect C's indexing port and verify committed receipts/source IDs.
- [x] B5: Verify formats and deduplication; share source IDs with D for labels.

Person B phases B1–B5 are integrated. The supplied 16-document public archive
has a provenance inventory and license notices in `corpus/`. PDF layout extraction
preserves page order; HTML text groups within headings for live indexing. Live
chunks use 4,096/200, with deterministic 1,800/200 retry on embedding length rejection.
The actual corpus commits 420 passages within the unchanged 500-passage limit.
Duplicate content/metadata does not bump revisions. `var/corpus-import.json`
records actual source IDs and passage locations; raw uploads are never committed.
The original parsing/chunking library interfaces and mock tools remain available.

Acceptance: citation locations survive chunking; failed files never appear indexed.
Progress: `progress/member-b.md`.

## Person C — Retrieval and answers — edit only this section
- [x] Shared contracts, ports, and mock fixtures exist.
- [x] Retrieval, drafting, and verification stubs exist.
- [x] C1: Add local embeddings and backend-owned Qdrant persistence.
  - [x] Use Nomic for embeddings; retain Qwen for generation only.
  - [x] Implement the trained 512-dimensional MRL profile and index compatibility metadata.
  - [x] Persist documents, passage locations, and revisions; reject incomplete writes.
  - [x] Verify restart and compare 512/768 dimensions on eight synthetic development cases.
  - Integration is covered by the current full automated suite and real corpus import.
- [x] C2: Add BM25/semantic fusion, scope filters, and version counterparts.
  - [x] Add BM25 lexical ranking and fuse it with the C1 semantic results.
- [x] C3: Add grounded Qwen drafting, conflict/clarification logic, and optional benchmark tooling.
- [x] C4: Add verification/fallback and index B's passages; expose tools to D.
  - [x] Reject inapplicable or invalid claim citations; verify API fallback with mocks.
- [x] C5: Verify restart and complete live integration with D; ranking quality evaluation deferred.

Acceptance: retrieval respects scope and persists; answers cite evidence and fail clearly.
Progress: `progress/member-c.md`.

## Person D — FastAPI and evaluation — edit only this section
- [x] FastAPI routes, configuration, dependency factory, and mock orchestration exist.
- [x] One smoke test covers API/tool wiring, chat submission, and rerun behavior.
- [x] D1: Implement FastAPI endpoints, validation, errors, and health/readiness.
- [x] D2: Wire B/C tools through shared ports; manage startup and request concurrency.
- [x] D3: Label 25 questions from the supplied real corpus; freeze 8 held-out cases before tuning.
- [ ] D4: Integrate Ragas with explicitly local model and embedding providers.
- [ ] D5: Measure retrieval, faithfulness, citations, fallback, and latency.
- [ ] D6: Review grading; produce the report and five evidence-backed examples.
- [x] D7: Run API/acceptance checks and provide the live startup/demo runbook; evaluation report excluded.

Acceptance: the API integrates all modules with clear errors; evaluation is
reproducible, held-out results are separate, and metrics are real.
Progress: `progress/member-d.md`.
