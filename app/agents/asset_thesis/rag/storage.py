import logging
from collections.abc import Mapping, Sequence
from time import perf_counter

from app.agents.asset_thesis.rag.capabilities import (
    FilingMetadataRepository,
    FilingVectorIndex,
    RawFilingStore,
)
from app.agents.asset_thesis.rag.observability import (
    log_failure_once,
    rag_run,
)
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingDocumentVersion,
)

logger = logging.getLogger(__name__)


class FilingCorpusStorageService:
    def __init__(
        self,
        raw_store: RawFilingStore,
        metadata: FilingMetadataRepository,
        vector_index: FilingVectorIndex,
    ) -> None:
        self._raw_store = raw_store
        self._metadata = metadata
        self._vector_index = vector_index

    async def store_document(
        self, document: FilingDocument, raw_html: bytes
    ) -> FilingDocumentVersion:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.store_document.start run_id=%s document_id=%s bytes=%d",
                run_id,
                document.document_id,
                len(raw_html),
            )
            try:
                stored = await self._raw_store.save(document, raw_html)
                await self._metadata.upsert_document(stored)
                assert stored.content_sha256 is not None
                version = FilingDocumentVersion(
                    document_id=stored.document_id,
                    content_sha256=stored.content_sha256,
                )
            except Exception:
                log_failure_once(
                    logger,
                    "store_document",
                    ids=f"document_id={document.document_id}",
                )
                raise
            logger.info(
                "thesis_rag.store_document.done run_id=%s document_id=%s "
                "content_sha256=%s duration_ms=%.1f",
                run_id,
                document.document_id,
                version.content_sha256,
                (perf_counter() - started) * 1000,
            )
            return version

    async def get_ready_corpus(self, corpus_id: str) -> FilingCorpusManifest | None:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.corpus_lookup.start run_id=%s corpus_id=%s",
                run_id,
                corpus_id,
            )
            try:
                manifest = await self._metadata.get_ready_manifest(corpus_id)
                if manifest is None:
                    logger.info(
                        "thesis_rag.corpus_lookup.done run_id=%s corpus_id=%s "
                        "cache_hit=False duration_ms=%.1f",
                        run_id,
                        corpus_id,
                        (perf_counter() - started) * 1000,
                    )
                    return None
                chunk_ids = await self._metadata.get_indexed_chunk_ids(corpus_id)
                if not chunk_ids or not await self._vector_index.contains_exactly(
                    manifest, chunk_ids
                ):
                    raise RuntimeError("Ready corpus is missing indexed vectors")
            except Exception:
                log_failure_once(logger, "corpus_lookup", ids=f"corpus_id={corpus_id}")
                raise
            logger.info(
                "thesis_rag.corpus_lookup.done run_id=%s corpus_id=%s "
                "cache_hit=True chunks=%d duration_ms=%.1f",
                run_id,
                corpus_id,
                len(chunk_ids),
                (perf_counter() - started) * 1000,
            )
            return manifest

    async def publish(
        self,
        manifest: FilingCorpusManifest,
        chunks: Sequence[FilingChunk],
        vectors: Mapping[str, Sequence[float]],
    ) -> FilingCorpusManifest:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.publish.start run_id=%s corpus_id=%s chunks=%d vectors=%d",
                run_id,
                manifest.corpus_id,
                len(chunks),
                len(vectors),
            )
            try:
                ready = await self._publish(manifest, chunks, vectors)
            except Exception:
                log_failure_once(
                    logger, "publish", ids=f"corpus_id={manifest.corpus_id}"
                )
                raise
            logger.info(
                "thesis_rag.publish.done run_id=%s corpus_id=%s chunks=%d "
                "status=%s duration_ms=%.1f",
                run_id,
                ready.corpus_id,
                len(chunks),
                ready.status,
                (perf_counter() - started) * 1000,
            )
            return ready

    async def _publish(
        self,
        manifest: FilingCorpusManifest,
        chunks: Sequence[FilingChunk],
        vectors: Mapping[str, Sequence[float]],
    ) -> FilingCorpusManifest:
        if manifest.index_version is None:
            raise ValueError("Cannot index a corpus without an index version")
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if not chunk_ids or len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("A corpus requires distinct chunks")
        if set(chunk_ids) != set(vectors):
            raise ValueError("Every chunk must have exactly one vector")
        for version in manifest.documents:
            document = await self._metadata.get_document(version)
            if document is None or document.raw_file_ref is None:
                raise ValueError("Every selected SEC document must be stored first")
            await self._raw_store.read(version)

        existing = await self._metadata.get_manifest(manifest.corpus_id)
        if existing is not None and existing.status == "ready":
            if (
                existing.index_version != manifest.index_version
                or existing.documents != manifest.documents
                or existing.asset != manifest.asset
                or existing.issuer_cik != manifest.issuer_cik
                or existing.as_of != manifest.as_of
            ):
                raise ValueError("Ready corpus identity cannot be changed")
            if not await self._vector_index.contains_exactly(existing, chunk_ids):
                raise RuntimeError("Ready corpus is missing indexed vectors")
            if not await self._vector_index.matches_vectors(existing, vectors):
                raise ValueError("Ready corpus has different vectors for its version")
            return await self._metadata.mark_ready(existing.corpus_id, chunk_ids)

        indexing = manifest.model_copy(update={"status": "indexing"})
        await self._metadata.save_manifest(indexing)
        await self._metadata.upsert_chunks(chunks)
        await self._vector_index.upsert(indexing, vectors)
        if not await self._vector_index.contains_exactly(indexing, chunk_ids):
            raise RuntimeError("Vector index did not persist the complete chunk set")
        return await self._metadata.mark_ready(manifest.corpus_id, chunk_ids)
