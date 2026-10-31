"""Collect real API responses once, score with local Ragas, and save auditable results."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep

import httpx

DATA = Path(__file__).parent / "data" / "enterprise-v1"
POLICY = {
    "version": 1,
    "scope": {"product": None, "version": None, "environment": None},
    "metrics": [
        "faithfulness",
        "context_recall",
        "context_precision_non_llm",
        "answer_relevancy",
        "semantic_similarity",
    ],
    "relevancy_strictness": 1,
    "non_llm_precision_threshold": 0.5,
    "judge": "qwen3:4b",
    "embeddings": "nomic-embed-text:v1.5",
    "workers": 1,
    "temperature": 0,
    "seed": 42,
    "empty_answer_policy": "NA for answer metrics; retained in answer-coverage denominator",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def load_labels():
    cases, provenance, freeze = (
        read(DATA / name) for name in ("cases.json", "provenance.json", "freeze.json")
    )
    if len(cases) != 25 or len({c["case_id"] for c in cases}) != 25:
        raise ValueError("Expected 25 distinct cases.")
    heldout = [c["case_id"] for c in cases if c["split"] == "heldout"]
    if heldout != freeze["heldout_case_ids"]:
        raise ValueError("Held-out membership differs from its recorded freeze.")
    if {c["topic_id"] for c in cases if c["split"] == "development"} & {
        c["topic_id"] for c in cases if c["split"] == "heldout"
    }:
        raise ValueError("Topic leakage between development and held-out cases.")
    warnings = []
    for name, value in (("cases", cases), ("provenance", provenance)):
        if digest(value) != freeze[name + "_sha256"]:
            warnings.append(
                f"Original {name} hash differs from freeze.json; "
                "original held-out integrity is not verified."
            )
    review = (DATA / "golden_set.md").read_text(encoding="utf-8")
    if digest(review) != freeze["review_sha256"]:
        warnings.append("Original review document differs from its freeze hash.")
    return cases, provenance, warnings


def api_post(client, route, payload):
    for attempt in range(12):
        response = client.post(route, json=payload)
        body = response.json()
        if response.status_code == 409 and body.get("error", {}).get("code") == "BUSY":
            sleep(5)
            continue
        return response.status_code, body
    raise RuntimeError("Backend remained busy; resume later without replacing saved observations.")


def collect(args):
    cases, provenance, warnings = load_labels()
    with httpx.Client(
        base_url=args.backend, timeout=httpx.Timeout(900, connect=5), trust_env=False
    ) as client:
        health = client.get("/v1/health").json()["data"]
        if health["mode"] != "live" or not health["ready"]:
            raise RuntimeError("Evaluation requires a ready live backend.")
        sources = client.post("/v1/sources:read", json={"document_id": None}).json()["data"]
        actual = {d["sha256"] for d in sources["documents"]}
        expected = {d["sha256"] for d in provenance["sources"]}
        if actual != expected:
            raise RuntimeError(
                "The indexed corpus does not exactly match the 16 evaluation source hashes."
            )
        with httpx.Client(base_url=args.ollama, timeout=5, trust_env=False) as ollama:
            tags = ollama.get("/api/tags").json()
        model_digests = {
            m["name"]: m["digest"]
            for m in tags["models"]
            if m["name"] in (POLICY["judge"], POLICY["embeddings"])
        }
        manifest = {
            "dataset_id": "enterprise-v1",
            "case_snapshot_sha256": digest(cases),
            "provenance_sha256": digest(provenance),
            "policy": POLICY,
            "policy_sha256": digest(POLICY),
            "backend": args.backend,
            "health": health,
            "model_digests": model_digests,
            "application_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "python": platform.python_version(),
            "integrity_warnings": warnings,
            "scope_note": "All scope fields null: labels do not specify user scope. "
            "No gold source metadata is supplied to the application.",
        }
        if (args.output / "manifest.json").exists():
            previous = read(args.output / "manifest.json")
            for key in ("case_snapshot_sha256", "policy_sha256", "model_digests", "health"):
                if previous[key] != manifest[key]:
                    raise RuntimeError(f"Cannot mix observations across changed {key}.")
        else:
            manifest["started_at_utc"] = datetime.now(timezone.utc).isoformat()
            save(args.output / "manifest.json", manifest)
            save(args.output / "source-inventory.json", sources)
            # Snapshot every committed passage for citation integrity and reference mapping.
            full = []
            for document in sources["documents"]:
                result = client.post(
                    "/v1/sources:read", json={"document_id": document["document_id"]}
                )
                result.raise_for_status()
                full.append(result.json()["data"])
            save(args.output / "source-passages.json", full)
        ordered = sorted(cases, key=lambda c: (c["split"] == "heldout", c["case_id"]))
        for number, case in enumerate(ordered, 1):
            path = args.output / "observations" / case["split"] / (case["case_id"] + ".json")
            if path.exists():
                continue
            print(f"Collecting {number}/25 {case['case_id']} ({case['split']})", flush=True)
            payload = {"question": case["user_input"], "context": POLICY["scope"]}
            started = perf_counter()
            status, body = api_post(client, "/v1/query", payload)
            latency = round((perf_counter() - started) * 1000)
            data = body.get("data") if body.get("ok") else None
            if data is not None:
                if (
                    data["mode"] != "live"
                    or data["retrieval"]["index_revision"] != health["index_revision"]
                ):
                    raise RuntimeError("Application mode/index changed during evaluation.")
                retrieval = data["retrieval"]
            else:
                search_status, search_body = api_post(client, "/v1/search", payload)
                retrieval = search_body.get("data") if search_status == 200 else None
            draft = data["result"] if data is not None else None
            response_text = (
                "\n".join(c["text"] for c in draft["claims"])
                if draft and draft["status"] == "answered"
                else ""
            )
            observation = {
                "case_id": case["case_id"],
                "split": case["split"],
                "question": case["user_input"],
                "scope": POLICY["scope"],
                "http_status": status,
                "latency_ms": latency,
                "raw_api_response": body,
                "draft_status": draft["status"] if draft else "api_error",
                "response": response_text,
                "retrieval": retrieval,
                "retrieved_contexts": [h["passage"]["text"] for h in retrieval["hits"]]
                if retrieval
                else [],
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            save(path, observation)
            print(
                f"Saved {case['case_id']}: {observation['draft_status']} ({latency / 1000:.1f}s)",
                flush=True,
            )
        save(
            args.output / "collection-complete.json",
            {
                "case_count": 25,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "health_after": client.get("/v1/health").json()["data"],
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["collect", "score", "report", "all"], default="all")
    parser.add_argument("--backend", default="http://127.0.0.1:8017")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    if args.phase in ("collect", "all"):
        collect(args)
    if args.phase in ("score", "all"):
        from evaluation.scoring import score

        score(args)
    if args.phase in ("report", "all"):
        from evaluation.reporting import report

        report(args.output)


if __name__ == "__main__":
    main()
