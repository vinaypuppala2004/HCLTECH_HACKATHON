"""Reproducible live C1 smoke check on synthetic development examples, not held-out evaluation."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx

from evidencedesk.contracts.models import (
    Document,
    EmbeddingInput,
    EmbeddingOutput,
    Metadata,
    Passage,
    QueryInput,
    Scope,
    SourcesInput,
)
from evidencedesk.core.responses import success
from evidencedesk.retrieval.embeddings import OllamaEmbeddings
from evidencedesk.retrieval.index import QdrantIndex
from evidencedesk.retrieval.projection import CompactEmbeddings

_CASES = [
    ("password", "Use the account portal to reset your password.", "How do I reset my password?"),
    (
        "shipping",
        "Packages ship by courier within five business days.",
        "When will my package ship?",
    ),
    (
        "refund",
        "Refunds return to the original payment method within fourteen days.",
        "Where is a refund sent?",
    ),
    (
        "api-key",
        "Create an API key in the developer console under Secrets.",
        "Where can I create an API key?",
    ),
    (
        "backup",
        "Database backups run daily at 02:00 UTC and are retained for thirty days.",
        "How long are database backups kept?",
    ),
    (
        "session",
        "Sessions expire after thirty minutes of inactivity.",
        "When does an idle session expire?",
    ),
    (
        "mfa",
        "Enable multi-factor authentication in Security using an authenticator app.",
        "How do I turn on multi-factor authentication?",
    ),
    (
        "language",
        "Choose French or Spanish under Preferences, then Display language.",
        "Where do I change the display language?",
    ),
]


def _query(question: str) -> QueryInput:
    return QueryInput(
        question=question, context=Scope(product="Demo", version="v1", environment="test")
    )


def _document(label: str, text: str) -> tuple[Document, list[Passage]]:
    doc_id = f"c1_synthetic_{label}"
    document = Document(
        document_id=doc_id,
        filename=f"{label}.txt",
        format="txt",
        metadata=Metadata(
            title=f"Synthetic C1 example: {label}",
            source_url=None,
            product="Demo",
            version="v1",
            environment="test",
            family_id=doc_id,
            published_at=None,
            origin="synthetic",
        ),
        sha256=sha256(text.encode()).hexdigest(),
        passage_count=1,
    )
    return document, [
        Passage(
            passage_id=f"{doc_id}/1",
            document_id=doc_id,
            section_path=["Synthetic C1 fixture"],
            page=None,
            text=text,
        )
    ]


def _unwrap(response):
    if not response.ok or response.data is None:
        raise RuntimeError(response.model_dump_json())
    return response.data


def _restart(path: Path, dimensions: int, url: str) -> dict:
    with httpx.Client(base_url=url, timeout=180, trust_env=False) as client:
        embedder = CompactEmbeddings(OllamaEmbeddings(client), dimensions=dimensions)
        with QdrantIndex(path, embedder) as index:
            sources = _unwrap(index.read_sources(SourcesInput(document_id="c1_synthetic_password")))
            assert sources.passages[0].text == _CASES[0][1]
            result = _unwrap(index.search(_query(_CASES[0][2])))
            assert result.hits[0].document.document_id == "c1_synthetic_password"
            return {
                "revision": index.index_revision,
                "documents": index.document_count,
                "live_query_after_process_restart": True,
                "source_excerpt_preserved": True,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("var/c1-validation"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--restart", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--dimensions", type=int, default=512, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.restart is not None:
        print(json.dumps(_restart(args.restart, args.dimensions, args.ollama_url)))
        return
    run_path = args.output / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    run_path.mkdir(parents=True)
    document_texts = [text for _, text, _ in _CASES]
    questions = [question for _, _, question in _CASES]
    native_times = {}
    batches = {}
    with httpx.Client(base_url=args.ollama_url, timeout=180, trust_env=False) as client:
        native = OllamaEmbeddings(client)
        for kind, texts in [("document", document_texts), ("query", questions)]:
            started = perf_counter()
            batches[kind] = _unwrap(native(EmbeddingInput(texts=texts, kind=kind)))
            native_times[f"{kind}_batch_ms"] = round((perf_counter() - started) * 1000, 3)
    assert batches["document"].model_digest == batches["query"].model_digest

    def cached_native(request):
        # Cache contains real vectors produced above, separated by query/document prefix.
        pool = document_texts if request.kind == "document" else questions
        source = batches[request.kind]
        return success(
            EmbeddingOutput(
                model=source.model,
                model_digest=source.model_digest,
                dimensions=source.dimensions,
                vectors=[source.vectors[pool.index(text)] for text in request.texts],
            )
        )

    report = {
        "kind": "synthetic development smoke check; not Ragas or held-out evaluation",
        "cases": len(_CASES),
        "model": batches["document"].model,
        "model_digest": batches["document"].model_digest,
        "native_embedding_wall_time": native_times,
        "dimension_comparisons": {},
    }
    for dimensions in (768, 512):
        embedder = CompactEmbeddings(cached_native, dimensions=dimensions)
        started = perf_counter()
        _unwrap(embedder(EmbeddingInput(texts=document_texts, kind="document")))
        reduction_ms = (perf_counter() - started) * 1000
        path = run_path / f"qdrant-{dimensions}"
        with QdrantIndex(path, embedder) as index:
            started = perf_counter()
            for label, text, _ in _CASES:
                _unwrap(index.index_document(*_document(label, text)))
            write_ms = (perf_counter() - started) * 1000
            checks = []
            started = perf_counter()
            for label, _, question in _CASES:
                result = _unwrap(index.search(_query(question)))
                ids = [hit.document.document_id for hit in result.hits]
                expected = f"c1_synthetic_{label}"
                checks.append(
                    {
                        "question": question,
                        "expected": expected,
                        "top1": ids[0] if ids else None,
                        "top1_correct": bool(ids) and ids[0] == expected,
                        "in_top3": expected in ids[:3],
                    }
                )
            search_ms = (perf_counter() - started) * 1000
        child = subprocess.run(
            [
                sys.executable,
                "-m",
                "evidencedesk.retrieval.check_c1",
                "--restart",
                str(path),
                "--dimensions",
                str(dimensions),
                "--ollama-url",
                args.ollama_url,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )
        report["dimension_comparisons"][str(dimensions)] = {
            "vector_float32_bytes": dimensions * 4,
            "postprocess_batch_ms": round(reduction_ms, 3),
            "qdrant_index_batch_ms": round(write_ms, 3),
            "cached_real_vector_search_batch_ms": round(search_ms, 3),
            "top1_correct": sum(case["top1_correct"] for case in checks),
            "top3_correct": sum(case["in_top3"] for case in checks),
            "checks": checks,
            "restart": json.loads(child.stdout),
        }
    report_path = run_path / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), **report}, indent=2))


if __name__ == "__main__":
    main()
