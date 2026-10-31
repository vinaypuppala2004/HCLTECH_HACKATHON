"""Summarize observed outcomes and real metric values with explicit denominators."""

import math
import statistics
from collections import Counter
from pathlib import Path

from evaluation.run import POLICY, load_labels, read, save


def normalized(text):
    return " ".join(text.split())


def custom_metrics(case, observed, corpus):
    retrieval = observed["retrieval"]
    hits = retrieval["hits"] if retrieval else []
    target_sources = {e["source_sha256"] for e in case["evidence"]}
    retrieved_sources = {h["document"]["sha256"] for h in hits[:5]}
    mapped = []
    for evidence in case["evidence"]:
        quote = normalized(evidence["quote"])
        identifiers = [
            p["passage_id"]
            for document, p in corpus
            if document["sha256"] == evidence["source_sha256"]
            and (evidence["page"] is None or p["page"] == evidence["page"])
            and quote in normalized(p["text"])
        ]
        mapped.append(identifiers)
    top5 = {h["passage"]["passage_id"] for h in hits[:5]}
    recall = (
        sum(bool(top5 & set(ids)) for ids in mapped) / len(mapped)
        if mapped and all(mapped)
        else None
    )
    raw = observed["raw_api_response"]
    data = raw.get("data") if raw.get("ok") else None
    draft = data["result"] if data else None
    by_id = {h["passage"]["passage_id"]: h for h in hits}
    valid, count = 0, 0
    if draft:
        for claim in draft["claims"]:
            for support in claim["supports"]:
                count += 1
                hit = by_id.get(support["passage_id"])
                valid += bool(
                    hit
                    and hit["applicable"]
                    and support["quote"].strip()
                    and support["quote"] in hit["passage"]["text"]
                )
    return {
        "source_recall_at_5": len(target_sources & retrieved_sources) / len(target_sources),
        "exact_evidence_recall_at_5": recall,
        "reference_mapping": mapped,
        "mapped_reference_count": sum(bool(ids) for ids in mapped),
        "reference_count": len(mapped),
        "citation_count": count,
        "valid_citation_count": valid,
        "citation_integrity": valid / count if count else None,
    }


def aggregate(rows):
    output = {"cases": len(rows), "outcomes": dict(Counter(r["draft_status"] for r in rows))}
    answered = sum(r["draft_status"] == "answered" and bool(r["response"]) for r in rows)
    output["answered_cases"] = answered
    output["answer_coverage"] = answered / len(rows) if rows else None
    output["api_error_cases"] = sum(r["draft_status"] == "api_error" for r in rows)
    times = sorted(r["latency_ms"] for r in rows)
    output["latency_ms"] = {
        "mean": statistics.mean(times) if times else None,
        "p50": statistics.median(times) if times else None,
        "p95": times[math.ceil(0.95 * len(times)) - 1] if times else None,
    }
    output["ragas"] = {}
    for name in POLICY["metrics"]:
        entries = [r["ragas"][name] for r in rows]
        values = [e["value"] for e in entries if e["status"] == "ok"]
        output["ragas"][name] = {
            "mean": statistics.mean(values) if values else None,
            "scored_cases": len(values),
            "total_cases": len(rows),
            "statuses": dict(Counter(e["status"] for e in entries)),
        }
    custom = {}
    for name in ("source_recall_at_5", "exact_evidence_recall_at_5"):
        values = [r["checks"][name] for r in rows if r["checks"][name] is not None]
        custom[name] = {
            "mean": statistics.mean(values) if values else None,
            "scored_cases": len(values),
            "total_cases": len(rows),
        }
    citations = sum(r["checks"]["citation_count"] for r in rows)
    valid = sum(r["checks"]["valid_citation_count"] for r in rows)
    custom["citation_integrity"] = {
        "value": valid / citations if citations else None,
        "valid_citations": valid,
        "total_citations": citations,
    }
    output["checks"] = custom
    return output


def report(output):
    output = Path(output)
    cases, _, warnings = load_labels()
    snapshots = read(output / "source-passages.json")
    corpus = [
        (d, p) for source in snapshots for d in source["documents"] for p in source["passages"]
    ]
    rows = []
    for case in cases:
        observed = read(output / "observations" / case["split"] / (case["case_id"] + ".json"))
        scores = read(output / "scores" / case["split"] / (case["case_id"] + ".json"))
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "category": case["category"],
                "question": case["user_input"],
                "reference": case["reference"],
                "response": observed["response"],
                "draft_status": observed["draft_status"],
                "latency_ms": observed["latency_ms"],
                "http_status": observed["http_status"],
                "retrieved_contexts": observed["retrieved_contexts"],
                "ragas": scores["metrics"],
                "checks": custom_metrics(case, observed, corpus),
            }
        )
    import json

    for split in ("development", "heldout"):
        subset = [r for r in rows if r["split"] == split]
        (output / f"{split}-results.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, allow_nan=False) for r in subset) + "\n",
            encoding="utf-8",
        )
    summary = {
        "dataset": "enterprise-v1",
        "integrity_warnings": warnings,
        "all": aggregate(rows),
        "development": aggregate([r for r in rows if r["split"] == "development"]),
        "heldout": aggregate([r for r in rows if r["split"] == "heldout"]),
    }
    save(output / "summary.json", summary)
    lines = [
        "# EvidenceDesk local Ragas evaluation",
        "",
        "25 real pipeline observations; 17 development / 8 held-out, reported separately.",
        "",
        "## Integrity and method",
        "",
    ]
    lines += ["- " + warning for warning in warnings]
    if not warnings:
        lines.append(
            "- UTF-8 label, provenance, and review hashes match the original freeze manifest; "
            "held-out membership is unchanged."
        )
    lines += [
        "- The labels and application were not tuned during this evaluation. "
        "Results describe the saved current dataset snapshot.",
        "- Judge: local qwen3:4b; embeddings: local nomic-embed-text:v1.5. "
        "Digests and package versions are saved in manifests.",
        "- Unmodified Ragas 0.4.3 metric implementations/prompts. "
        "Answer relevancy uses one generated question (strictness=1).",
        "- Non-LLM context precision uses Ragas string similarity at its 0.5 threshold; "
        "different chunk/excerpt lengths can depress it. It is not LLM context precision.",
        "- Full actual retrieved passages were scored without truncation. "
        "Gold references were never sent to the application.",
        "- Missing factual answers have NA answer metrics and remain in coverage/outcome "
        "denominators. Metric failures are not zeros or successes.",
        "- The same small local model generates and judges, so scores have correlated errors. "
        "Gold labels are assistant-authored, not independently human-reviewed.",
        "- All 25 questions are answerable: abstentions here are missed answers; "
        "this set cannot measure correct rejection of unsupported questions.",
        "",
        "## Results",
        "",
        "| Metric | Development | Held-out |",
        "|---|---:|---:|",
    ]

    def show_metric(split, metric):
        item = summary[split]["ragas"][metric]
        value = f"{item['mean']:.4f}" if item["mean"] is not None else "NA"
        return f"{value} ({item['scored_cases']}/{item['total_cases']} scored)"

    for name in POLICY["metrics"]:
        lines.append(
            f"| Ragas {name} | {show_metric('development', name)} | "
            f"{show_metric('heldout', name)} |"
        )
    for split in ("development", "heldout"):
        item = summary[split]
        lines += [
            "",
            f"### {split.title()}",
            "",
            f"Answered: {item['answered_cases']}/{item['cases']}; outcomes: `{item['outcomes']}`.",
            f"Query latency (ms): `{item['latency_ms']}`.",
            f"Deterministic retrieval/citation checks: `{item['checks']}`.",
        ]
    lines += [
        "",
        "## Per-case outcomes",
        "",
        "| Case | Split | Outcome | Query seconds | Metric errors |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        errors = sum(v["status"] == "metric_error" for v in row["ragas"].values())
        lines.append(
            f"| {row['case_id']} | {row['split']} | {row['draft_status']} | "
            f"{row['latency_ms'] / 1000:.1f} | {errors} |"
        )
    lines += [
        "",
        "## Files",
        "",
        "- `development-results.jsonl` and `heldout-results.jsonl`: questions, references, "
        "actual responses, contexts, scores, errors, citation and retrieval checks.",
        "- `observations/`: untouched API envelopes and wall latency; "
        "`scores/`: individual metric results.",
        "- `judge-calls/`: structured grading details/reasons and token/timing metadata; "
        "`embedding-calls/`: local vector cache.",
        "- `manifest.json`, `metric-manifest.json`, source snapshots, and "
        "`requirements.lock`: reproducibility records.",
        "",
        "Metric definitions: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    save(
        output.parent / "latest.json",
        {"report": str(output / "report.md"), "summary": str(output / "summary.json")},
    )
    print(f"Saved report and results to {output}", flush=True)
