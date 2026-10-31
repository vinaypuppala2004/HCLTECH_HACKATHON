# Qwen-only embedding policy — Person C

The user requires **only `qwen3:4b`** for model calls. The embedding adapter is
locked to this model and never downloads or substitutes an alternative model.
The earlier Nomic adapter is superseded by this policy.

## What the local check showed

On 2026-10-31, `/api/show` for the installed Qwen model reported capabilities
`completion`, `tools`, and `thinking`. It did not advertise `embedding`.
A direct `/api/embed` request using `qwen3:4b` returned HTTP 501 with the message
"This server does not support embeddings. Start it with `--embeddings`".

Its metadata also reports `qwen3.embedding_length=2560`. That is an internal
model dimension; this value alone does not demonstrate a working embedding API.
The previous 768-dimensional Nomic vectors do not count as Qwen embeddings and
must not be indexed or reused under this policy.

The adapter therefore returns `EMBEDDING_UNAVAILABLE` on the current setup.
It checks capabilities before attempting `/api/embed`, so it does not send
unsupported requests or silently call another installed model.

## How retrieval can work with one model

BM25 ranks passages using their words and term frequencies. It does not call
an embedding model. Once lexical retrieval is implemented, `qwen3:4b` can write
an answer from the retrieved passages, and the verifier can check citations.

This is the next implementation step. Current API search and drafting remain
explicitly labelled mocks. Semantic ranking, Qdrant vector indexing, and Ragas
metrics requiring an embedding provider remain pending.

## Adapter behavior and handoff to Person D

`retrieval.embeddings.OllamaEmbeddings` still implements `EmbeddingPort` and uses
a caller-owned `httpx.Client` and shared request lock. Its model is hardcoded to
`qwen3:4b`; no model argument or settings value can redirect it to another model.

The adapter validates input, obtains the required model's digest from `/api/tags`,
then checks `/api/show`. Without the `embedding` capability it returns an explicit,
nonretryable error and releases the lock. If a future Qwen configuration advertises
embedding support, its declared architecture and embedding length determine the
required vector size. Inputs are sent unchanged for both query and document kinds;
Nomic-specific task prefixes are not used.

The remaining checks still reject wrong models, invalid dimensions, numeric strings,
booleans, nonfinite or zero vectors, wrong vector counts, and changing model digests.
Timeouts, connection errors, and busy locks retain their existing envelopes.
HTTP 501 is a nonretryable `EMBEDDING_UNAVAILABLE` error.

`.env.example` now sets both model fields to `qwen3:4b`. D owns
`core/settings.py` and must also update its two legacy embedding-model defaults.
Those defaults are not model calls, but the mock health endpoint can still display
the old name if no environment override is supplied. C has not edited D's files.
No existing `.env` was overwritten.

## Tests and limitations

HTTP simulations test both the unsupported-capability path and vector validation.
The success-path tests deliberately supply **synthetic** capability metadata and
small vectors; they do not claim that the installed Qwen model can embed.
A regression test includes an alternative installed embedding model and verifies
that it is never selected.

No successful Qwen embedding inference has been demonstrated. Local weights
downloaded for the superseded Nomic experiment have not been deleted; the new
adapter does not invoke them.

Reference: [Ollama embedding API](https://docs.ollama.com/api/embed).
