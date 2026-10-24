# Thesis SEC filings RAG skeleton

The SEC filing RAG boundary supports storage, explicit-document ingestion,
retrieval, and fixed-evidence analytical generation. The parent Thesis graph
and `ThesisDataPreparationGraph` stub remain
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
future CLI commands, tests, and graph nodes. `ingest_documents` accepts
an explicit document selection; automatic SEC corpus selection through `ingest`
still raises `NotImplementedError`. The existing `SecEdgarClient` now lives in
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
parity with a running Ollama model has not been measured here. Prefer the explicit `:v1.5` Ollama
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

Generation uses a separate tokenizer from Nomic: the configured Ollama chat
model is `qwen3:14b`, matched to `Qwen/Qwen3-14B` at commit
`40c069824f4251a91eefaf281ebe4c544efd3e18`. Install its tokenizer assets
into the same local cache once:

```sh
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
from app.core.config import get_settings

settings = get_settings()
snapshot_download(
    repo_id=settings.thesis_rag_chat_tokenizer_id,
    revision=settings.thesis_rag_chat_tokenizer_revision,
    cache_dir=str(settings.thesis_rag_tokenizer_cache_path),
    allow_patterns=[
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "vocab.json", "merges.txt",
    ],
)
PY
```

The counter loads only local assets, once per process. When
`OLLAMA_CHAT_MODEL` differs from `THESIS_RAG_CHAT_TOKENIZER_MODEL`, or the
matching pinned tokenizer is unavailable locally, the composition root uses
a model-labeled text-size estimate and a 512-token fallback margin. It does
not download assets at runtime. To regain local tokenizer counting after
changing the chat model, configure a matching Hugging Face tokenizer ID and
pinned revision, install its assets, and compare counts against Ollama.

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
select SEC filings. Parsing one
filing preserves representative passages but does not
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

## Retrieval and analytical generation

The baseline has three independently callable components under
`app/agents/asset_thesis/rag/`. `SecFilingRetrievalService.retrieve` accepts an
internal `FilingRetrievalRequest`: research ID, question, asset/CIK, exact
research `as_of`, selected corpus/index version, and `top_k`. It checks a ready
corpus, its selected asset/issuer/date, document publication times, and the
current Nomic embedding version before dense search. The
per-corpus Chroma collection provides the scope filter; only returned IDs are
batch-loaded as canonical SQL chunks. Retrieval does not rescan every indexed
chunk on each query. Dense mode preserves ascending Chroma L2 distance. The
configured `dense-lexical-v1` mode retrieves a bounded candidate set and
reranks its canonical text by query-term and adjacent-phrase overlap, using
dense rank as a small tie-breaker. It returns the final `top_k` and retains each
candidate's original distance. `THESIS_RAG_RETRIEVAL_RERANK_ENABLED=false`
reproduces the dense baseline; `THESIS_RAG_RETRIEVAL_CANDIDATE_K` controls the
candidate set separately from `THESIS_RAG_RETRIEVAL_TOP_K`. Results include a
`ranking_version` so comparisons remain explicit. Retrieval preserves
source identity, section path, period, URL, and DOM locator. A ready corpus has
indexed chunks; an empty dense-search response raises `NoVectorsFoundError` rather than
missing evidence. Missing stores and version mismatches also raise errors.
The Nomic adapter applies `search_query:` once and refuses truncation.

`SecFilingContextBuilder` deduplicates chunk IDs and whitespace-normalized
text in rank order, then packs complete chunks. It assigns `E1`, `E2`, ...
and retains a mapping to original ranked chunks. It counts the **entire**
prompt rendered by `ThesisFilingPromptBuilder`, including instructions,
question, source labels, metadata, context, and the generation model's
single-user chat template, against `OLLAMA_NUM_CTX` minus reserved output and a
safety margin. The structured-output schema is sent as Ollama's `format`
parameter; it did not add to `prompt_eval_count` in the configured model check.
With the matching assets, counts come from the pinned Qwen3 tokenizer, with
truncation disabled. The 128-token margin covers the measured Ollama template
difference. Fallback counts are estimates based on word/punctuation and UTF-8
byte counts; the 512-token margin covers unknown chat framing and estimation
drift but does not guarantee fit
for every other model or prompt. `FilingContextBudget.count_kind` records which
path was used.
Oversized chunks are excluded whole, never truncated. Chunk text already
contains its table headers, periods, units and section context.

`SecFilingAnalyticalGenerator` consumes only `FilingPackedContext` and returns
`FilingResearchAnswer` through the existing structured `BaseChatModelClient`.
The result separates a cited answer and supported factual claims from
interpretations, assumptions, uncertainties, and missing data. Each narrative
entry has structured `text` and `evidence_ids`; inline `E` labels must also
appear in that entry's IDs. It checks every citation against the packed `E`
map and returns an explicit
`insufficient_evidence` answer without an LLM call when nothing fits. Prompts
treat filing text as data, not instructions, and forbid financial arithmetic.
The `thesis-filing-grounded-v3` prompt shows only citation ID, form, publication
and reporting dates, and section in the model-facing source header. Full
document IDs, hashes, URLs, and HTML locators remain in the citation mapping.
Optional narrative lists may be empty; `partial_evidence` identifies a missing
requested component, while `answered` requires a cited answer and no missing
data. Numeric answers must state the reported unit, including table-scale
units. Citation IDs are validated in code against the packed mapping; semantic
support still requires review or evaluation.
If a model omits the optional answer field but supplies a cited supported
claim, validation uses the first such claim as the answer.
`SecFilingRagPipeline` composes the three services without LangGraph and
returns all stage outputs together as `FilingRagRun`: question, ranked excerpts,
packed context, response, references, corpus/parser/splitter/embedding/prompt/
model versions, and estimated input/output token diagnostics. The returned object can be
serialized for later evaluation without introducing a production dump writer.

The composition root wires shared settings into these constructors.
`THESIS_RAG_RETRIEVAL_TOP_K`,
`THESIS_RAG_RETRIEVAL_CANDIDATE_K`,
`THESIS_RAG_RETRIEVAL_RERANK_ENABLED`,
`THESIS_RAG_GENERATION_RESERVED_OUTPUT_TOKENS`,
`THESIS_RAG_GENERATION_SAFETY_MARGIN_TOKENS`,
`THESIS_RAG_GENERATION_FALLBACK_SAFETY_MARGIN_TOKENS`, chat tokenizer
identity/revision,
and `OLLAMA_NUM_CTX` live in
`.env.example`. The public request remains asset name/type. No Thesis graph
node calls this pipeline yet, and no Ragas suite was added.

Verify the local tokenizer against the exact LangChain/Ollama structured-output
call using two prompts and one output token per call:

```sh
.venv/bin/python -m tests.rag.test_verify_thesis_chat_tokenizer_cli
```

The command requires the matching local tokenizer and prints local counts,
Ollama `prompt_eval_count`, and differences;
it fails if a difference exceeds the configured safety margin. On the local
`qwen3:14b` model, the short request counted 10 locally versus 12 in Ollama;
the longer structured research prompt counted 1,223 versus 1,225. Re-run this check after changing
models, tokenizer revisions, or Ollama templates.

With the configured Ollama embedding and chat models available, run an
isolated live smoke test against the MA fixture:

```sh
.venv/bin/python -m tests.rag.test_thesis_rag_smoke_cli \
  --fixture MA \
  --question "What was Net Revenue for the three months ended June 30, 2026?" \
  --task answer --top-k 4 --json
```

The runner writes SQL, raw HTML and Chroma only in a temporary directory. Each
successful invocation saves one complete JSON report under
`tests/rag/rag_retrieval_test_runs/<report_id>.json`, including the fixture,
task, question, retrieval, packed context, answer, references and versions.
The directory is gitignored. `--json` prints that same report to stdout;
without it, the CLI prints a short summary and answer. The report path goes to
stderr. It does not create debug dump files. The existing
`--dump-debug` inspection flag remains the only path for persistent full
pipeline dumps under `tests/rag/rag_pipeline_test_runs/`. Offline tests cover
scope/version gating, SQL/Chroma retrieval, ranking, context budgets,
deduplication, empty evidence, and citation validation. An isolated live run
with the configured local Ollama models retrieved four chunks and returned the
cited answer “$9,277 million” for that question. This checks execution, not
retrieval quality or factual consistency across other questions. Exact chat
token parity across arbitrary prompts remains unverified; diagnostics identify
the local tokenizer and preserve the measured buffer. The updated live smoke
run packed four excerpts, counted 2,029 local prompt tokens, and returned the
cited answer `$9,277 million` with no optional narrative additions.

## Retrieval and generation quality check

The labeled `tests/fixtures/sec/MA/retrieval_cases.json` set distinguishes
similar revenue measures and three- versus six-month periods. It is a regression
example, not a cross-issuer quality estimate. Run the reproducible dense baseline
and the bounded reranker in isolated temporary SQL/Chroma stores with the local
Ollama embedding model:

```sh
.venv/bin/python -m tests.rag.test_thesis_rag_retrieval_eval_cli --fixture MA --top-k 4
.venv/bin/python -m tests.rag.test_thesis_rag_retrieval_eval_cli --fixture MA --top-k 4 --rerank
```

On the configured local Nomic model, six labeled questions had relevant evidence
within four dense results (coverage@4 = 6/6); first relevant ranks were
`2, 3, 1, 1, 3, 1` (MRR 0.694). With 16 dense candidates and four final
results, all six first relevant hits were rank 1 (coverage@4 = 6/6, MRR 1.0).
Thus the measured gain is ranking, not evidence coverage on this small fixture.
For the net-revenue question, dense rank 1 was a different $966 million revenue
measure; the $9,277 million table was rank 2 at L2 distance 0.365. Reranking
placed that table first while retaining the Chroma distance. The exact query
input was `search_query: What was Net Revenue for the three months ended June
30, 2026?` (21 Nomic tokens including special tokens); indexed chunks use one
`search_document:` prefix. The local Chroma default is L2. The corpus and query
had matching parser/splitter/embedding/index versions, so this was a dense
ranking issue rather than a scope or version mismatch. The configured embedding
revision is manually declared; a local Ollama tag digest is not checked on
every request.

The original CLI trace's four excerpts used 4,383 source-header characters out
of 6,730 total context characters (65.1%). With the compact headers, the same
excerpts use 745 header characters out of 3,092 (24.1%); the matching Qwen
tokenizer estimates 1,585 prompt tokens versus 3,632 for the earlier rendering.
Context packing and generation call the same prompt builder.

`tests/fixtures/sec/MA/generation_cases.json` holds fixed source excerpts so
generation can be checked separately from retrieval. Run, for example:

```sh
.venv/bin/python -m tests.rag.test_thesis_rag_generation_eval_cli \
  --fixture MA --case direct_net_revenue
```

The four fixed-context live cases returned the expected $9,277 million and
$966 million answers, a partial answer with the second requested metric missing,
and an insufficient-evidence result for an unrelated cover page. A full
retrieval-to-generation run with prompt v3 returned `$9,277 million` with a
valid evidence ID and empty optional lists. These outcomes demonstrate the
configured local models on this fixture, not general semantic grounding.
