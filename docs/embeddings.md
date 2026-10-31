# Qwen embeddings: runner setup and verification

Only **`qwen3:4b`** is used. The adapter does not download, substitute, or call
another model. Raw Qwen embeddings now work through an isolated local Ollama
process, while the regular Ollama process continues to handle generation.

## Why the earlier request failed

The installed Ollama 0.40.13 starts this model's default runner in generation
mode because its GGUF metadata has no pooling setting. `/api/embed` on that
runner returned HTTP 501 asking for embedding mode. The adapter also rejected
the model too early based on its `/api/show` capability list.

The fix starts another process with `LLAMA_ARG_EMBEDDINGS=1` and
`LLAMA_ARG_POOLING=last`. These are process-scoped settings: the existing chat
server and its configuration are not modified. Capability metadata still lists
`completion`, `tools`, and `thinking`, so the adapter now validates actual endpoint
output instead of treating a missing `embedding` label as conclusive.

Sources: [Ollama 0.40.13 runner startup and inherited environment](https://github.com/ollama/ollama/blob/v0.40.13/llm/llama_server.go),
[llama.cpp embedding and pooling settings](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Start the embedding process

Keep your regular Ollama service running. From the Person C worktree, start a
second terminal with:

```powershell
.\.venv\Scripts\python.exe -m evidencedesk.retrieval.embedding_server
```

On Linux/macOS use `.venv/bin/python`. If Ollama is not found, supply
`--ollama` with the installed executable's path. `--port` can select another
unprivileged loopback port except the standard chat port 11434.

| Purpose | URL | Model |
|---|---|---|
| Generation | `http://127.0.0.1:11434` | `qwen3:4b` |
| Raw embeddings | `http://127.0.0.1:11435` | `qwen3:4b` |

The launcher uses existing model storage, binds only loopback, refuses an occupied
port, and downloads no weights. Stop a foreground launcher with Ctrl+C. The adapter
uses CPU for embeddings to avoid consuming the generation model's GPU allocation.
It requests context 1024, batch 64, `truncate=false`, and one-minute keepalive.
Oversized passages must be split; they are not silently shortened.

## Use the adapter

```python
import httpx

from evidencedesk.contracts.models import EmbeddingInput
from evidencedesk.retrieval.embeddings import OllamaEmbeddings

with httpx.Client(base_url="http://127.0.0.1:11435", timeout=180, trust_env=False) as client:
    embed = OllamaEmbeddings(client)
    response = embed(EmbeddingInput(texts=["Reset my password"], kind="query"))
    if response.ok:
        assert response.data.model == "qwen3:4b"
        assert response.data.dimensions == 2560
        vector = response.data.vectors[0]
```

Queries and documents use unchanged text and the same pooling profile. The adapter
requires finite, nonzero vectors with the model's declared dimensions, one per
input in order. It checks the model name and digest, rejects digest changes during
a call, and retains explicit errors and shared request locking. An unconfigured
runner's HTTP 501 now includes the launcher command and embedding URL.

## Real verification on 2026-10-31

The project launcher plus adapter returned two synthetic passage vectors and one
query vector, all **2560-dimensional**, using model digest:

`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`

The regular service reported the same digest and completed a real generation
request with HTTP 200 afterward. A direct embedding probe also returned finite
vectors with norms approximately 1. These checks establish actual vector output
and generation compatibility; they do not establish retrieval accuracy.

## Limits and handoff to D

Last-token pooling takes a vector from the generation model's internal states.
This is an **experimental raw representation**, and the upstream embedding-mode
documentation targets dedicated embedding models. D must evaluate retrieval
quality before treating these vectors as a validated semantic-search solution.
Prior Nomic vectors cannot be reused: their model, dimensions, and profile differ.
Future index metadata must preserve the Qwen digest, pooling profile, and dimensions.

`.env.example` defines `EMBEDDING_OLLAMA_BASE_URL=http://127.0.0.1:11435`.
D must wire that client separately from `OLLAMA_BASE_URL`, retain startup/readiness
checks, and pass the same request lock to generation and embedding adapters.
D also owns the remaining legacy model defaults in `core/settings.py`; C has not
edited those files. No existing `.env` was overwritten.

The default API still uses labelled mock tools. Qdrant persistence, live retrieval,
grounded generation integration, and evaluation remain pending.
