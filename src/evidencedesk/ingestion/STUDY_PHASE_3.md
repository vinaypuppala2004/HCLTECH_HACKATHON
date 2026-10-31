# Phase 3 study checklist

Phase 3 implements B3 in `chunking.py`. It builds passages in memory; it does not
write to an index or enable live search. Start with the phase-2 parser concepts.

## Files changed in phase 3

| File | Purpose |
|---|---|
| `src/evidencedesk/ingestion/chunking.py` | Passage construction, overlap, stable IDs, and internal locations |
| `tests/ingestion/test_chunking.py` | 47 new test cases, including deterministic varied inputs |
| `src/evidencedesk/ingestion/README.md` | Behavior, limits, usage example, and identity rules |
| `src/evidencedesk/ingestion/STUDY_PHASE_2.md` | Previous phase's learning checklist |
| `plan.md` | Only Person B's phase/status notes |
| `progress/member-b.md` | Work, checks, and limitations |

## Topics to study

| Topic | What to understand | Code |
|---|---|---|
| Dataclasses and properties | Configuration, prepared results, and exposing existing contract records | `ChunkingConfig`, `LocatedPassage`, `PreparedDocument` |
| String slicing | Zero-based offsets and why the end offset is exclusive | `chunk_document` |
| Sliding windows | Size limits, overlap, and ensuring each iteration moves forward | `_spans` |
| Boundary selection | Paragraph/line/whitespace boundaries and hard splitting for long words | `_spans` |
| Source context | Why chunks stay within a source block, heading section, and PDF page | `chunk_document` |
| Citation locations | Exact text slices, original pages, and precise versus enclosing source line ranges | `_line_range`, `LocatedPassage` |
| Hashing | SHA-256 versus Python's process-dependent `hash()` | `_stable_id`, `prepare_document` |
| Canonical JSON | Sorted keys and stable serialization before hashing | `_stable_id` |
| Identity design | Same input gives stable IDs; metadata/version changes distinguish sources; renaming preserves identity | `prepare_document` |
| Frozen contracts | Internal location sidecars versus public Document and Passage fields | `PreparedDocument.passages`, shared models |
| Invariants and tests | Maximum size, exact overlap, full evidence coverage, unique IDs, and no cross-page chunks | `tests/ingestion/test_chunking.py` |

## Suggested exercises

1. Trace text `0123456789ABCDEFGHIJ` with size 8 and overlap 3. Expected offsets:
   `[0:8]`, `[5:13]`, `[10:18]`, `[15:20]`. Reconstruct the original without
   repeating the overlap.
2. Explain why a chunk's heading path is metadata rather than text prepended to
   the evidence.
3. Change size/overlap and explain why the document ID stays the same while
   passage IDs may change.
4. Rename a file, then change its version metadata. Explain the ID behavior.
5. Explain why a repeated paragraph must have different passage IDs at different
   locations, even when its text is identical.
6. Run the boundary, location, and ID tests separately, then the whole suite.

Defaults are 1,200 Unicode characters and 200 characters of overlap. They are not
token budgets or measured quality results. Exact overlap can start within a word.

```sh
.venv/bin/python -m pytest -q tests/ingestion/test_chunking.py
.venv/bin/python -m pytest -q tests/ingestion
```

Prompt for a new chat with this repository open:

> Teach me EvidenceDesk phase 3 from `src/evidencedesk/ingestion/chunking.py`
> and `tests/ingestion/test_chunking.py`. Follow `STUDY_PHASE_3.md`. Explain
> one topic at a time, trace small examples, then ask me a short question before
> continuing. Begin with string slicing and sliding-window overlap.
