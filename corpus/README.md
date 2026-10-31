# Corpus ownership

Person B owns curated sources and their provenance manifest. No public documents
have been downloaded yet. The running skeleton uses one synthetic in-memory
fixture in `src/evidencedesk/mocks/fixtures.py`.

Public sources proposed for later ingestion:

- Password authentication: [PostgreSQL 16](https://www.postgresql.org/docs/16/auth-password.html), [17](https://www.postgresql.org/docs/17/auth-password.html).
- Connection settings: [PostgreSQL 16](https://www.postgresql.org/docs/16/runtime-config-connection.html), [17](https://www.postgresql.org/docs/17/runtime-config-connection.html).
- ALTER ROLE: [PostgreSQL 16](https://www.postgresql.org/docs/16/sql-alterrole.html), [17](https://www.postgresql.org/docs/17/sql-alterrole.html).
- [Markdown README](https://raw.githubusercontent.com/postgres/postgres/REL_17_STABLE/README.md).
- [Plain-text copyright and licence](https://raw.githubusercontent.com/postgres/postgres/REL_17_STABLE/COPYRIGHT).

Preserve URLs, download timestamps, hashes, product/version metadata, and licence
notices. Label synthetic fixtures explicitly; different versions alone do not
establish a contradiction. Store runtime uploads in ignored `var/`.
