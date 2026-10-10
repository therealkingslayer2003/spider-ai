import asyncio
import hashlib
import math
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

from app.domain.schemas.thesis_rag import FilingCorpusManifest, FilingVectorMatch


class ChromaFilingVectorIndex:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._client: Any = None
        self._client_lock = Lock()

    async def upsert(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> None:
        if corpus.status != "indexing" or corpus.index_version is None:
            raise ValueError("Only an indexing corpus with a version can be written")
        if not vectors:
            raise ValueError("A filing index requires at least one vector")
        dimensions = {len(vector) for vector in vectors.values()}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ValueError("Filing vectors must have one nonzero dimension")
        if any(
            not math.isfinite(value) for vector in vectors.values() for value in vector
        ):
            raise ValueError("Filing vectors must contain only finite values")
        await asyncio.to_thread(self._upsert, corpus, vectors)

    async def contains_exactly(
        self, corpus: FilingCorpusManifest, chunk_ids: Sequence[str]
    ) -> bool:
        if corpus.index_version is None or not self._root.exists():
            return False
        return await asyncio.to_thread(self._contains_exactly, corpus, set(chunk_ids))

    async def matches_vectors(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> bool:
        if not await self.contains_exactly(corpus, list(vectors)):
            return False
        return await asyncio.to_thread(self._matches_vectors, corpus, vectors)

    async def search(
        self,
        corpus: FilingCorpusManifest,
        query_vector: Sequence[float],
        limit: int,
    ) -> list[FilingVectorMatch]:
        if corpus.status != "ready" or corpus.index_version is None:
            raise ValueError("Only a ready filing corpus can be searched")
        if (
            limit <= 0
            or not query_vector
            or any(not math.isfinite(value) for value in query_vector)
        ):
            raise ValueError("Search requires a finite query vector and positive limit")
        return await asyncio.to_thread(self._search, corpus, query_vector, limit)

    @staticmethod
    def _collection_name(corpus: FilingCorpusManifest) -> str:
        assert corpus.index_version is not None
        pair = f"{corpus.corpus_id}\0{corpus.index_version}".encode()
        return f"filing_{hashlib.sha256(pair).hexdigest()}"

    @staticmethod
    def _vector_hash(vector: Sequence[float]) -> str:
        packed = struct.pack(f">{len(vector)}d", *vector)
        return hashlib.sha256(packed).hexdigest()

    def _get_client(self) -> Any:
        with self._client_lock:
            if self._client is None:
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.PersistentClient(
                    path=str(self._root),
                    settings=Settings(anonymized_telemetry=False),
                )
            return self._client

    def _upsert(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> None:
        client = self._get_client()
        collection = client.get_or_create_collection(
            name=self._collection_name(corpus), embedding_function=None
        )
        ids = sorted(vectors)
        batch_size = client.get_max_batch_size()
        for start in range(0, len(ids), batch_size):
            batch = ids[start : start + batch_size]
            hashes = {item: self._vector_hash(vectors[item]) for item in batch}
            existing = collection.get(ids=batch, include=["metadatas"])
            for existing_id, metadata in zip(
                existing["ids"], existing["metadatas"] or [], strict=True
            ):
                if (
                    metadata is None
                    or metadata.get("vector_sha256") != hashes[existing_id]
                ):
                    raise ValueError("Conflicting vector for an existing chunk/version")
            collection.upsert(
                ids=batch,
                embeddings=[list(vectors[item]) for item in batch],
                metadatas=[{"vector_sha256": hashes[item]} for item in batch],
            )
        stale = set(collection.get(include=[])["ids"]) - set(ids)
        if stale:
            collection.delete(ids=sorted(stale))

    def _contains_exactly(
        self, corpus: FilingCorpusManifest, chunk_ids: set[str]
    ) -> bool:
        from chromadb.errors import NotFoundError

        try:
            collection = self._get_client().get_collection(
                name=self._collection_name(corpus), embedding_function=None
            )
        except NotFoundError:
            return False
        if collection.count() != len(chunk_ids):
            return False
        ids = sorted(chunk_ids)
        batch_size = self._get_client().get_max_batch_size()
        found: set[str] = set()
        for start in range(0, len(ids), batch_size):
            found.update(
                collection.get(ids=ids[start : start + batch_size], include=[])["ids"]
            )
        return found == chunk_ids

    def _matches_vectors(
        self,
        corpus: FilingCorpusManifest,
        vectors: Mapping[str, Sequence[float]],
    ) -> bool:
        collection = self._get_client().get_collection(
            name=self._collection_name(corpus), embedding_function=None
        )
        ids = sorted(vectors)
        batch_size = self._get_client().get_max_batch_size()
        for start in range(0, len(ids), batch_size):
            result = collection.get(
                ids=ids[start : start + batch_size], include=["metadatas"]
            )
            for chunk_id, metadata in zip(
                result["ids"], result["metadatas"] or [], strict=True
            ):
                if metadata is None or metadata.get("vector_sha256") != (
                    self._vector_hash(vectors[chunk_id])
                ):
                    return False
        return True

    def _search(
        self,
        corpus: FilingCorpusManifest,
        query_vector: Sequence[float],
        limit: int,
    ) -> list[FilingVectorMatch]:
        collection = self._get_client().get_collection(
            name=self._collection_name(corpus), embedding_function=None
        )
        if collection.count() == 0:
            raise RuntimeError("A ready filing corpus has no indexed vectors")
        result = collection.query(
            query_embeddings=[list(query_vector)],
            n_results=limit,
            include=["distances"],
        )
        ids = result["ids"][0]
        distances = (result["distances"] or [[]])[0]
        return [
            FilingVectorMatch(chunk_id=chunk_id, distance=float(distance))
            for chunk_id, distance in zip(ids, distances, strict=True)
        ]
