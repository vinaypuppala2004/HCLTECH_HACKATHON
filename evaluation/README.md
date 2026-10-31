# Evaluation ownership

Person D owns the labelled dataset, Ragas integration, report, and demo examples.
Person D also owns the FastAPI backend and runtime wiring in `api/` and `core/`.
Ragas is planned, not installed or executed by the mock skeleton.

Plan 24 labelled questions: 8 direct, 6 paraphrase, 4 conflict/version, 3 ambiguous,
and 3 unsupported. Reserve 8 held-out questions before tuning. Report retrieval
Recall@5, citation integrity, faithfulness, context quality, fallback behavior,
and latency; manually review model-graded results.

Configure Ragas generation and embedding providers explicitly for local Ollama.
Keep evaluation outside the interactive query path. Mock results are not quality
measurements. Store generated reports and results under ignored `var/evaluation/`.
