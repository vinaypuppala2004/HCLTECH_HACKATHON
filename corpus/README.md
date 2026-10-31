# Curated public source inventory

`manifest.json` records the 16 original documents from the user-supplied
`enterprise-document-corpus.zip`: four PDFs, four HTML snapshots, four Markdown
files, and four TXT RFCs. It retains URLs, timestamps, hashes, product, version,
family, and origin. License notices accompany the inventory. Raw archive contents,
uploads, models, and runtime Qdrant files are not committed.

The domains are OAuth standards, Microsoft Entra password reset, and Azure
billing/subscriptions/quotas. A different RFC is not automatically a replacement
version or a contradiction. Month-only publication dates stay separate from the
nullable exact publication date. Microsoft includes and text extraction can be
incomplete; inspect the original source when an excerpt lacks required context.

Import through the live backend:

```powershell
.\.venv\Scripts\python.exe -m evidencedesk.ingestion.import_corpus C:\path\enterprise-document-corpus.zip
```

The importer checks every hash and writes ignored `var/corpus-import.json` with
receipts and source-to-document/passage IDs, pages, headings, source line ranges,
and extracted-block offsets. The 4,096-character / 200-overlap profile initially
prepares 351 passages. Nomic rejects a token-dense RFC at that size; deterministic
1,800/200 rechunking indexes its complete text. The actual committed corpus has
**16 documents / 420 passages**. The importer verifies the alternate passage IDs
against the committed sources and records the compact profile in its report.

Adjacent HTML blocks group within headings; PDFs never cross pages. The library
default remains 1,200/200. These are size settings, not measured quality claims.
Unchanged content and metadata deduplicate even when the filename changes;
different versions/metadata retain separate identities.
