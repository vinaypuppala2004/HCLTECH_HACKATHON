# Evaluation ownership

Person D owns the labelled dataset, Ragas integration, report, and demo examples.
Person D also owns the FastAPI backend and runtime wiring in `api/` and `core/`.
Ragas is planned, not installed or executed by the mock skeleton.

## Real-document golden set (recommended)

The user supplied `enterprise-document-corpus.zip` on 2026-10-31. The new
[enterprise-v1 golden set](data/enterprise-v1/README.md) contains **25 answerable
questions** grounded in all 16 original public documents, with **17 development**
and **8 frozen held-out** cases. Read [the questions and reference answers](data/enterprise-v1/golden_set.md)
or use [the Ragas JSONL export](data/enterprise-v1/golden_set.jsonl).
Exact excerpts, source hashes, publisher URLs, and page/section locations are
included. No model outputs or scores are fabricated, and no Ragas providers were
integrated. `synthetic-v1` below remains an explicitly synthetic test fixture.

Plan 24 labelled questions: 8 direct, 6 paraphrase, 4 conflict/version, 3 ambiguous,
and 3 unsupported. Reserve 8 held-out questions before tuning. Report retrieval
Recall@5, citation integrity, faithfulness, context quality, fallback behavior,
and latency; manually review model-graded results.

Configure Ragas generation and embedding providers explicitly for local Ollama.
Keep evaluation outside the interactive query path. Mock results are not quality
measurements. Store generated reports and results under ignored `var/evaluation/`.

## D3 labelled fixture: synthetic-v1

`data/synthetic-v1/` contains **synthetic, evaluation-only** source snapshots and
labels. AtlasDesk and BorealDesk are invented products. None of these statements
describes a real product or a public document. The running API still uses its one
existing mock source; these files are not indexed or wired into the application.
This synthetic fixture predates the supplied archive; the real-document dataset
is now separately versioned as `enterprise-v1`. Runtime passage IDs from B's live
ingestion are still pending.

| Category | Development | Held out | Total |
|---|---:|---:|---:|
| Direct | 6 | 2 | 8 |
| Paraphrase | 4 | 2 | 6 |
| Conflict/version | 2 | 2 | 4 |
| Ambiguous | 2 | 1 | 3 |
| Unsupported | 2 | 1 | 3 |
| **Total** | **16** | **8** | **24** |

- `sources.json`: 6 synthetic document records and 19 passages in the shared
  `SourcesResult` shape. Each document's SHA-256 hashes its passage texts joined by
  a newline, in listed order. These are fixture snapshots, not downloaded files.
- `development.json`: the 16 cases available for future development and tuning.
- `heldout.json`: 8 cases frozen on **2026-10-31**, before any tuning or model
  evaluation. Related direct/paraphrase cases stay in the same split. The eight
  held-out cases cover six independent topic families, not eight independent topics.
- `freeze.json`: ordered held-out membership, held-out topic families, and SHA-256
  hashes of held-out labels and the complete source set. Hashes use canonical JSON
  (sorted keys, compact separators, UTF-8), so checkout line endings do not alter
  the freeze. An independent manifest hash is pinned in the acceptance test.

Every case records a stable case ID, topic `family_id`, category, contract-valid
query/context, expected `Draft`, relevant passage IDs, and a grading rationale.
The expected draft is a **gold label**, not a saved model response. Its claims give
the reference answer and exact evidence excerpts; passage IDs resolve to document
IDs and product/version/environment metadata in `sources.json`. Labels and schema
live only in `evaluation/`; no API or tool contract changes are involved.

Version differences select the explicitly requested version and retain both
excerpts. Contradictions within the same scope remain unresolved because the
fixture supplies no authority ordering. Ambiguous cases ask for version,
environment, or product before asserting facts. Unsupported cases have no claimed
support and expect `not_found` / `no_support` over this complete fixture corpus.
Both splits cover every category; topic families never cross the split boundary.
Automated integrity checks do not replace human review of semantic labels.

Run from the repository root using the existing Python environment:

```powershell
.\.venv\Scripts\python.exe -m evaluation.dataset
.\.venv\Scripts\python.exe -m pytest tests/acceptance/test_evaluation_dataset.py -q
```

`load_cases()` defaults to development and never reads held-out labels.
`load_cases("heldout")` is an explicit opt-in and checks the freeze first. The
validator reads both splits to check integrity but does not send labels to any
retriever or model. Do not tune prompts, retrieval, thresholds, or source content
against held-out questions or answers. Source material remains visible to retrieval
as in normal document Q&A; held-out questions and labels are reserved for final
evaluation. Any necessary correction to frozen content requires a new dataset
version and an explicit review, not resealing this fixture after observing results.

D3 adds data and integrity checks only. No Ragas integration, model/provider calls,
retrieval execution, scoring, latency measurement, or evaluation report is included.
The current mock pipeline cannot answer this fixture set; no quality result is
claimed. D4 and later tasks remain pending.
