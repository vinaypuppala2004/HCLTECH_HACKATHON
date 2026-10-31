# Enterprise corpus golden set

This dataset contains **25 answerable questions and reference answers authored from
the user's `enterprise-document-corpus.zip`**, prepared on 2026-10-31. It represents
all 16 documents: four Microsoft Azure HTML articles, four Microsoft Entra Markdown
guides, four OAuth PDF RFCs, and four OAuth TXT RFCs. It replaces synthetic examples
as the recommended source-grounded golden set; `synthetic-v1` stays unchanged for
its existing fixture tests.

## Files

| File | Use |
|---|---|
| `golden_set.md` | Read and review all 25 questions, reference answers, source links, locations, and grading notes. |
| `golden_set.jsonl` | All 25 rows projected to Ragas reference fields. Includes held-out labels; do not tune on this combined file. |
| `development.jsonl` | 17 development cases. |
| `heldout.jsonl` | 8 cases reserved for final evaluation. |
| `cases.json` | Canonical labels with case IDs, split, topic, exact evidence excerpts, and source locations. |
| `provenance.json` | Archive and manifest hashes; all 16 source IDs, original file hashes, publisher URLs, metadata, and extraction details. |
| `freeze.json` | Frozen label, provenance, and review-document hashes, plus held-out membership. |

The case mix is 14 direct, 7 scenario, 2 paraphrase, 1 multi-evidence, and 1 guidance
update. Both splits include all four formats. Related question topics stay in the
same split; the eight held-out cases cover seven independent topics. These labels
were frozen before tuning or running model evaluation on this set.

## Ragas fields and evaluation use

JSONL rows contain `user_input` (question), `reference` (gold answer),
`reference_contexts` (supporting source excerpts with whitespace collapsed), and
`reference_context_ids` (stable evidence identifiers). These names follow the
[Ragas SingleTurnSample schema](https://docs.ragas.io/en/stable/references/evaluation_schema/).
When Ragas is installed, a JSONL file can be loaded with
`EvaluationDataset.from_jsonl(path)`; this task does not install or configure Ragas.

During a later evaluation run, add the actual system `response` and actual
`retrieved_contexts` for each question. Do not copy gold answers into responses or
gold contexts into retrieved contexts: those are reference labels, not observations
of the RAG pipeline. No scores, measured latency, or saved system answers are
included here. The API still returns its existing mock data.

Reference IDs beginning with `ref_` identify these evidence excerpts. They are not
EvidenceDesk ingestion passage IDs. Person B/C must map evidence to actual chunks
by source hash and location before using metrics that compare chunk IDs. Text-based
reference contexts can be used without pretending that this mapping already exists.

## Source fidelity and review

- Answers are grounded in the supplied snapshots, not live account information or
  a claim that the publishers' current pages remain identical.
- Source IDs and metadata come from the archive manifest. Its 16 source-byte hashes
  were independently checked against archive contents. Original uploads are not
  copied into tracked project files. Licences/notices remain in the original archive;
  the dataset records excerpts and does not claim a new licence over source material.
- PDF page numbers are physical, one-based page numbers. Selected PDF pages were
  rendered and inspected. In particular, RFC 9700 section 2.4 on page 10 preserves
  the security-critical `MUST NOT` wording that plain extraction can displace.
- Each raw `quote` is an exact substring of the extracted source. HTML is parsed
  under `<main>` with scripts/styles/navigation omitted; Markdown/TXT line endings
  are normalized; PDF text uses pdfplumber 0.11.9 with the recorded settings.
- Line numbers refer to extracted text, or text within the cited PDF page, not raw
  HTML markup line numbers. Markdown directives and linked images are not treated
  as separately available source evidence.
- The RFC 6749/RFC 9700 case identifies updated security guidance, not an unresolved
  contradiction or interchangeable software versions. Billing questions explicitly
  distinguish MOSP from MCA/MPA roles. No question asks for private account balances.
- The set is assistant-authored and mechanically verified, with no independent
  human review claimed. A domain reviewer should review the gold labels before a
  final benchmark. Correcting frozen labels requires a new dataset version and
  review, rather than silently resealing them after seeing model results.

## Preparation checks

During authoring, all 16 source-byte hashes were checked against the archive
manifest. Each cited excerpt was re-extracted from the original archive and its
text and line location verified; selected PDF pages were also visually inspected.
The JSONL projections were checked against the canonical 25 labels, with split
membership and source coverage checked. Preparation used the bundled PDF runtime;
the dataset itself has no runtime dependency.

This delivery contains dataset files only. Pipeline testing and Ragas evaluation
are deferred. Intermediate extraction text and rendered pages remain under ignored
`var/evaluation/enterprise-corpus/`.
