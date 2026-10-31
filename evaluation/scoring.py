"""Run actual Ragas metrics with local providers and preserve errors/NA explicitly."""

import asyncio
import importlib.metadata
import math
from pathlib import Path
from time import perf_counter

from evaluation.run import POLICY, digest, load_labels, read, save


async def score_async(args):
    from ragas import SingleTurnSample
    from ragas.metrics import NonLLMContextPrecisionWithReference
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextRecall,
        Faithfulness,
        SemanticSimilarity,
    )

    from evaluation.providers import LocalEmbeddings, LocalJudge, local_client

    manifest = read(args.output / "manifest.json")
    cases, _, _ = load_labels()
    if manifest["case_snapshot_sha256"] != digest(cases):
        raise RuntimeError("Case labels changed since observations were collected.")
    versions = {
        name: importlib.metadata.version(name)
        for name in ("ragas", "rapidfuzz", "httpx", "pydantic", "numpy")
    }
    metric_manifest = {
        "packages": versions,
        "policy": POLICY,
        "judge_context": 36864,
        "judge_max_output": 2048,
        "embedding_profile": "native Nomic 768; query prefixes for relevancy; "
        "document prefixes for answer similarity",
        "provider_sha256": digest(Path(__file__).with_name("providers.py").read_text()),
        "ragas_prompts": "Unmodified Ragas 0.4.3 metric prompts and formulas",
    }
    metric_manifest["sha256"] = digest(metric_manifest)
    old = args.output / "metric-manifest.json"
    if old.exists() and read(old) != metric_manifest:
        raise RuntimeError("Metric configuration changed. Use a new evaluation output directory.")
    save(old, metric_manifest)
    with local_client(args.ollama) as client:
        tags = {m["name"]: m["digest"] for m in client.get("/api/tags").json()["models"]}
        if any(tags.get(k) != v for k, v in manifest["model_digests"].items()):
            raise RuntimeError("A local model digest changed since collection.")
        judge = LocalJudge(client, args.output, tags[POLICY["judge"]])
        query_embeddings = LocalEmbeddings(client, args.output, tags[POLICY["embeddings"]])
        document_embeddings = LocalEmbeddings(
            client, args.output, tags[POLICY["embeddings"]], kind="document"
        )
        faithfulness = Faithfulness(llm=judge)
        recall = ContextRecall(llm=judge)
        precision = NonLLMContextPrecisionWithReference(threshold=0.5)
        relevancy = AnswerRelevancy(llm=judge, embeddings=query_embeddings, strictness=1)
        similarity = SemanticSimilarity(embeddings=document_embeddings)
        ordered = sorted(cases, key=lambda c: (c["split"] == "heldout", c["case_id"]))
        for number, case in enumerate(ordered, 1):
            path = args.output / "scores" / case["split"] / (case["case_id"] + ".json")
            if path.exists():
                continue
            observed = read(
                args.output / "observations" / case["split"] / (case["case_id"] + ".json")
            )
            question, response, contexts = (
                case["user_input"],
                observed["response"],
                observed["retrieved_contexts"],
            )
            row = {
                "case_id": case["case_id"],
                "split": case["split"],
                "metrics": {},
                "metric_manifest_sha256": metric_manifest["sha256"],
            }
            tasks = [
                (
                    "context_precision_non_llm",
                    lambda: precision.single_turn_ascore(
                        SingleTurnSample(
                            retrieved_contexts=contexts,
                            reference_contexts=case["reference_contexts"],
                        )
                    ),
                    bool(contexts),
                ),
                (
                    "context_recall",
                    lambda: recall.ascore(
                        user_input=question,
                        retrieved_contexts=contexts,
                        reference=case["reference"],
                    ),
                    bool(contexts),
                ),
                (
                    "faithfulness",
                    lambda: faithfulness.ascore(
                        user_input=question, response=response, retrieved_contexts=contexts
                    ),
                    bool(response and contexts),
                ),
                (
                    "answer_relevancy",
                    lambda: relevancy.ascore(user_input=question, response=response),
                    bool(response),
                ),
                (
                    "semantic_similarity",
                    lambda: similarity.ascore(reference=case["reference"], response=response),
                    bool(response),
                ),
            ]
            for name, call, applicable in tasks:
                if not applicable:
                    row["metrics"][name] = {
                        "value": None,
                        "status": "not_applicable",
                        "reason": "No factual answer or no retrieved contexts.",
                    }
                    continue
                print(f"Scoring {number}/25 {case['case_id']} {name}", flush=True)
                started = perf_counter()
                try:
                    result = await call()
                    value = float(result.value if hasattr(result, "value") else result)
                    row["metrics"][name] = {
                        "value": value if math.isfinite(value) else None,
                        "status": "ok" if math.isfinite(value) else "undefined",
                    }
                except Exception as exc:
                    row["metrics"][name] = {
                        "value": None,
                        "status": "metric_error",
                        "error_type": type(exc).__name__,
                        "reason": str(exc)[:1500],
                    }
                row["metrics"][name]["duration_ms"] = round((perf_counter() - started) * 1000)
                save(args.output / "partial-scores" / (case["case_id"] + ".json"), row)
            save(path, row)
            print(f"Saved scores {case['case_id']}", flush=True)


def score(args):
    asyncio.run(score_async(args))
