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
research runs. A retrieved evidence bundle references the selected corpus and
index together through `FilingCorpusVersion`. An in-memory manifest may lack an
index version while planning, but persistence requires the version and a corpus
ID computed from it. That ID remains unchanged through indexing and readiness;
a different index version creates a new corpus ID. Evidence excerpts carry the
source locator needed for citations. Vector matches retain Chroma's distance
unchanged, with lower values representing closer matches.

`app/agents/asset_thesis/rag/capabilities.py` defines the ports for parsing,
splitting, embeddings, raw-file storage, SQL metadata, and vector indexing.
`services.py` exposes independent ingestion and retrieval entry points for
future CLI commands, tests, evals, and graph nodes. Both methods currently
raise `NotImplementedError`. The existing `SecEdgarClient` now lives in
`app/market_data/sec_edgar_provider.py`; it is not wired into the production
graph. Company Facts and market quotes remain separate structured-data work.

Storage is now implemented. `FileRawFilingStore` preserves original SEC response
bytes under a SHA-256-derived path and checks the hash on read. Stable keys
include CIK, accession, and filename for document identity; chunks additionally
include their document version, parser/splitter versions, position, locator, and
text. A corpus key includes the selected document versions, `as_of`, and an
index version chosen before the manifest is stored. `SecEdgarClient.document()`
now returns the original response bytes.

`SqlFilingMetadataRepository` stores document versions, reusable chunks, corpus
membership, and the exact indexed chunk set in migration `002`. It rejects
conflicting writes and future-published or cross-issuer corpus members.
`ChromaFilingVectorIndex` stores caller-supplied embeddings in a persistent
collection per corpus/index version. `FilingCorpusStorageService` writes raw
documents and SQL metadata, then vectors, verifies the complete vector set,
and finally marks the corpus ready in SQL. Failed writes leave it indexing, so
the same inputs can be retried safely; conflicting vectors under the same
version are rejected. A ready corpus is exposed through the
storage service only while its complete vector set is present. Blocking Chroma
and filesystem operations run off the async event loop.

The storage paths are configurable with `SPIDER_AI_SEC_FILINGS_PATH` and
`SPIDER_AI_CHROMA_PATH`; the existing `SPIDER_AI_DB_PATH` holds the SQL records.
These adapters are independently callable and are not wired into the Thesis
graph. The next stage is parsing, splitting, embedding generation, and indexing
one real HTML filing through this storage boundary. The source HTML sample and
retrieval evaluation baseline remain work for that stage; no claim about RAG
quality follows from the storage tests.

Storage verification on 2026-10-10: isolated SQL/raw/Chroma tests cover
round trips, exhibit provenance, repeated writes, corpus isolation, byte
integrity, `as_of` filtering, incomplete coverage, and interrupted-write
recovery. The full test suite passed (518 passed, 11 skipped); targeted mypy
passed. Ruff passed for changed files. Repository-wide Ruff still reports the
pre-existing `UP042` in `app/domain/schemas/asset_snapshot.py`; with that
rule ignored, the whole `app/` and `tests/` tree passes. Chroma emits one
upstream Python 3.14 deprecation warning in the test suite.
