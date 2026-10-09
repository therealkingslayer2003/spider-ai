# Thesis SEC filings RAG skeleton

This stage defines the SEC filing RAG boundary without executing it. The
existing parent Thesis graph and `ThesisDataPreparationGraph` stub remain
unchanged; an ordinary Thesis request still returns 501.

`app/domain/schemas/thesis_rag.py` holds filing-document, parsed-block, chunk,
corpus-manifest, and retrieved-evidence contracts. One accession may contain a
primary HTML document and multiple exhibit documents, each with its own ID,
filename, source URL, and content version. `published_at` records when the
document became available; `report_period_end` is separate and optional. A
corpus manifest selects document versions at one `as_of` and is reusable across
research runs. Evidence excerpts carry the source locator needed for citations.

`app/agents/asset_thesis/rag/capabilities.py` defines the ports for parsing,
splitting, embeddings, raw-file storage, SQL metadata, and vector indexing.
`services.py` exposes independent ingestion and retrieval entry points for
future CLI commands, tests, evals, and graph nodes. Both methods currently
raise `NotImplementedError`. The existing `SecEdgarClient` now lives in
`app/market_data/sec_edgar_provider.py`; it is not wired into the production
graph. Company Facts and market quotes remain separate structured-data work.

The next task is storage: filesystem preservation of original HTML, focused
SQL records and corpus manifests, and a Chroma index keyed by chunk and corpus
versions. Implement idempotent writes and readiness transitions before parsing
or retrieval. The retained SEC client's `document()` method currently returns
decoded text; raw-byte preservation will require adapting that method when
the filesystem store is implemented. No Chroma dependency, migration, parser,
splitter, embedding call, retrieval algorithm, or generation path is added here.

Verification on 2026-10-08: `pytest -q` passed (511 passed, 11 skipped);
targeted Ruff and mypy checks passed; an import smoke check observed no client,
database, model, or filesystem setup.
