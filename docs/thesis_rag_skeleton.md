# Thesis SEC filings RAG skeleton

The SEC filing RAG boundary now supports storage and explicit-document
ingestion. The parent Thesis graph and `ThesisDataPreparationGraph` stub remain
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
future CLI commands, tests, evals, and graph nodes. `ingest_documents` accepts
an explicit document selection and is implemented; automatic SEC corpus
selection through `ingest` and evidence retrieval still raise
`NotImplementedError`. The existing `SecEdgarClient` now lives in
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
Migration `003` backfills chunk plaintext and text-only `token_count` into
first-class `filing_chunk` columns for direct SQL access. The remaining chunk
metadata stays in `chunk_json`; new writes do not duplicate those two fields
there, and reads reconstruct the validated `FilingChunk` from both sources.
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
graph.

Stage 3 adds `SecHtmlFilingParser`, `SecFilingChunkSplitter`, and
`OllamaFilingEmbeddingGenerator`. The parser walks visible Inline XBRL HTML in
order, retains Part/Item/subsection headings, and serializes tables with their
period and unit rows. Blocks and chunks carry source locators; the exact SEC
response bytes remain in the raw store. The splitter groups paragraphs and
sentences within sections, splits long table rows, repeats table headers, and
applies bounded overlap. Its configuration changes the splitter version.
`FilingChunk.token_count` and overlap use text-only counts from the pinned
Nomic v1.5 BERT tokenizer. The splitter and embedding adapter share one local
counter. Document and query inputs use Nomic's `search_document:` and
`search_query:` prefixes exactly once; embedding limits include the complete
formatted text and BERT `[CLS]`/`[SEP]` tokens. Character limits also apply to
the complete embedding input. Tokenizer and Ollama truncation are disabled, so
oversized inputs fail explicitly. The splitter version includes the tokenizer
identity, pinned revision, counting rules, and chunk/embedding bounds. The
embedding version also changed because indexed vectors now use task prefixes.
Ready corpora are reused before parsing or embedding again; failed
embedding/indexing can be retried under the same key.

The tokenizer is [`nomic-ai/nomic-embed-text-v1.5`](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) at commit
`e9b6763023c676ca8431644204f50c2b100d9aab`. Ollama's published
[`nomic-embed-text:v1.5`](https://ollama.com/library/nomic-embed-text:v1.5) model links this Hugging Face model and reports a BERT
tokenizer with CLS ID 101, SEP ID 102, and a 30,522-token vocabulary. The
adapter accepts only published Nomic v1.5 Ollama model names. Exact token-count
parity with a running Ollama model has not been measured here because that
embedding model is not installed locally. Prefer the explicit `:v1.5` Ollama
tag over a mutable alias; advance `OLLAMA_EMBEDDING_MODEL_REVISION` when local
weights or model settings change.

After `uv sync`, download only the tokenizer assets once. This setup needs
network access; parsing, token counting, tests, and embedding-input validation
then use local files without embedding inference or tokenizer network calls:

```sh
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
from app.core.config import get_settings
from app.llm.tokenization import TOKENIZER_ID, TOKENIZER_REVISION

snapshot_download(
    repo_id=TOKENIZER_ID,
    revision=TOKENIZER_REVISION,
    cache_dir=str(get_settings().thesis_rag_tokenizer_cache_path),
    allow_patterns=[
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "vocab.txt",
    ],
)
PY
```

The compressed, unmodified Mastercard 2026-06-30 10-Q HTML in
`tests/fixtures/sec/MA/ma-20260630.html.gz` provides a reproducible real filing
fixture (uncompressed SHA-256:
`c961b20f1f5cf573bfff9e3c07d3c7cec712cc1b5523d464122fa666d509d7f7`).
Its SEC source is
`https://www.sec.gov/Archives/edgar/data/1141391/000114139126000083/ma-20260630.htm`.
The adjacent `metadata.json` supplies the asset, SEC document identifiers,
source URL, publication and reporting dates, and corpus `as_of` time. To add
another fixture, create a sibling folder containing an `.html.gz` file and a
matching `metadata.json`, then pass that folder name to `--fixture`. Inspect MA
without writing storage after tokenizer setup:

```sh
.venv/bin/python -m tests.rag.test_inspect_thesis_rag_cli --fixture MA --show 5
```

Add `--index` to store and index it using the fixture's `as_of` time. This
requires an installed Ollama embedding model (default `nomic-embed-text`) at
`OLLAMA_BASE_URL`; set `OLLAMA_EMBEDDING_MODEL` and
`OLLAMA_EMBEDDING_MODEL_REVISION` for the actual local model. Set
`OLLAMA_EMBEDDING_BATCH_SIZE`, `OLLAMA_EMBEDDING_MAX_INPUT_CHARS`,
`OLLAMA_EMBEDDING_MAX_INPUT_TOKENS`, `OLLAMA_EMBEDDING_EXPECTED_DIMENSIONS`,
`THESIS_RAG_CHUNK_MAX_CHARS`,
`THESIS_RAG_CHUNK_MAX_TOKENS`, `THESIS_RAG_CHUNK_OVERLAP_TOKENS`, and
`THESIS_RAG_TOKENIZER_CACHE_PATH` in `.env` to tune batching, chunking, and
the local tokenizer cache. The CLI injects those settings into both
components. Chunk limits must not exceed embedding input limits; invalid
combinations fail during configuration loading. Changing the input limits or
chunk settings changes the processing version and creates a new
corpus identity. The current implementation does not automatically discover or
select SEC filings, generate answers, or run retrieval evals. Those are later
stages. Parsing one filing preserves representative passages but does not
establish retrieval quality.

To write an explicit debug record of an indexing run, run:

```sh
.venv/bin/python -m tests.rag.test_inspect_thesis_rag_cli \
  --fixture MA --index --dump-debug --show 5
```

The flag is available only in `tests/rag/test_inspect_thesis_rag_cli.py`, defaults off,
and requires indexing. It creates a unique directory under
`tests/rag/rag_pipeline_test_runs/` with sanitized document metadata, parsed
blocks, chunk plaintext, counts, processing versions, timings, and embedding
and index summaries. Each run also writes `pipeline.log` with the RAG INFO,
DEBUG, and ERROR records, including a traceback on failure. The file handler
is removed after the run. No embedding arrays or credentials are written. Regular
application runs do not create these files.
RAG INFO logs report stage counts, durations, persistence and cache results;
DEBUG logs add bounded previews and token/split details. A run ID correlates
the stage records, and a failed operation logs one traceback before re-raising.

To prove a cold index and a warm cache hit without touching application storage,
add `--verify-cold-warm` to the debug command. The inspector creates temporary
SQL, raw-file, and Chroma stores, indexes the selected fixture, verifies vector
dimensions, finite values, and SQL/Chroma chunk IDs, then runs ingestion again
against the same stores. `summary.json` records cold and warm counts separately;
the temporary stores are removed after verification. A normal `--index` debug
run records `existing_chunks`, `newly_processed_chunks`, and `cache_hit`, so a
ready corpus is not mistaken for a fresh embedding run.
`OLLAMA_EMBEDDING_EXPECTED_DIMENSIONS` sets the expected vector width for this
verification (768 for the configured `nomic-embed-text` model).

Parser `sec-html-v2` walks Inline XBRL wrappers and nested tables in reading
order, records original DOM locations and table cell positions/spans, preserves
Note context across page furniture, and removes repeated numbered page footers.
Splitter `sec-structure-v4` attaches headings to content, distinguishes reusable
title/period/column/unit headers from row groups, and repeats the full header
plus only the active group when a size limit requires another chunk. Tables
that fit stay together across internal group headings. Separate HTML tables
share a header only when their column layout and section match and an explicit
continuation marker or matching continued title supports the link; adjacency
alone does not link them. Parser and splitter versions feed the
index version and corpus ID, so ready corpora from the earlier versions cannot
be reused for these outputs. Complex visual table layouts still need further
semantic interpretation; the parser preserves their cell coordinates rather
than inferring financial meaning from CSS.

On the MA fixture, the saved baseline run had 450 blocks, 304 chunks, 28
body-only locators, 56 heading-only chunks, and 44 retained page footers.
After these changes the local inspection yields 476 blocks, 251 chunks, zero
body-only locators, zero heading-only chunks, and zero retained page footers.
The formerly flattened revenue, contracts, and EPS tables are separate table
blocks; continued Note 3, Note 9, and Note 14 content retains its Note path.
The operations table keeps its period/year/unit header once per chunk, and
later exhibit chunks do not repeat records 4.1–4.3 as headers.

The subsequent `sec-structure-v4` MA inspection kept 476 parsed blocks and
reduced 251 chunks to 239. The two revenue row groups now fit in one table
chunk (previously two); the operations table uses two chunks (previously three),
each with its period, year and unit rows. An indexed inspection dump now reads
`document.json` from SQL after storage, so `raw_file_ref` points to the saved
HTML. The input document may still lack that reference before ingestion.

Storage verification on 2026-10-10: isolated SQL/raw/Chroma tests cover
round trips, exhibit provenance, repeated writes, corpus isolation, byte
integrity, `as_of` filtering, incomplete coverage, and interrupted-write
recovery. The full test suite passed (518 passed, 11 skipped); targeted mypy
passed. Ruff passed for changed files. Repository-wide Ruff still reports the
pre-existing `UP042` in `app/domain/schemas/asset_snapshot.py`; with that
rule ignored, the whole `app/` and `tests/` tree passes. Chroma emits one
upstream Python 3.14 deprecation warning in the test suite.
