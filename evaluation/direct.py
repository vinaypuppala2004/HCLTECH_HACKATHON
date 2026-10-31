"""Finish saved-response evaluation offline with explicit assistant review provenance."""

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path

from evaluation.reporting import custom_metrics
from evaluation.run import digest, load_labels, read, save

REVIEWS = {
    "enterprise_01": (
        "partial",
        (
            "Correct reset portal, but omits the requested help-desk inst"
            "ruction when SSPR is disabled."
        ),
    ),
    "enterprise_02": (
        "correct",
        "Correctly denies reset/unlock with one registered method under a two-method policy.",
    ),
    "enterprise_04": (
        "non_answer",
        (
            "Repeats the two questions instead of answering two methods a"
            "nd security questions prohibited."
        ),
    ),
    "enterprise_05": (
        "incorrect",
        (
            "Lists generic end-user failure causes; misses checking the l"
            "icense of the administrator who cannot see the option."
        ),
    ),
    "enterprise_06": (
        "incorrect",
        (
            "Lists unrelated generic SSPR issues; does not address number"
            " formatting or unsupported phone extensions."
        ),
    ),
    "enterprise_07": (
        "correct",
        (
            "Both required outbound global-cloud HTTPS destinations match"
            " the reference and cited passage."
        ),
    ),
    "enterprise_08": (
        "incorrect",
        (
            "Uses 32002/32013 instead of listener-identification IDs 3103"
            "4/31019 and omits the Test-NetConnection command."
        ),
    ),
    "enterprise_09": (
        "correct",
        "Correctly states that pay-as-you-go subscriptions cannot enable the spending limit.",
    ),
    "enterprise_11": (
        "incorrect",
        (
            "Wrongly requires the account-admin role exclusively; its own"
            " quote allows Owner/Contributor/Reader with admin permission"
            "."
        ),
    ),
    "enterprise_12": (
        "correct",
        "Correct profile-level and billing-account-level roles and access scopes.",
    ),
    "enterprise_13": (
        "correct",
        (
            "Correct 24-hour reactivation limit and escalation after 30 m"
            "inutes following reactivation."
        ),
    ),
    "enterprise_14": (
        "non_answer",
        "Repeats the questions; does not state no request charge or no capacity guarantee.",
    ),
    "enterprise_21": (
        "partial",
        (
            "Mentions the access-token typ example but misses ID-token su"
            "bstitution prevention; an example alone does not establish i"
            "ts claimed normative requirement."
        ),
    ),
}


async def finish(output):
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    from ragas import SingleTurnSample
    from ragas.metrics import NonLLMContextPrecisionWithReference

    cases, _, warnings = load_labels()
    reviewed_hashes = read(Path(__file__).with_name("direct-review-observations.json"))
    manifest = read(output / "manifest.json")
    if manifest["case_snapshot_sha256"] != digest(cases):
        raise ValueError("Case snapshot changed.")
    full = read(output / "source-passages.json")
    corpus = [(d, p) for source in full for d in source["documents"] for p in source["passages"]]
    precision = NonLLMContextPrecisionWithReference(threshold=0.5)
    rows = []
    for case in cases:
        observed = read(output / "observations" / case["split"] / (case["case_id"] + ".json"))
        if digest(observed) != reviewed_hashes[case["case_id"]]:
            raise ValueError("Response differs from the reviewed observation; new review required.")
        if case["case_id"] in REVIEWS:
            verdict, reason = REVIEWS[case["case_id"]]
        else:
            if observed["draft_status"] == "answered":
                raise ValueError("An answered case has no direct review.")
            verdict, reason = (
                "abstained",
                "No factual answer returned for this answerable reference question.",
            )
        score = await precision.single_turn_ascore(
            SingleTurnSample(
                retrieved_contexts=observed["retrieved_contexts"],
                reference_contexts=case["reference_contexts"],
            )
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "question": case["user_input"],
                "reference": case["reference"],
                "response": observed["response"],
                "api_status": observed["draft_status"],
                "latency_ms": observed["latency_ms"],
                "assistant_review": {
                    "verdict": verdict,
                    "reason": reason,
                    "method": (
                        "Direct assistant inspection of response, reference, and cite"
                        "d excerpts; not an Ollama/Ragas judge score."
                    ),
                },
                "ragas_non_llm_context_precision": float(score),
                "checks": custom_metrics(case, observed, corpus),
                "observation_sha256": digest(observed),
            }
        )
    summary = {
        "mode": "direct_assistant_review_plus_offline_ragas_metric",
        "case_count": 25,
        "freeze_warnings": warnings,
        "ollama_grading": "Stopped at user request; original partial metrics retained separately.",
        "additional_ollama_calls": 0,
    }
    for split in ("all", "development", "heldout"):
        selected = rows if split == "all" else [r for r in rows if r["split"] == split]
        counts = Counter(r["assistant_review"]["verdict"] for r in selected)
        citations = sum(r["checks"]["citation_count"] for r in selected)
        valid = sum(r["checks"]["valid_citation_count"] for r in selected)
        recall = [
            r["checks"]["exact_evidence_recall_at_5"]
            for r in selected
            if r["checks"]["exact_evidence_recall_at_5"] is not None
        ]
        summary[split] = {
            "cases": len(selected),
            "review_outcomes": dict(counts),
            "strict_correct_fraction": counts["correct"] / len(selected),
            "api_answered_status_count": sum(r["api_status"] == "answered" for r in selected),
            "ragas_non_llm_context_precision_mean": sum(
                r["ragas_non_llm_context_precision"] for r in selected
            )
            / len(selected),
            "source_recall_at_5": sum(r["checks"]["source_recall_at_5"] for r in selected)
            / len(selected),
            "exact_evidence_recall_at_5": sum(recall) / len(recall) if recall else None,
            "exact_evidence_mapped_cases": len(recall),
            "citation_integrity": valid / citations if citations else None,
            "valid_citations": valid,
            "total_citations": citations,
            "mean_query_latency_ms": sum(r["latency_ms"] for r in selected) / len(selected),
        }
        if split != "all":
            (output / (split + "-results.jsonl")).write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in selected) + "\n",
                encoding="utf-8",
            )
    save(output / "summary.json", summary)
    save(output / "assistant-review.json", rows)
    lines = [
        "# EvidenceDesk evaluation results",
        "",
        "Completed using 25 saved live API observations: 17 development / 8 held-out.",
        "",
        "## Method",
        "",
        (
            "At the user's request, local Ollama grading was stopped. No "
            "further Ollama calls were made."
        ),
        (
            "Correctness verdicts below are direct assistant reviews, not"
            " Ragas LLM scores or independent human judgments."
        ),
        (
            "Ragas 0.4.3 non-LLM context precision was computed on all 25"
            " actual retrieved-context/reference-context pairs."
        ),
        (
            "The partial earlier Ollama/Ragas scores remain in scores/ an"
            "d partial-scores/; they are not generalized to all cases."
        ),
        (
            "Gold labels/application were unchanged. UTF-8 freeze hashes "
            "and split membership verified."
        ),
        "",
        "## Results",
        "",
        "| Measure | Development | Held-out | Overall |",
        "|---|---:|---:|---:|",
    ]
    for label, key in [
        ("Strict correct (assistant review)", "strict_correct_fraction"),
        ("Ragas non-LLM context precision", "ragas_non_llm_context_precision_mean"),
        ("Source Recall@5", "source_recall_at_5"),
        ("Exact-quote citation integrity", "citation_integrity"),
    ]:
        values = [
            f"{summary[s][key]:.4f}" if summary[s][key] is not None else "NA"
            for s in ("development", "heldout", "all")
        ]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    lines += [
        "",
        f"Review outcomes: `{summary['all']['review_outcomes']}`.",
        (
            "The API marked 13 cases answered, but two merely repeated qu"
            "estions. Citation matches do not prove correct answers."
        ),
        "All 25 labels are answerable, so the 12 abstentions are missed answers on this set.",
        "",
        "## Per-case review",
        "",
        "| Case | Split | Verdict | Review |",
        "|---|---|---|---|",
    ]
    for row in rows:
        review = row["assistant_review"]
        lines.append(
            f"| {row['case_id']} | {row['split']} | {review['verdict']} | {review['reason']} |"
        )
    lines += [
        "",
        "## Files and limits",
        "",
        (
            "- summary.json: split-level measured statistics and explicit"
            "ly labelled assistant verdicts."
        ),
        (
            "- development-results.jsonl / heldout-results.jsonl: actual "
            "responses, references, review reasons, offline Ragas values,"
            " and checks."
        ),
        "- assistant-review.json: all 25 reviews and observation hashes.",
        (
            "- observations/: complete original API outputs, retrieved pa"
            "ssages, and measured query latency."
        ),
        (
            "- scores/, partial-scores/, judge-calls/: preserved partial "
            "Ollama grading, not a completed 25-case Ragas LLM benchmark."
        ),
        "- manifests, source snapshots, requirements.lock: reproducibility records.",
        (
            "Non-LLM precision is string similarity at threshold 0.5 and "
            "is sensitive to passage/excerpt length."
        ),
        (
            "Exact-evidence recall is NA where references cannot be mappe"
            "d exactly; source Recall@5 remains separately available."
        ),
        "No unsupported-question rejection rate can be inferred from this all-answerable dataset.",
        "Direct assistant review is a rapid review, not independent human adjudication.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    save(
        output.parent / "latest.json",
        {"report": str(output / "report.md"), "summary": str(output / "summary.json")},
    )
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(finish(args.output))


if __name__ == "__main__":
    main()
