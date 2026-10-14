"""Independent Thesis filing RAG entry points."""

import hashlib
import logging
from collections.abc import Sequence
from datetime import datetime
from time import perf_counter

from app.agents.asset_thesis.rag.capabilities import (
    FilingChunkSplitter,
    FilingEmbeddingGenerator,
    FilingHtmlParser,
    FilingMetadataRepository,
    FilingVectorIndex,
)
from app.agents.asset_thesis.rag.identity import make_corpus_id, make_index_version
from app.agents.asset_thesis.rag.observability import (
    current_run_id,
    log_failure_once,
    rag_run,
)
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingEvidenceBundle,
    ParsedFilingDocument,
)

logger = logging.getLogger(__name__)


class SecFilingIngestionService:
    """Prepare an explicit SEC document selection; selection itself follows later."""

    def __init__(
        self,
        storage: FilingCorpusStorageService | None,
        parser: FilingHtmlParser,
        splitter: FilingChunkSplitter,
        embeddings: FilingEmbeddingGenerator,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._splitter = splitter
        self._embeddings = embeddings

    async def inspect_document(
        self, document: FilingDocument, raw_html: bytes
    ) -> tuple[ParsedFilingDocument, list[FilingChunk]]:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.inspect.start run_id=%s document_id=%s input_bytes=%d",
                run_id,
                document.document_id,
                len(raw_html),
            )
            try:
                digest = hashlib.sha256(raw_html).hexdigest()
                if (
                    document.content_sha256 is not None
                    and document.content_sha256 != digest
                ):
                    raise ValueError(
                        "SEC document content hash does not match its HTML"
                    )
                versioned = document.model_copy(update={"content_sha256": digest})
                parsed = await self._parser.parse(versioned, raw_html)
                chunks = await self._splitter.split(parsed)
            except Exception:
                log_failure_once(
                    logger, "inspect", ids=f"document_id={document.document_id}"
                )
                raise
            logger.info(
                "thesis_rag.inspect.done run_id=%s document_id=%s blocks=%d "
                "chunks=%d duration_ms=%.1f",
                run_id,
                document.document_id,
                len(parsed.blocks),
                len(chunks),
                (perf_counter() - started) * 1000,
            )
            return parsed, chunks

    async def ingest_documents(
        self,
        *,
        asset: str,
        as_of: datetime,
        documents: Sequence[tuple[FilingDocument, bytes]],
    ) -> FilingCorpusManifest:
        """Index a caller-selected filing and its optional exhibits."""
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.ingest.start run_id=%s asset=%s documents=%d",
                run_id,
                asset,
                len(documents),
            )
            try:
                manifest = await self._ingest_documents(
                    asset=asset, as_of=as_of, documents=documents
                )
            except Exception:
                log_failure_once(logger, "ingest", ids=f"asset={asset}")
                raise
            logger.info(
                "thesis_rag.ingest.done run_id=%s corpus_id=%s documents=%d "
                "status=%s duration_ms=%.1f",
                run_id,
                manifest.corpus_id,
                len(manifest.documents),
                manifest.status,
                (perf_counter() - started) * 1000,
            )
            return manifest

    async def _ingest_documents(
        self,
        *,
        asset: str,
        as_of: datetime,
        documents: Sequence[tuple[FilingDocument, bytes]],
    ) -> FilingCorpusManifest:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("Corpus as_of must be timezone-aware")
        if not documents:
            raise ValueError("A filing corpus needs at least one document")
        if self._storage is None:
            raise RuntimeError("Filing storage is required for indexing")
        issuer_cik = documents[0][0].issuer_cik
        if any(doc.issuer_cik != issuer_cik for doc, _ in documents):
            raise ValueError("A corpus cannot mix issuers")
        if any(doc.published_at > as_of for doc, _ in documents):
            raise ValueError("A corpus cannot contain future-published documents")
        selected = sorted(documents, key=lambda pair: pair[0].document_id)
        if len({doc.document_id for doc, _ in selected}) != len(selected):
            raise ValueError("A corpus cannot select a document twice")
        versions = [
            await self._storage.store_document(doc, raw) for doc, raw in selected
        ]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "thesis_rag.ingest.selection run_id=%s document_ids=%s input_bytes=%d",
                current_run_id(),
                [doc.document_id for doc, _ in selected],
                sum(len(raw) for _, raw in selected),
            )
        index_version = make_index_version(
            embedding_model_version=self._embeddings.version,
            parser_version=self._parser.version,
            splitter_version=self._splitter.version,
        )
        corpus_id = make_corpus_id(
            asset=asset,
            issuer_cik=issuer_cik,
            as_of=as_of,
            documents=versions,
            index_version=index_version,
        )
        ready = await self._storage.get_ready_corpus(corpus_id)
        if ready is not None:
            return ready
        chunks: list[FilingChunk] = []
        for (doc, raw), version in zip(selected, versions, strict=True):
            versioned = doc.model_copy(
                update={"content_sha256": version.content_sha256}
            )
            _, prepared = await self.inspect_document(versioned, raw)
            chunks.extend(prepared)
        vectors = await self._embeddings.embed_chunks(chunks)
        if len(vectors) != len(chunks):
            raise RuntimeError("Embedding model returned an incomplete corpus")
        manifest = FilingCorpusManifest(
            corpus_id=corpus_id,
            asset=asset,
            issuer_cik=issuer_cik,
            as_of=as_of,
            documents=versions,
            index_version=index_version,
            status="selected",
        )
        return await self._storage.publish(
            manifest,
            chunks,
            {
                chunk.chunk_id: vector
                for chunk, vector in zip(chunks, vectors, strict=True)
            },
        )

    async def ingest(self, *, asset: str, as_of: datetime) -> FilingCorpusManifest:
        raise NotImplementedError("SEC filing ingestion is not implemented yet.")


class SecFilingRetrievalService:
    """Will return cited filing excerpts from one prepared corpus."""

    def __init__(
        self,
        metadata: FilingMetadataRepository,
        embeddings: FilingEmbeddingGenerator,
        vector_index: FilingVectorIndex,
    ) -> None:
        self._metadata = metadata
        self._embeddings = embeddings
        self._vector_index = vector_index

    async def retrieve(
        self, *, query: str, corpus_id: str, limit: int
    ) -> FilingEvidenceBundle:
        raise NotImplementedError("SEC filing retrieval is not implemented yet.")
