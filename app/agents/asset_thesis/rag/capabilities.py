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
    async def parse(
        self, document: FilingDocument, raw_html: bytes
    ) -> ParsedFilingDocument: ...


class FilingChunkSplitter(Protocol):
    async def split(self, document: ParsedFilingDocument) -> list[FilingChunk]: ...


class FilingEmbeddingGenerator(Protocol):
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

    async def search(
        self,
        corpus: FilingCorpusManifest,
        query_vector: Sequence[float],
        limit: int,
    ) -> list[FilingVectorMatch]: ...
