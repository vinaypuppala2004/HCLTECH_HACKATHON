# EvidenceDesk JSON contracts v1

Owner: Person C. Models: `src/evidencedesk/contracts/models.py`. Callable dependency
ports: `src/evidencedesk/contracts/ports.py`. Ask C before changing shapes.
FastAPI exports the public schemas at `/openapi.json` and documents them at `/docs`.

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
500 corpus passages. Only the file count is enforced in this skeleton.

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

`VerifyInput` → `Envelope[Verification]`. Stub checks only claim quotation IDs and
nonempty exact substrings. Success is labelled `limited`. It does not evaluate
semantic support or conflicts. Empty claims produce `passed=false` and no checks.

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

## Internal model ports — planned

Both use envelopes and have typed callable ports, but no implementations yet.

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

C owns embeddings and generation. Target embeddings have 768 dimensions and
one vector per input in order, using `search_query:` / `search_document:` prefixes.
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
