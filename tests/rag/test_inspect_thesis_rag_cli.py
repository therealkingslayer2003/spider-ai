"""Development-only inspection of one local SEC HTML document.

Run with ``python -m tests.rag.test_inspect_thesis_rag_cli --help``.
"""

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, HttpUrl
from sqlalchemy import func, select

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.embeddings import OllamaFilingEmbeddingGenerator
from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.identity import make_document_id
from app.agents.asset_thesis.rag.observability import (
    current_run_id,
    log_failure_once,
    rag_run,
)
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.services import SecFilingIngestionService
from app.agents.asset_thesis.rag.splitter import (
    SecFilingChunkSplitter,
    SplitterSettings,
)
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.core.config import Settings, get_settings
from app.domain.schemas.thesis_rag import (
    Cik,
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingForm,
    FilingVectorMatch,
    Text,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from app.infrastructure.db.models import (
    FilingChunkModel,
    FilingCorpusChunkModel,
    FilingCorpusDocumentModel,
    FilingCorpusModel,
    FilingDocumentModel,
)
from app.llm.tokenization import NomicTokenCounter

DUMP_ROOT = Path(__file__).resolve().parent / "rag_pipeline_test_runs"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/sec"
logger = logging.getLogger(__name__)


class FixtureMetadata(BaseModel):
    asset: Text
    html_file: Text
    issuer_cik: Cik
    accession_number: Text
    filename: Text
    form: FilingForm
    source_url: HttpUrl
    published_at: AwareDatetime
    report_period_end: date | None = None
    as_of: AwareDatetime


def _load_fixture(name: str) -> tuple[FixtureMetadata, FilingDocument, bytes]:
    if name in {"", ".", ".."} or Path(name).name != name:
        raise ValueError("--fixture must name one folder under tests/fixtures/sec")
    fixture_dir = FIXTURE_ROOT / name
    metadata = FixtureMetadata.model_validate_json(
        (fixture_dir / "metadata.json").read_text(encoding="utf-8")
    )
    is_basename = Path(metadata.html_file).name == metadata.html_file
    if not is_basename or not metadata.html_file.endswith(".html.gz"):
        raise ValueError("metadata.html_file must be an .html.gz filename")
    with gzip.open(fixture_dir / metadata.html_file, "rb") as file:
        raw = file.read()
    document = FilingDocument(
        document_id=make_document_id(
            metadata.issuer_cik, metadata.accession_number, metadata.filename
        ),
        issuer_cik=metadata.issuer_cik,
        accession_number=metadata.accession_number,
        filename=metadata.filename,
        form=metadata.form,
        source_url=metadata.source_url,
        published_at=metadata.published_at,
        report_period_end=metadata.report_period_end,
    )
    return metadata, document, raw


class _RecordingEmbeddings:
    def __init__(self, delegate: OllamaFilingEmbeddingGenerator) -> None:
        self._delegate = delegate
        self.version = delegate.version
        self.summary: dict[str, Any] = {"calls": 0, "chunks": 0, "batches": 0}

    async def embed_chunks(self, chunks: Sequence[FilingChunk]) -> list[list[float]]:
        started = perf_counter()
        self.summary = {
            "calls": self.summary["calls"] + 1,
            "chunks": len(chunks),
            "batches": (len(chunks) + self._delegate.batch_size - 1)
            // self._delegate.batch_size,
            "status": "started",
        }
        try:
            vectors = await self._delegate.embed_chunks(chunks)
        except Exception as exc:
            self.summary.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "duration_ms": round((perf_counter() - started) * 1000, 1),
                }
            )
            raise
        self.summary.update(
            {
                "status": "completed",
                "dimensions": len(vectors[0]) if vectors else 0,
                "duration_ms": round((perf_counter() - started) * 1000, 1),
            }
        )
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        return await self._delegate.embed_query(query)


class _RecordingIndex:
    def __init__(self, delegate: ChromaFilingVectorIndex) -> None:
        self._delegate = delegate
        self.summary: dict[str, Any] = {"upsert_calls": 0, "vectors": 0}

    async def upsert(
        self, corpus: FilingCorpusManifest, vectors: Mapping[str, Sequence[float]]
    ) -> None:
        started = perf_counter()
        self.summary = {
            "upsert_calls": self.summary["upsert_calls"] + 1,
            "vectors": len(vectors),
            "status": "started",
        }
        try:
            await self._delegate.upsert(corpus, vectors)
        except Exception as exc:
            self.summary.update(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "duration_ms": round((perf_counter() - started) * 1000, 1),
                }
            )
            raise
        self.summary.update(
            {
                "status": "completed",
                "duration_ms": round((perf_counter() - started) * 1000, 1),
            }
        )

    async def contains_exactly(
        self, corpus: FilingCorpusManifest, chunk_ids: Sequence[str]
    ) -> bool:
        return await self._delegate.contains_exactly(corpus, chunk_ids)

    async def matches_vectors(
        self, corpus: FilingCorpusManifest, vectors: Mapping[str, Sequence[float]]
    ) -> bool:
        return await self._delegate.matches_vectors(corpus, vectors)

    async def search(
        self, corpus: FilingCorpusManifest, query_vector: Sequence[float], limit: int
    ) -> list[FilingVectorMatch]:
        return await self._delegate.search(corpus, query_vector, limit)


def _write_dump(directory: Path, name: str, value: Any) -> None:
    (directory / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


async def _sql_counts(database: Database) -> dict[str, int]:
    async with database.session_factory() as session:
        return {
            model.__tablename__: int(
                await session.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in (
                FilingDocumentModel,
                FilingChunkModel,
                FilingCorpusModel,
                FilingCorpusDocumentModel,
                FilingCorpusChunkModel,
            )
        }


def _vector_inventory(
    index: ChromaFilingVectorIndex,
    corpus: FilingCorpusManifest,
    expected_ids: set[str],
    expected_dimensions: int,
) -> int:
    collection = index._get_client().get_collection(
        name=index._collection_name(corpus), embedding_function=None
    )
    if collection.count() != len(expected_ids):
        raise RuntimeError("Chroma vector count differs from SQL chunk IDs")
    found: set[str] = set()
    ids = sorted(expected_ids)
    batch_size = index._get_client().get_max_batch_size()
    for start in range(0, len(ids), batch_size):
        result = collection.get(
            ids=ids[start : start + batch_size], include=["embeddings"]
        )
        vectors = result["embeddings"]
        if vectors is None or len(vectors) != len(result["ids"]):
            raise RuntimeError("Chroma returned an incomplete vector batch")
        for chunk_id, vector in zip(result["ids"], vectors, strict=True):
            if chunk_id in found:
                raise RuntimeError("Chroma returned a duplicate chunk ID")
            if len(vector) != expected_dimensions or not all(
                math.isfinite(float(value)) for value in vector
            ):
                raise RuntimeError("Chroma vector dimensions or values are invalid")
            found.add(chunk_id)
    if found != expected_ids:
        raise RuntimeError("SQL and Chroma chunk IDs differ")
    return len(found)


@contextmanager
def _capture_run_logs(directory: Path | None, run_id: str) -> Iterator[None]:
    if directory is None:
        yield
        return

    handler = logging.FileHandler(directory / "pipeline.log", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    handler.addFilter(lambda _record: current_run_id() == run_id)
    rag_logger = logging.getLogger("app.agents.asset_thesis.rag")
    previous_level = rag_logger.level
    rag_logger.addHandler(handler)
    logger.addHandler(handler)
    rag_logger.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        rag_logger.removeHandler(handler)
        rag_logger.setLevel(previous_level)
        handler.close()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", required=True, help="Folder name under tests/fixtures/sec"
    )
    parser.add_argument("--show", type=int, default=5, help="Number of chunks to print")
    parser.add_argument(
        "--index", action="store_true", help="Write SQL/Chroma and embed"
    )
    parser.add_argument(
        "--dump-debug",
        action="store_true",
        help="Write this indexing run's JSON dumps and pipeline.log under tests/rag/",
    )
    parser.add_argument(
        "--verify-cold-warm",
        action="store_true",
        help="Index twice in isolated temporary SQL/Chroma stores and verify reuse",
    )
    return parser.parse_args()


def _processing_components(
    settings: Settings,
) -> tuple[SecFilingChunkSplitter, OllamaFilingEmbeddingGenerator]:
    token_counter = NomicTokenCounter(settings.thesis_rag_tokenizer_cache_path)
    splitter = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=settings.thesis_rag_chunk_max_tokens,
            max_chars=settings.thesis_rag_chunk_max_chars,
            overlap_tokens=settings.thesis_rag_chunk_overlap_tokens,
            embedding_max_tokens=settings.ollama_embedding_max_input_tokens,
            embedding_max_chars=settings.ollama_embedding_max_input_chars,
        ),
        token_counter=token_counter,
    )
    embeddings = OllamaFilingEmbeddingGenerator(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
        model_revision=settings.ollama_embedding_model_revision,
        batch_size=settings.ollama_embedding_batch_size,
        max_input_chars=settings.ollama_embedding_max_input_chars,
        max_input_tokens=settings.ollama_embedding_max_input_tokens,
        token_counter=token_counter,
    )
    return splitter, embeddings


async def _run(args: argparse.Namespace) -> None:
    if args.dump_debug and not args.index:
        raise ValueError("--dump-debug requires --index")
    if args.verify_cold_warm and not (args.dump_debug and args.index):
        raise ValueError("--verify-cold-warm requires --index --dump-debug")
    run_id = uuid4().hex
    directory = DUMP_ROOT / run_id if args.dump_debug else None
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {"run_id": run_id, "status": "started"}
    observed_embeddings: _RecordingEmbeddings | None = None
    observed_index: _RecordingIndex | None = None
    with rag_run(run_id), _capture_run_logs(directory, run_id):
        try:
            settings = get_settings()
            fixture_metadata, document, raw = _load_fixture(args.fixture)
            source = urlsplit(str(document.source_url))
            safe_url = urlunsplit(
                (source.scheme, source.hostname or "", source.path, "", "")
            )
            if directory is not None:
                _write_dump(
                    directory,
                    "document.json",
                    {
                        **document.model_dump(mode="json", exclude={"source_url"}),
                        "source_url": safe_url,
                        "raw_bytes": len(raw),
                        "content_sha256": hashlib.sha256(raw).hexdigest(),
                    },
                )
            parser = SecHtmlFilingParser()
            splitter, embeddings = _processing_components(settings)
            observed_embeddings = (
                _RecordingEmbeddings(embeddings) if directory is not None else None
            )
            service = SecFilingIngestionService(
                None, parser, splitter, observed_embeddings or embeddings
            )
            started = perf_counter()
            parsed, chunks = await service.inspect_document(document, raw)
            summary.update(
                {
                    "documents": 1,
                    "blocks": len(parsed.blocks),
                    "chunks": len(chunks),
                    "text_tokens": sum(chunk.token_count for chunk in chunks),
                    "parser_version": parsed.parser_version,
                    "splitter_version": splitter.version,
                    "embedding_version": embeddings.version,
                    "inspection_ms": round((perf_counter() - started) * 1000, 1),
                }
            )
            if directory is not None:
                _write_dump(
                    directory,
                    "parsed_blocks.json",
                    [block.model_dump(mode="json") for block in parsed.blocks],
                )
                _write_dump(
                    directory,
                    "chunks.json",
                    [chunk.model_dump(mode="json") for chunk in chunks],
                )
            print(f"Document: {safe_url}")
            print(f"Published: {document.published_at}")
            print(f"Period: {document.report_period_end}")
            print(f"Parser: {parsed.parser_version}; splitter: {splitter.version}")
            print(f"Blocks: {len(parsed.blocks)}; chunks: {len(chunks)}")
            for chunk in chunks[: args.show]:
                print(
                    f"\n[{chunk.position}] {chunk.token_count} text tokens "
                    f"| {' > '.join(chunk.section_path)} | {chunk.source_locator}"
                )
                print(chunk.text)
            if args.index:
                storage_context = (
                    TemporaryDirectory(prefix="thesis_rag_verify_")
                    if args.verify_cold_warm
                    else nullcontext(None)
                )
                with storage_context as isolated_root:
                    root = Path(isolated_root) if isolated_root is not None else None
                    db_path = (
                        root / "filings.db" if root else settings.spider_ai_db_path
                    )
                    raw_path = (
                        root / "raw" if root else settings.spider_ai_sec_filings_path
                    )
                    chroma_path = (
                        root / "chroma" if root else settings.spider_ai_chroma_path
                    )
                    database = Database(db_path)
                    try:
                        metadata = SqlFilingMetadataRepository(database)
                        vector_index = ChromaFilingVectorIndex(chroma_path)
                        observed_index = (
                            _RecordingIndex(vector_index)
                            if directory is not None
                            else None
                        )
                        storage = FilingCorpusStorageService(
                            FileRawFilingStore(raw_path),
                            metadata,
                            observed_index or vector_index,
                        )
                        service = SecFilingIngestionService(
                            storage,
                            parser,
                            splitter,
                            observed_embeddings or embeddings,
                        )
                        started = perf_counter()
                        corpus = await service.ingest_documents(
                            asset=fixture_metadata.asset,
                            as_of=fixture_metadata.as_of,
                            documents=[(document, raw)],
                        )
                        if directory is not None:
                            stored_document = await metadata.get_document(
                                corpus.documents[0]
                            )
                            if (
                                stored_document is None
                                or stored_document.raw_file_ref is None
                            ):
                                raise RuntimeError(
                                    "Indexed document has no saved raw HTML reference"
                                )
                            _write_dump(
                                directory,
                                "document.json",
                                {
                                    **stored_document.model_dump(
                                        mode="json", exclude={"source_url"}
                                    ),
                                    "source_url": safe_url,
                                    "raw_bytes": len(raw),
                                },
                            )
                        chunk_ids = await metadata.get_indexed_chunk_ids(
                            corpus.corpus_id
                        )
                        newly_indexed = bool(
                            observed_embeddings and observed_embeddings.summary["calls"]
                        )
                        summary.update(
                            {
                                "corpus_id": corpus.corpus_id,
                                "index_version": corpus.index_version,
                                "corpus_status": corpus.status,
                                "indexed_chunks": len(chunk_ids),
                                "existing_chunks": (
                                    0 if newly_indexed else len(chunk_ids)
                                ),
                                "newly_processed_chunks": (
                                    len(chunk_ids) if newly_indexed else 0
                                ),
                                "cache_hit": not newly_indexed,
                                "ingestion_ms": round(
                                    (perf_counter() - started) * 1000, 1
                                ),
                            }
                        )
                        if args.verify_cold_warm:
                            assert observed_embeddings is not None
                            assert observed_index is not None
                            dimensions = observed_embeddings.summary.get(
                                "dimensions", 0
                            )
                            if (
                                dimensions
                                != settings.ollama_embedding_expected_dimensions
                            ):
                                raise RuntimeError(
                                    "Cold embedding dimension differs from "
                                    "OLLAMA_EMBEDDING_EXPECTED_DIMENSIONS"
                                )
                            if (
                                observed_embeddings.summary["calls"] != 1
                                or observed_index.summary["upsert_calls"] != 1
                                or len(chunk_ids) != len(set(chunk_ids))
                                or len(await metadata.get_chunks(chunk_ids))
                                != len(chunk_ids)
                            ):
                                raise RuntimeError("Cold indexing did not complete")
                            vector_count = await asyncio.to_thread(
                                _vector_inventory,
                                vector_index,
                                corpus,
                                set(chunk_ids),
                                dimensions,
                            )
                            cold_sql = await _sql_counts(database)
                            stored_doc = await metadata.get_document(
                                corpus.documents[0]
                            )
                            assert stored_doc is not None
                            assert stored_doc.raw_file_ref is not None
                            raw_file = raw_path / stored_doc.raw_file_ref
                            raw_mtime = raw_file.stat().st_mtime_ns
                            warm_started = perf_counter()
                            warm = await service.ingest_documents(
                                asset=fixture_metadata.asset,
                                as_of=fixture_metadata.as_of,
                                documents=[(document, raw)],
                            )
                            warm_ids = await metadata.get_indexed_chunk_ids(
                                warm.corpus_id
                            )
                            warm_sql = await _sql_counts(database)
                            warm_vectors = await asyncio.to_thread(
                                _vector_inventory,
                                vector_index,
                                warm,
                                set(warm_ids),
                                dimensions,
                            )
                            if (
                                warm != corpus
                                or warm_ids != chunk_ids
                                or warm_sql != cold_sql
                                or warm_vectors != vector_count
                                or raw_file.stat().st_mtime_ns != raw_mtime
                                or observed_embeddings.summary["calls"] != 1
                                or observed_index.summary["upsert_calls"] != 1
                            ):
                                raise RuntimeError(
                                    "Warm indexing changed ready storage"
                                )
                            summary["cold_warm_verification"] = {
                                "cold": {
                                    "newly_processed_chunks": len(chunk_ids),
                                    "embedding_calls": 1,
                                    "upsert_calls": 1,
                                    "vector_count": vector_count,
                                    "dimensions": dimensions,
                                    "expected_dimensions": (
                                        settings.ollama_embedding_expected_dimensions
                                    ),
                                    "sql_rows": cold_sql,
                                },
                                "warm": {
                                    "existing_chunks": len(warm_ids),
                                    "additional_embedding_calls": 0,
                                    "additional_upsert_calls": 0,
                                    "vector_count": warm_vectors,
                                    "sql_rows": warm_sql,
                                    "duration_ms": round(
                                        (perf_counter() - warm_started) * 1000, 1
                                    ),
                                },
                                "verified": True,
                            }
                            print("Cold/warm indexing verified in isolated storage")
                        print(f"\nCorpus: {corpus.corpus_id} ({corpus.status})")
                    finally:
                        await database.close()
            summary["status"] = "completed"
        except Exception as exc:
            summary.update({"status": "failed", "error_type": type(exc).__name__})
            log_failure_once(
                logger,
                "inspect_cli",
                ids=f"fixture={args.fixture}",
            )
            raise
        finally:
            if directory is not None:
                if observed_embeddings is not None:
                    summary.setdefault("embedding", observed_embeddings.summary)
                if observed_index is not None:
                    summary.setdefault("indexing", observed_index.summary)
                _write_dump(directory, "summary.json", summary)
                print(f"\nDebug dump: {directory}")


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))
