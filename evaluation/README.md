# Evaluation ownership

Person D owns the labelled dataset, Ragas integration, report, and demo examples.
Person D also owns the FastAPI backend and runtime wiring in `api/` and `core/`.
Ragas 0.4.3 is integrated as a separate local evaluation job. The application
environment and interactive request path do not import or execute Ragas.

## Run and stored outputs

### Fast direct review, without Ollama grading

The 2026-10-31 run collected all 25 real responses. At the user's request,
Ollama grading was stopped and the saved responses were reviewed directly.
`python -m evaluation.direct --output <saved-run-directory>` regenerates that
specific run's reviewed report and offline Ragas context precision, with no
Ollama calls. Stored review annotations are specific to those responses, not an
automatic judge for future runs. Assistant verdicts are explicitly separate from
Ragas scores; partial earlier model grades are preserved separately.

Stored report: `var/evaluation/enterprise-v1-ragas-20261031/report.md`.
Stable direct-review report/summary copies are retained beside it.

Use an isolated environment: Ragas needs a compatible LangChain 0.3 stack and
packaging 25, while the application keeps its original pinned lock. The complete
evaluation lock is `evaluation/requirements.lock`; do not install it over the
running application's environment.

```powershell
python -m venv var\ragas-venv
.\var\ragas-venv\Scripts\python.exe -m pip install -r evaluation/requirements.lock
.\var\ragas-venv\Scripts\python.exe -m pip install -e . --no-deps
.\var\ragas-venv\Scripts\python.exe -m evaluation.run --backend http://127.0.0.1:8017 --output var/evaluation/enterprise-v1-ragas-20261031
```

Ollama must have `qwen3:4b` and `nomic-embed-text:v1.5` installed. Both providers
use loopback HTTP with no cloud fallback. Ragas telemetry and LangChain tracing
are disabled. Native 768-dimensional Nomic query vectors score answer relevancy;
document vectors score semantic similarity. Production retrieval retains its
separate 512-dimensional stored profile.

The runner validates frozen UTF-8 label/provenance/review hashes, checks the exact
16 indexed source hashes, and records model digests and application/index state.
It collects 17 development responses followed by 8 held-out responses, with no
gold answers or source metadata supplied to the application. All query scope
fields are null because the dataset supplies no explicit user scope. It does not
tune or repair the application after seeing any held-out output.

Phases can be run separately with `--phase collect`, `--phase score`, and
`--phase report`. Existing observations and scores resume without replacement;
changed models, corpus, labels, or grading configuration cannot be mixed into
the same run. Reports/results stay in ignored `var/evaluation/`.

Artifacts include `report.md`, `summary.json`, separate development/held-out
results JSONL, complete API envelopes/latencies, source/passage snapshots, per-case
scores, structured judge outputs/reasons, embedding caches, model/configuration
manifests, and a dependency lock. `var/evaluation/latest.json` links the latest
finished report. Results are real observations, including failures and abstentions.

Metrics are Ragas Faithfulness, ContextRecall, non-LLM context precision with
reference (threshold 0.5), AnswerRelevancy (strictness 1), and SemanticSimilarity.
Ragas metric prompts/formulas are unchanged. Non-LLM precision is text similarity,
not the LLM-based precision metric; passage/excerpt length affects it. Additional
deterministic checks report source Recall@5, exact-quote evidence Recall@5 when
all references map unambiguously by source hash/text, citation integrity, outcome
coverage, and wall latency. Unmapped evidence is NA, not a fabricated passage ID.

No factual answer means NA for answer metrics, with the case retained in answer
coverage. Metric errors/undefined values stay explicit; no NaN/zero substitution
or exclusion without a denominator. Every dataset question is answerable, so this
set cannot measure correct rejection of unsupported questions. The same local
4B model drafts and judges: a human/domain review is still valuable, and scores
are not an independent guarantee of correctness.

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
