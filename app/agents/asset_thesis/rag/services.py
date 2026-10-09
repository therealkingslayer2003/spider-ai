"""Independent Thesis filing RAG entry points; implementation follows later."""

from datetime import datetime

from app.agents.asset_thesis.rag.capabilities import (
    FilingChunkSplitter,
    FilingEmbeddingGenerator,
    FilingHtmlParser,
    FilingMetadataRepository,
    FilingVectorIndex,
    RawFilingStore,
)
from app.domain.schemas.thesis_rag import FilingCorpusManifest, FilingEvidenceBundle
from app.market_data.sec_edgar_provider import SecEdgarClient


class SecFilingIngestionService:
    """Will select a fixed SEC corpus and coordinate its durable preparation."""

    def __init__(
        self,
        sec_client: SecEdgarClient,
        raw_store: RawFilingStore,
        metadata: FilingMetadataRepository,
        parser: FilingHtmlParser,
        splitter: FilingChunkSplitter,
        embeddings: FilingEmbeddingGenerator,
        vector_index: FilingVectorIndex,
    ) -> None:
        self._sec_client = sec_client
        self._raw_store = raw_store
        self._metadata = metadata
        self._parser = parser
        self._splitter = splitter
        self._embeddings = embeddings
        self._vector_index = vector_index

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
