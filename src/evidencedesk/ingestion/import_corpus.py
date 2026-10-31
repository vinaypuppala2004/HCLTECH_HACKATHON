"""Verify a supplied corpus archive and ingest it through the public live API."""

import argparse
import base64
import json
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

import httpx

from evidencedesk.contracts.models import Envelope, IngestResult, Metadata
from evidencedesk.ingestion.chunking import COMPACT_CHUNKING, LIVE_CHUNKING, prepare_document


def inventory(archive: Path) -> tuple[dict, list[dict], list[dict]]:
    """Read only manifest-listed members; never extract archive paths to disk."""
    uploads, mapping = [], []
    with zipfile.ZipFile(archive) as bundle:
        manifests = [n for n in bundle.namelist() if n.endswith("/manifest.json")]
        if len(manifests) != 1:
            raise ValueError("Expected one corpus manifest.")
        manifest_name = manifests[0]
        prefix = manifest_name.removesuffix("manifest.json")
        if bundle.getinfo(manifest_name).file_size > 1024 * 1024:
            raise ValueError("Corpus manifest exceeds 1 MB.")
        manifest = json.loads(bundle.read(manifest_name))
        entries = manifest["documents"]
        if not 1 <= len(entries) <= 20 or sum(e["size_bytes"] for e in entries) > 50 * 1024 * 1024:
            raise ValueError("Corpus inventory exceeds the 20-file / 50 MB import limits.")
        for entry in entries:
            relative = PurePosixPath(entry["file"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid manifest member path.")
            member = prefix + str(relative)
            if bundle.getinfo(member).file_size > 10 * 1024 * 1024:
                raise ValueError("Corpus file exceeds 10 MB.")
            content = bundle.read(member)
            if sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError(f"Source hash mismatch: {entry['source_id']}")
            metadata = Metadata.model_validate(entry["metadata"])
            prepared = prepare_document(relative.name, content, metadata, config=LIVE_CHUNKING)
            mapping.append(
                {
                    "source_id": entry["source_id"],
                    "sha256": entry["sha256"],
                    "document_id": prepared.document.document_id,
                    "passages": [
                        {
                            "passage_id": c.passage.passage_id,
                            "page": c.passage.page,
                            "section_path": c.passage.section_path,
                            "start_line": c.start_line,
                            "end_line": c.end_line,
                            "block_index": c.block_index,
                            "start_offset": c.start_offset,
                            "end_offset": c.end_offset,
                        }
                        for c in prepared.chunks
                    ],
                    "warnings": list(prepared.warnings),
                }
            )
            uploads.append(
                {
                    "filename": relative.name,
                    "content_base64": base64.b64encode(content).decode(),
                    "metadata": metadata.model_dump(),
                }
            )
    return manifest, uploads, mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("var/corpus-import.json"))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    manifest, uploads, mapping = inventory(args.archive)
    count = sum(len(row["passages"]) for row in mapping)
    print(f"Verified {len(uploads)} sources and {count} passages.", flush=True)
    if count > 500:
        raise SystemExit("Corpus exceeds 500 passages. Import a smaller source selection.")
    if args.check_only:
        return
    with httpx.Client(base_url=args.backend, timeout=600, trust_env=False) as client:
        health = client.get("/v1/health")
        health.raise_for_status()
        if health.json()["data"]["mode"] != "live":
            raise SystemExit("Corpus import requires the live backend.")
        results = []
        for position, upload in enumerate(uploads):
            response = client.post("/v1/documents:ingest", json={"documents": [upload]})
            response.raise_for_status()
            receipt = Envelope[IngestResult].model_validate(response.json())
            if not receipt.ok or receipt.data is None:
                raise SystemExit("Corpus import failed; inspect the API error.")
            item = receipt.data.results[0]
            results.append(item.model_dump())
            if item.state != "rejected" and item.passage_count != len(
                mapping[position]["passages"]
            ):
                prepared = prepare_document(
                    upload["filename"],
                    base64.b64decode(upload["content_base64"]),
                    Metadata.model_validate(upload["metadata"]),
                    config=COMPACT_CHUNKING,
                )
                actual = client.post("/v1/sources:read", json={"document_id": item.document_id})
                actual.raise_for_status()
                if [p["passage_id"] for p in actual.json()["data"]["passages"]] != [
                    p.passage_id for p in prepared.passages
                ]:
                    raise SystemExit("Committed source IDs differ from the importer profile.")
                mapping[position]["passages"] = [
                    {
                        "passage_id": c.passage.passage_id,
                        "page": c.passage.page,
                        "section_path": c.passage.section_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "block_index": c.block_index,
                        "start_offset": c.start_offset,
                        "end_offset": c.end_offset,
                    }
                    for c in prepared.chunks
                ]
                mapping[position]["chunk_max_chars"] = COMPACT_CHUNKING.max_chars
            print(f"{item.filename}: {item.state} ({item.passage_count} passages)", flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "collection_id": manifest["collection_id"],
                    "results": results,
                    "sources": mapping,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if any(item["state"] == "rejected" for item in results):
            raise SystemExit("Some sources were rejected; see the import report.")


if __name__ == "__main__":
    main()
