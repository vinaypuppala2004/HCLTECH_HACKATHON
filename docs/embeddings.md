# Local embedding adapter — Person C

`retrieval.embeddings.OllamaEmbeddings` implements the existing `EmbeddingPort`.
It is opt-in: the default API and search still use explicitly labelled mocks.
No JSON contract, dependency pin, or Person D file changes are needed.

## What this step does

An embedding is a numeric representation of text. Later, semantic search will
compare a question's vector with passage vectors saved in Qdrant. This step
implements the text-to-vector boundary; persistence and ranking are separate tasks.

For this project the model is fixed to `nomic-embed-text:v1.5` and the vector length
is 768. Input order is preserved, so vector 0 belongs to text 0. Queries receive
`search_query: ` and passages receive `search_document: ` before being sent to
Ollama. The original passage text remains unchanged for citations.

The adapter reads `/api/tags` for the required model and its digest, then posts the
prefixed batch to `/api/embed` with `truncate=false`. A digest identifies the
installed model contents. Checking it before and after embedding detects a model
tag change during the operation; changed results are discarded. Future indexing
must also ensure that stored document vectors and query vectors use the same
model digest and dimensions.

Responses must contain one finite, nonzero, 768-dimensional vector per input.
Malformed JSON, a different model, numeric strings, booleans, missing vectors,
zero vectors, and nonfinite numbers are rejected. The adapter returns the frozen
success/error envelope and never substitutes random or mock embeddings.

## Handoff to Person D

Person D owns client startup/shutdown, settings, API wiring, and readiness. Create
one HTTP client with an explicit timeout and inject a shared model lock:

```python
from threading import Lock

import httpx

from evidencedesk.contracts.models import EmbeddingInput
from evidencedesk.retrieval.embeddings import OllamaEmbeddings

model_lock = Lock()  # Reuse this lock for the future generation adapter.
with httpx.Client(base_url="http://127.0.0.1:11434", timeout=180, trust_env=False) as client:
    embed = OllamaEmbeddings(client, request_lock=model_lock)
    response = embed(EmbeddingInput(texts=["How do I reset my password?"], kind="query"))
    if response.ok:
        vectors = response.data.vectors
    else:
        error = response.error
```

The caller owns the HTTP client; the adapter does not close it. With no explicit
lock, embedding adapter instances share a module-level lock. A busy lock returns
`BUSY` without waiting or calling Ollama. The lock is released on success and on
every error path. Passing the same lock to generation will allow at most one
model operation at a time.

| Condition | Error code | Retryable |
|---|---|---|
| Empty batch or blank text | `BAD_INPUT` | No |
| Required model missing | `EMBEDDING_UNAVAILABLE` | No; install the model first |
| Connection failure | `EMBEDDING_UNAVAILABLE` | Yes |
| HTTP 400, including oversized input | `BAD_INPUT` | No; fix or split the input |
| Lock occupied or HTTP 429 | `BUSY` | Yes |
| Timeout | `MODEL_TIMEOUT` | Yes |
| HTTP 5xx | `EMBEDDING_UNAVAILABLE` | Yes |
| Other HTTP errors | `EMBEDDING_UNAVAILABLE` | No |
| Malformed response or invalid vectors | `INVALID_MODEL_OUTPUT` | No |
| Model digest changes during the request | `INVALID_MODEL_OUTPUT` | Yes |

The required model must already be installed. An operator can install it with
`ollama pull nomic-embed-text:v1.5`. The adapter never downloads models itself.

## Verification and current limits

`tests/retrieval/test_embeddings.py` uses `httpx.MockTransport`: requests stay in
process and responses contain synthetic vectors. These tests verify prefixes,
ordering, model identity, validation, errors, and lock behavior; they do not
measure embedding quality or live inference latency.

A local check on 2026-10-31 first verified `EMBEDDING_UNAVAILABLE` while the
embedding model was absent, then installed `nomic-embed-text:v1.5` in Ollama storage.
The first request hit a 60-second timeout; Ollama's log reported about 48 seconds
of initial model startup. A subsequent check with a 180-second client timeout
succeeded. D should account for model warmup in readiness and choose the API
timeout policy. The adapter itself does not change the caller's timeout.

The successful check produced two passage vectors and one question vector, all
768-dimensional, with model digest
`0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
For the question "How can I reset my password?", the synthetic example passages
gave these illustrative cosine similarities:

| Synthetic passage | Cosine similarity |
|---|---|
| Use the account portal to reset your password. | 0.848697 |
| Packages are shipped by courier within five business days. | 0.365934 |

This is a live adapter demonstration, not a retrieval evaluation or accuracy score.
Qdrant storage, hybrid retrieval, and FastAPI integration remain pending.

References: [Ollama embedding API](https://docs.ollama.com/api/embed),
[Ollama model inventory](https://docs.ollama.com/api/tags),
[Nomic model instructions](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5).
