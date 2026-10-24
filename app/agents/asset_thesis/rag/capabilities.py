from collections.abc import Mapping, Sequence
from typing import Protocol

from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingDocumentVersion,
    FilingVectorMatch,
    ParsedFilingDocument,
)


class FilingHtmlParser(Protocol):
    @property
    def version(self) -> str: ...

    async def parse(
        self, document: FilingDocument, raw_html: bytes
    ) -> ParsedFilingDocument: ...


class FilingChunkSplitter(Protocol):
    @property
    def version(self) -> str: ...

    async def split(self, document: ParsedFilingDocument) -> list[FilingChunk]: ...


class FilingEmbeddingGenerator(Protocol):
    @property
    def version(self) -> str: ...

    async def embed_chunks(
        self, chunks: Sequence[FilingChunk]
    ) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


class RawFilingStore(Protocol):
    async def save(
        self, document: FilingDocument, raw_html: bytes
    ) -> FilingDocument: ...

    async def read(self, document: FilingDocumentVersion) -> bytes: ...


class FilingMetadataRepository(Protocol):
    async def upsert_document(self, document: FilingDocument) -> None: ...

    async def upsert_chunks(self, chunks: Sequence[FilingChunk]) -> None: ...

    async def save_manifest(self, manifest: FilingCorpusManifest) -> None: ...

    async def get_manifest(self, corpus_id: str) -> FilingCorpusManifest | None: ...

    async def get_ready_manifest(
        self, corpus_id: str
    ) -> FilingCorpusManifest | None: ...

    async def mark_ready(
        self, corpus_id: str, chunk_ids: Sequence[str]
    ) -> FilingCorpusManifest: ...

    async def get_indexed_chunk_ids(self, corpus_id: str) -> list[str]: ...

    async def get_processing_versions(
        self, corpus_id: str
    ) -> tuple[str, str] | None: ...

    async def get_document(
        self, version: FilingDocumentVersion
    ) -> FilingDocument | None: ...

    async def get_chunks(self, chunk_ids: Sequence[str]) -> list[FilingChunk]: ...


class FilingVectorIndex(Protocol):
    async def upsert(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> None: ...

    async def contains_exactly(
        self, corpus: FilingCorpusManifest, chunk_ids: Sequence[str]
    ) -> bool: ...

    async def matches_vectors(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> bool: ...

    async def search(
        self,
        corpus: FilingCorpusManifest,
        query_vector: Sequence[float],
        limit: int,
    ) -> list[FilingVectorMatch]: ...
