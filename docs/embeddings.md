# C1: Nomic embeddings and local Qdrant persistence

The current model split is `qwen3:4b` for generation and
`nomic-embed-text:v1.5` for embeddings. Both use the normal Ollama service at
`http://127.0.0.1:11434`. The experimental Qwen embedding launcher was removed,
and its task-owned background process was stopped. No existing `.env` was overwritten.

## Dimensions and model behavior

`OllamaEmbeddings` produces native 768-dimensional Nomic vectors. It prefixes
questions with `search_query: ` and passages with `search_document: `, while
leaving the stored source text unchanged. It disables silent truncation and
validates model identity, digest, dimensions, vector counts, and finite values.

`CompactEmbeddings` follows the model's Matryoshka profile: layer-normalize the
native vector, keep its leading dimensions, then L2-normalize. The implementation
centers all native dimensions before slicing; the layer-norm variance scale
cancels in the final normalization. The default stored dimension is **512**;
pass `dimensions=768` for the full transformed profile.

This reduces float32 vector storage from 3072 to 2048 bytes per passage. It does
not reduce the embedding model's forward-pass work. Native model width is 768;
it is no longer the 2560-dimensional raw Qwen experiment.

Reference: [Nomic task prefixes and dimensionality instructions](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5).

## Backend integration

```python
import httpx

from evidencedesk.contracts.models import QueryInput, Scope
from evidencedesk.retrieval.embeddings import OllamaEmbeddings
from evidencedesk.retrieval.index import QdrantIndex
from evidencedesk.retrieval.projection import CompactEmbeddings

with httpx.Client(base_url="http://127.0.0.1:11434", timeout=180, trust_env=False) as client:
    embed = CompactEmbeddings(OllamaEmbeddings(client), dimensions=512)
    with QdrantIndex("var/qdrant", embed) as index:
        # Person B supplies parsed Document and Passage records:
        # result = index.index_document(document, passages)
        response = index.search(QueryInput(
            question="How do I reset my password?",
            context=Scope(product=None, version=None, environment=None),
        ))
```

D owns API wiring and the lifetime of this single local client. B's parser calls
`index_document(document, passages)`, which returns the existing ingestion envelope
for one document. `search` and `read_sources` return the frozen search/source
envelopes. An empty index returns `INDEX_EMPTY`. No API JSON keys changed.

Product and environment filters are case-insensitive; versions match exactly.
Search returns at most six semantic hits with original document and passage
metadata. BM25, RRF fusion, and version counterparts are C2 work; current responses
carry an explicit semantic-only warning, null BM25 scores, and zero RRF scores.

## Persistence and failure handling

The index stores document metadata, source excerpts, locations, embedding profile,
model digest, and revision in Qdrant's local directory. Each replacement writes
a new passage generation before committing one state point. Searches consider
only committed generations. Interrupted writes remain invisible and are cleaned
up when reopened. Exact repeated indexing is idempotent and returns `duplicate`.

Indexing enforces unique passage IDs, correct document ownership/counts, nonblank
text, non-PDF null pages, and the 500-passage corpus limit. Model errors do not
commit a ready document. A Qdrant write error makes the instance unavailable until
closed/reopened so its committed state can be inspected.

Changing dimensions or the MRL profile requires a new index path or a deliberate
rebuild. Changing the embedding model digest is also rejected. The index never
silently overwrites a different profile. Close the local client before reopening
the path; a second simultaneous writer fails explicitly.

## Development evidence and current limits

Before the user's no-check instruction, 65 retrieval tests passed. A live Nomic
run compared 768 and 512 dimensions on eight labelled synthetic examples; both
returned the expected first result for all eight. Each index was then reopened
in a fresh Python process, and a new live query and exact source excerpt succeeded.
See `docs/c1-report.md` for the recorded measurements.

The latest cleanup/documentation edits were not retested or linted because the
user explicitly requested no further tests or checks. The default API remains
mock-only until D wires the live tools. These development examples are not Ragas
or held-out evaluation, and broader corpus quality remains D's evaluation work.
