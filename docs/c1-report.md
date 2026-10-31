# C1 synthetic development run — 2026-10-31

Model: `nomic-embed-text:v1.5`.
Digest: `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.

Eight synthetic passages and eight labelled questions cover passwords, shipping,
refunds, API keys, backups, sessions, MFA, and display language. They are defined
in `retrieval/check_c1.py`, separate from D's evaluation set. No tuning was done
against these results, and no Ragas or held-out scores are claimed.

| Measurement | 768 dimensions | 512 dimensions |
|---|---:|---:|
| Correct first result | 8/8 | 8/8 |
| Expected result in first three | 8/8 | 8/8 |
| Float32 bytes per vector | 3072 | 2048 |
| MRL processing for eight vectors | 0.586 ms | 0.492 ms |
| Index eight documents | 35.155 ms | 48.988 ms |
| Eight searches using cached real query vectors | 5.547 ms | 4.399 ms |
| Fresh-process live query after reopening | Passed | Passed |
| Exact source excerpt after reopening | Preserved | Preserved |

The native document embedding batch took 15740.387 ms; the native question batch
took 12225.317 ms. These include local HTTP/model work, and the first batch may
include model loading. Native vectors were generated once, then reused to isolate
the dimension-dependent processing and Qdrant timings. Restart checks generated
a fresh query embedding through Ollama in each new process.

The small timing sample does not establish a general latency improvement: the
512-dimensional index writes were slower in this run. The reason for the 512
default is lower vector storage with no observed ranking loss on these examples.
Reducing stored dimensions does not shorten Nomic's native forward pass.

The run created eight committed documents at revision 8 in each index. Artifacts
are in the ignored local directory
`var/c1-validation/20261031T084549Z-ac7a0d66/`, including `report.json` and both
Qdrant directories. Runtime data and model files are not committed.

Reproduction command, when checks are permitted again:

```powershell
.\.venv\Scripts\python.exe -m evidencedesk.retrieval.check_c1
```

Each run creates a new directory. It does not erase an existing index. The latest
cleanup and documentation changes have not been revalidated under the user's
current instruction to skip tests and checks.
