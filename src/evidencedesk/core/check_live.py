"""Exercise real Ollama, Qdrant, and API wiring with labelled synthetic documents."""

import argparse
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from evidencedesk.api.app import create_app
from evidencedesk.core.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-cases", action="store_true", help="Also run optional model scenarios."
    )
    args = parser.parse_args()
    Path("var").mkdir(exist_ok=True)
    results = {}
    with TemporaryDirectory(prefix="live-check-", dir="var") as directory:
        settings = Settings(app_mode="live", qdrant_path=directory)
        app = create_app(settings)
        with TestClient(app) as client:
            health = client.get("/v1/health").json()["data"]
            if not health["ready"]:
                raise RuntimeError("Ollama must have qwen3:4b and nomic-embed-text:v1.5 installed.")
            documents = []
            for filename, product, version, text in [
                (
                    "reset-v1.txt",
                    "Demo",
                    "v1",
                    "Reset your password in the account portal. "
                    "The reset link expires after 15 minutes.",
                ),
                (
                    "reset-v2.txt",
                    "Demo",
                    "v2",
                    "Reset your password in the recovery center. "
                    "The reset link expires after 30 minutes.",
                ),
                (
                    "policy-a.txt",
                    "ConflictDemo",
                    "v1",
                    "The production audit log retention period is exactly 30 days.",
                ),
                (
                    "policy-b.txt",
                    "ConflictDemo",
                    "v1",
                    "The production audit log retention period is exactly 90 days.",
                ),
            ]:
                documents.append(
                    {
                        "filename": filename,
                        "content_base64": base64.b64encode(text.encode()).decode(),
                        "metadata": {
                            "title": filename,
                            "source_url": None,
                            "product": product,
                            "version": version,
                            "environment": "production",
                            "family_id": product,
                            "published_at": None,
                            "origin": "synthetic",
                        },
                    }
                )
            ingested = client.post("/v1/documents:ingest", json={"documents": documents}).json()
            assert all(r["state"] == "ready" for r in ingested["data"]["results"]), ingested
            cases = [
                ("direct", "How do I reset my password?", "Demo", "v1", {"answered"}),
                (
                    "version",
                    "How long does the password reset link last?",
                    "Demo",
                    "v2",
                    {"answered"},
                ),
                (
                    "clarification",
                    "How long does the password reset link last?",
                    "Demo",
                    None,
                    {"needs_context"},
                ),
                (
                    "contradiction",
                    "What is the production audit log retention period?",
                    "ConflictDemo",
                    "v1",
                    {"conflict"},
                ),
                (
                    "unsupported",
                    "What is the company headquarters street address?",
                    "Demo",
                    "v1",
                    {"not_found", "insufficient_evidence"},
                ),
            ]
            for name, question, product, version, expected in (
                cases if args.all_cases else cases[:1]
            ):
                print(f"Checking {name}...", flush=True)
                response = client.post(
                    "/v1/query",
                    json={
                        "question": question,
                        "context": {
                            "product": product,
                            "version": version,
                            "environment": "production",
                        },
                    },
                )
                result = response.json()
                results[name] = result
                state = (
                    result["data"]["result"]["status"]
                    if result.get("data")
                    else result.get("error")
                )
                print(f"{name}: HTTP {response.status_code} / {state}", flush=True)
                Path("var/live-check.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8"
                )
                assert response.status_code == 200, result
                assert result["data"]["result"]["status"] in expected, result
            assert client.get("/v1/health").json()["data"]["document_count"] == 4
        # Reopening the same path verifies that the application released its writer lock.
        with TestClient(create_app(settings)) as restarted:
            health = restarted.get("/v1/health").json()["data"]
            assert health["document_count"] == 4 and health["index_revision"] == 4
            assert restarted.post("/v1/sources:read", json={"document_id": None}).json()["ok"]
    print(
        "Real live smoke and restart passed. "
        "Sources are synthetic; this is not a quality evaluation."
    )


if __name__ == "__main__":
    main()
