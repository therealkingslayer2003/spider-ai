"""Dense search over one verified, versioned SEC filing corpus."""

import logging
from time import perf_counter

from app.agents.asset_thesis.rag.capabilities import (
    FilingEmbeddingGenerator,
    FilingMetadataRepository,
    FilingVectorIndex,
)
from app.agents.asset_thesis.rag.identity import make_index_version
from app.agents.asset_thesis.rag.observability import log_failure_once, rag_run
from app.agents.asset_thesis.rag.reranking import LexicalFilingReranker
from app.domain.schemas.thesis_rag import (
    FilingEvidenceBundle,
    FilingEvidenceExcerpt,
    FilingEvidenceSource,
    FilingRetrievalRequest,
)

logger = logging.getLogger(__name__)


class NoVectorsFoundError(RuntimeError):
    """A ready filing corpus returned no vectors for a dense search."""


class SecFilingRetrievalService:
    """Return ranked canonical SQL chunks from a selected Chroma collection."""

    def __init__(
        self,
        metadata: FilingMetadataRepository,
        embeddings: FilingEmbeddingGenerator,
        vector_index: FilingVectorIndex,
        *,
        reranker: LexicalFilingReranker | None = None,
        candidate_k: int | None = None,
    ) -> None:
        if reranker is not None and (candidate_k is None or candidate_k <= 0):
            raise ValueError("A positive candidate limit is required for reranking")
        self._metadata = metadata
        self._embeddings = embeddings
        self._vector_index = vector_index
        self._reranker = reranker
        self._candidate_k = candidate_k

    async def retrieve(self, request: FilingRetrievalRequest) -> FilingEvidenceBundle:
        with rag_run(request.research_id) as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.retrieve.start run_id=%s corpus_id=%s top_k=%d",
                run_id,
                request.corpus.corpus_id,
                request.top_k,
            )
            try:
                result = await self._retrieve(request)
            except Exception:
                log_failure_once(
                    logger,
                    "retrieve",
                    ids=f"corpus_id={request.corpus.corpus_id}",
                )
                raise
            logger.info(
                "thesis_rag.retrieve.done run_id=%s corpus_id=%s "
                "matches=%d embedding_version=%s duration_ms=%.1f",
                run_id,
                request.corpus.corpus_id,
                len(result.excerpts),
                result.embedding_version,
                (perf_counter() - started) * 1000,
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "thesis_rag.retrieve.matches run_id=%s question=%r "
                    "chunk_distances=%s",
                    run_id,
                    request.question,
                    [
                        (item.chunk_id, item.retrieval_distance)
                        for item in result.excerpts
                    ],
                )
            return result

    async def _retrieve(self, request: FilingRetrievalRequest) -> FilingEvidenceBundle:
        manifest = await self._metadata.get_ready_manifest(request.corpus.corpus_id)
        if manifest is None:
            raise ValueError("Filing corpus is missing or not ready")
        if (
            manifest.index_version != request.corpus.index_version
            or manifest.asset.upper() != request.asset.upper()
            or manifest.issuer_cik != request.issuer_cik
            or manifest.as_of != request.as_of
        ):
            raise ValueError("Filing corpus does not match the research selection")
        documents = {}
        for version in manifest.documents:
            document = await self._metadata.get_document(version)
            if document is None or document.published_at > request.as_of:
                raise RuntimeError("Ready corpus has a missing or future document")
            documents[(version.document_id, version.content_sha256)] = document

        processing = await self._metadata.get_processing_versions(manifest.corpus_id)
        if processing is None:
            raise RuntimeError("Ready corpus has no chunk processing version")
        expected_index = make_index_version(
            embedding_model_version=self._embeddings.version,
            parser_version=processing[0],
            splitter_version=processing[1],
        )
        if expected_index != manifest.index_version:
            raise ValueError(
                "Query embedding configuration differs from indexed corpus"
            )
        query_vector = await self._embeddings.embed_query(request.question)
        candidate_limit = (
            max(request.top_k, self._candidate_k)
            if self._reranker is not None and self._candidate_k is not None
            else request.top_k
        )
        matches = await self._vector_index.search(
            manifest, query_vector, candidate_limit
        )
        if not matches:
            raise NoVectorsFoundError("Ready corpus search returned no vectors")
        dense = sorted(matches, key=lambda item: item.distance)
        canonical = await self._metadata.get_chunks([item.chunk_id for item in dense])
        by_id = {item.chunk_id: item for item in canonical}
        ordered = (
            self._reranker.rerank(request.question, dense, by_id)[: request.top_k]
            if self._reranker is not None else dense
        )      
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "thesis_rag.retrieve.ranking corpus_id=%s dense=%s final=%s",
                manifest.corpus_id,
                [(item.chunk_id, item.distance) for item in dense],
                [item.chunk_id for item in ordered],
            )

        excerpts = []
        for rank, match in enumerate(ordered, start=1):
            chunk = by_id[match.chunk_id]
            document = documents[
                (chunk.document.document_id, chunk.document.content_sha256)
            ]
            excerpts.append(
                FilingEvidenceExcerpt(
                    rank=rank,
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    retrieval_distance=match.distance,
                    source=FilingEvidenceSource(
                        document=chunk.document,
                        accession_number=document.accession_number,
                        filename=document.filename,
                        form=document.form,
                        exhibit_type=document.exhibit_type,
                        source_url=document.source_url,
                        published_at=document.published_at,
                        report_period_end=document.report_period_end,
                        section_path=chunk.section_path,
                        source_locator=chunk.source_locator,
                    ),
                )
            )
        return FilingEvidenceBundle(
            request=request,
            parser_version=processing[0],
            splitter_version=processing[1],
            embedding_version=self._embeddings.version,
            ranking_version=(
                self._reranker.version if self._reranker is not None else "dense-v1"
            ),
            excerpts=excerpts,
        )
