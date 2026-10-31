# EvidenceDesk JSON contracts v1

Owner: Person C. Models: `src/evidencedesk/contracts/models.py`. Callable dependency
ports: `src/evidencedesk/contracts/ports.py`. Ask C before changing shapes.
Person D owns the FastAPI implementation and dependency wiring; C owns shared
contracts and retrieval/answer tools. D integrates B/C tools through these ports.
FastAPI exports the public schemas at `/openapi.json` and documents them at `/docs`.

## Live integration status

The API supports explicit `mock` and `live` modes without changing JSON keys.
The stub descriptions below apply to mock mode. Live mode wires validated uploads
to the committed Qdrant index, hybrid BM25/Nomic search, grounded Qwen drafting,
and semantic verification. `core/factory.py` owns these adapters and their close
hooks; shutdown drains work and closes the index/client. See `live-runbook.md`.
Health reports actual model availability, committed counts, and index readiness.
Readiness permits an empty healthy index; search on it returns `INDEX_EMPTY`.

Live ingestion enforces every documented file/batch/page/corpus limit. It uses
4,096-character chunks with 200-character overlap and groups adjacent HTML text
within each heading. A model length rejection retries that file at 1,800/200,
without truncation; failed retries never mark the file ready. Duplicate identity
includes content, format, and metadata, excluding filename. Distinct versions
remain distinct. Renaming with unchanged content/metadata does not bump revision.

Live verification first checks exact quotes, source IDs, scope applicability, and
conflict structure. It then asks local Qwen whether the statements follow from
the evidence. Failed/unclear checks withhold factual claims and conflicts; service
failures retain explicit error envelopes. No-fact fallbacks have no checks and
insufficient evidence strength. Model judgments are not a semantic guarantee or
a Ragas quality measurement. Public passage/source IDs remain stable; short IDs
used inside generation prompts are mapped back before returning any response.

## Conventions and envelope

All listed keys are required. Nullable values use explicit JSON null. Unknown
object keys are rejected. Requests are unwrapped; tool and API responses use the
same envelope. In shape blocks, quoted types describe values: `"Scope"` references
a named record, `"string|null"` means a nullable string, and `["Hit"]` means an
array of Hit objects. Those type expressions are not literal wire values.

Success (data is the actual output object):

```json
{"ok":true,"request_id":"req_example","data":{},"error":null}
```

Failure:

```json
{
  "ok":false,"request_id":"req_example","data":null,
  "error":{"code":"NOT_FOUND","message":"Document not found.","retryable":false}
}
```

Request IDs are opaque and vary per call. Tools take a typed request model and
return `Envelope[Output]`. Convert JSON with `model_validate` / `model_dump`.

| Error code | HTTP status |
|---|---|
| `BAD_INPUT`, `UNSUPPORTED_FORMAT`, `EMPTY_DOCUMENT` | 422 |
| `NOT_FOUND` | 404 |
| `INDEX_EMPTY`, `BUSY` | 409 |
| `EMBEDDING_UNAVAILABLE`, `MODEL_UNAVAILABLE` | 503 |
| `MODEL_TIMEOUT` | 504 |
| `INVALID_MODEL_OUTPUT` | 502 |
| `NOT_IMPLEMENTED` | 501 |
| `INTERNAL_ERROR` | 500 |

Tool calls have no HTTP status. A batch ingestion rejection is a per-file result
inside a successful HTTP 200 envelope. `NOT_IMPLEMENTED` explicitly identifies a
stub; it must never be reported as successful indexing.

## Shared shapes

```json
{
  "Scope":{"product":"string|null","version":"string|null","environment":"string|null"},
  "Metadata":{
    "title":"string","source_url":"string|null","product":"string|null",
    "version":"string|null","environment":"string|null","family_id":"string|null",
    "published_at":"string|null","origin":"public|synthetic|user"
  },
  "Document":{
    "document_id":"string","filename":"string","format":"pdf|html|markdown|txt",
    "metadata":"Metadata","sha256":"string","passage_count":"integer"
  },
  "Passage":{
    "passage_id":"string","document_id":"string","section_path":["string"],
    "page":"integer|null","text":"string"
  },
  "Hit":{
    "document":"Document","passage":"Passage","rank":"integer",
    "bm25_score":"number|null","cosine_score":"number|null","rrf_score":"number",
    "selection":"ranked|version_counterpart","applicable":"boolean"
  },
  "Support":{"passage_id":"string","quote":"string"},
  "Claim":{"claim_id":"string","text":"string","supports":["Support"]},
  "Conflict":{
    "conflict_id":"string","kind":"contradiction|version_difference","topic":"string",
    "sides":["Support"],"resolution":"unresolved|resolved_by_context",
    "selected_passage_ids":["string"]
  },
  "Clarification":{
    "field":"product|version|environment","question":"string","options":["string"]
  },
  "Draft":{
    "status":"answered|conflict|needs_context|not_found|insufficient_evidence",
    "claims":["Claim"],"conflicts":["Conflict"],"clarification":"Clarification|null",
    "fallback_reason":"no_support|weak_evidence|failed_verification|null"
  },
  "Check":{
    "target_type":"claim|conflict","target_id":"string","quote_valid":"boolean",
    "verdict":"supported|unsupported|unclear","reason":"string"
  },
  "Verification":{
    "passed":"boolean","evidence_strength":"strong|limited|insufficient","checks":["Check"]
  },
  "SearchResult":{"index_revision":"integer","hits":["Hit"],"warnings":["string"]},
  "QueryInput":{"question":"string","context":"Scope"},
  "Error":{"code":"enum in error table","message":"string","retryable":"boolean"}
}
```

Questions are trimmed and must have 1–2,000 characters. Claims have at least one
support; conflicts at least two sides; search at most six hits. Ranks/pages start
at 1; counts/revisions are nonnegative; numbers must be finite. Non-PDF pages are
null. IDs are opaque. Titles are nonempty. Publication dates are intended to use
`YYYY-MM-DD`; URL, date, and hash format validation is not implemented yet.

Target live semantics: exact quotes must occur in identified passages; claims
must have applicable support; unresolved contradictions stay visible. A missing
scope may require clarification. `not_found` uses `no_support`; insufficient
evidence carries no factual answer claims. These policies are integration tasks,
not all enforced by the mock skeleton.

## Tool 1: ingest_documents — B

```json
{
  "input":{
    "documents":[{"filename":"string","content_base64":"string","metadata":"Metadata"}]
  },
  "output":{
    "index_revision":"integer",
    "results":[{
      "filename":"string","state":"ready|duplicate|rejected","document_id":"string|null",
      "passage_count":"integer","error":"Error|null"
    }]
  }
}
```

`IngestInput` → `Envelope[IngestResult]`. Accept 1–20 file records. The stub returns
`rejected` / `NOT_IMPLEMENTED` for each; no decoding, parsing, saving, or indexing.
Target live limits: 10 MB decoded per file, 50 MB per batch, 100 PDF pages, and
500 corpus passages. All limits are enforced in live mode.

## Tool 2: search_passages — C

```json
{"input":"QueryInput","output":"SearchResult"}
```

`QueryInput` → `Envelope[SearchResult]`. The stub returns one synthetic source at
revision 1, with a warning that question and scope are ignored. No embedding or
Qdrant calls run. Live product/environment matching will be case-insensitive;
version matching exact. Version counterparts must retain real applicability.

## Tool 3: draft_answer — C

```json
{"input":{"query":"QueryInput","retrieval":"SearchResult"},"output":"Draft"}
```

`DraftInput` → `Envelope[Draft]`. The stub copies the first passage into a cited
claim, or returns `not_found` for no hits. No Ollama, conflicts, or clarification.

## Tool 4: verify_answer — C

```json
{
  "input":{"query":"QueryInput","retrieval":"SearchResult","draft":"Draft"},
  "output":"Verification"
}
```

`VerifyInput` → `Envelope[Verification]`. Deterministic checks require every claim
citation to identify a retrieved passage with a nonblank exact quote and
`applicable=true`. An exact quote from an inapplicable hit retains
`quote_valid=true`, but its claim verdict is `unsupported` and verification fails.
All claim checks must be supported for verification to pass. Success is labelled
`limited`; semantic support and conflicts are not evaluated. Empty claims produce
`passed=false` and no checks.

## Tool 5: read_sources — B

```json
{
  "input":{"document_id":"string|null"},
  "output":{"documents":["Document"],"passages":["Passage"]}
}
```

`SourcesInput` → `Envelope[SourcesResult]`. Null lists summaries without passages.
`doc_mock_guide` returns the fixture and passage. Unknown IDs return `NOT_FOUND`.
Synthetic fixtures never claim real public URLs.

## Internal model ports

Both use envelopes and have typed callable ports. The embedding port has an
opt-in Ollama adapter in `retrieval/embeddings.py`; see `docs/embeddings.md` for
validation, errors, and shared model locking. Generation uses the schema-constrained
Qwen adapter in `assistant/generation.py`. The API factory selects these only in live mode.

```json
{
  "EmbeddingInput":{"texts":["string"],"kind":"query|document"},
  "EmbeddingOutput":{
    "model":"string","model_digest":"string","dimensions":"integer","vectors":[["number"]]
  },
  "GenerationMessage":{"role":"system|user","content":"string"},
  "GenerationInput":{
    "messages":["GenerationMessage"],"response_schema":"JSON Schema object"
  },
  "GenerationOutput":{
    "model":"string","model_digest":"string","content":"JSON object",
    "prompt_tokens":"integer","completion_tokens":"integer","duration_ms":"integer"
  }
}
```

C owns the model ports. Generation uses `qwen3:4b`; embeddings use
`nomic-embed-text:v1.5` on the normal Ollama service at port 11434. The native
adapter adds `search_query:` or `search_document:` prefixes and validates the
model, digest, vector count, finite values, and declared dimensions. It produces
768-dimensional vectors. `CompactEmbeddings` applies the Nomic MRL transform
(layer normalization, leading dimensions, L2 normalization) to produce 512
dimensions by default. Stored profile metadata prevents mixing incompatible
dimensions or transforms. Model digest changes require a new/rebuilt index.
Truncation is disabled, and no alternative embedding model is selected on failure.
The JSON shapes are unchanged; `EmbeddingOutput.dimensions` reports the actual
output size. See `docs/embeddings.md` for indexing and the handoff to D.
Generation content must match the supplied JSON Schema. Future model adapters
share a request limiter. Never silently substitute a different model or mock.

## Public API

| Method / route | Request body | Success envelope data |
|---|---|---|
| `GET /v1/health` | none | `Health` |
| `POST /v1/documents:ingest` | `IngestInput` | `IngestResult` |
| `POST /v1/sources:read` | `SourcesInput` | `SourcesResult` |
| `POST /v1/search` | `QueryInput` | `SearchResult` |
| `POST /v1/query` | `QueryInput` | `QueryResult` |

```json
{
  "Health":{
    "mode":"mock|live","ready":"boolean","ollama_available":"boolean",
    "generation_model":"string","embedding_model":"string",
    "index_revision":"integer","document_count":"integer"
  },
  "TraceStep":{
    "step":"retrieve|draft|verify","status":"ok|skipped|error","duration_ms":"integer"
  },
  "QueryResult":{
    "mode":"mock|live","result":"Draft","retrieval":"SearchResult",
    "verification":"Verification","trace":["TraceStep"]
  }
}
```

Success returns HTTP 200. Invalid requests and tool errors use the envelope and
status table. Query calls search → draft → verify; a failed claim check replaces
the draft with `insufficient_evidence`. Timings are stub timings, not inference
benchmarks. Health `ready=true` means the mock is ready, not live services.

Concrete query/search body:

```json
{
  "question":"How do I reset my password?",
  "context":{"product":null,"version":null,"environment":null}
}
```

Concrete source-list body:

```json
{"document_id":null}
```

Concrete source-read body:

```json
{"document_id":"doc_mock_guide"}
```

Concrete ingestion body (valid shape, rejected by the stub):

```json
{
  "documents":[{
    "filename":"sample.txt","content_base64":"SGVsbG8=",
    "metadata":{
      "title":"Sample","source_url":null,"product":null,"version":null,
      "environment":null,"family_id":null,"published_at":null,"origin":"user"
    }
  }]
}
```

Concrete mock health response (request ID varies):

```json
{
  "ok":true,"request_id":"req_example",
  "data":{
    "mode":"mock","ready":true,"ollama_available":false,
    "generation_model":"qwen3:4b","embedding_model":"nomic-embed-text:v1.5",
    "index_revision":1,"document_count":1
  },
  "error":null
}
```

Use `/docs` to execute requests and inspect full nested responses. UI history is
display-only; v1 sends the latest question and explicit scope, not chat history.
The health example assumes `.env` uses the updated `.env.example` model values.
The existing default model names in `core/settings.py` already match this split.

## Internal C1 indexing interface

`QdrantIndex(path, CompactEmbeddings(native_embedder, dimensions=512))` owns one
local client. D constructs it once in the backend and closes it at shutdown;
UI processes must not open the same path. B supplies validated `Document` and
`Passage` records to `index_document(document, passages)`, which returns
`Envelope[IngestResult]` for one document using the existing JSON shapes.

`search(QueryInput)` returns `Envelope[SearchResult]` with at most six scoped
hybrid hits, including BM25/cosine scores and reciprocal rank fusion. Version
counterparts may be included for comparison but retain actual applicability.
Product/environment matching is case-insensitive; version matching is exact.
`read_sources(SourcesInput)` returns the existing source envelope. The live API
factory owns this index; explicitly selected mock mode retains the fixed fixture.
