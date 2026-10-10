"""SQL persistence for reusable SEC document versions and corpus selections."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.asset_thesis.rag.identity import (
    make_chunk_id,
    make_corpus_id,
    make_document_id,
)
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingDocumentVersion,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.models import (
    FilingChunkModel,
    FilingCorpusChunkModel,
    FilingCorpusDocumentModel,
    FilingCorpusModel,
    FilingDocumentModel,
)


class SqlFilingMetadataRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert_document(self, document: FilingDocument) -> None:
        if document.document_id != make_document_id(
            document.issuer_cik, document.accession_number, document.filename
        ):
            raise ValueError("Filing document ID does not match its SEC identity")
        if document.content_sha256 is None or document.raw_file_ref is None:
            raise ValueError("Persisted filing documents require a raw file and hash")
        await self._database.initialize()
        async with self._database.session_factory() as session, session.begin():
            key = (document.document_id, document.content_sha256)
            existing = await session.get(FilingDocumentModel, key)
            if existing is not None:
                if (
                    FilingDocument.model_validate_json(existing.document_json)
                    != document
                ):
                    raise ValueError(
                        "Conflicting SEC document metadata for the same version"
                    )
                return
            session.add(
                FilingDocumentModel(
                    document_id=document.document_id,
                    content_sha256=document.content_sha256,
                    issuer_cik=document.issuer_cik,
                    accession_number=document.accession_number,
                    filename=document.filename,
                    published_at_utc=document.published_at.astimezone(UTC).isoformat(
                        timespec="microseconds"
                    ),
                    document_json=document.model_dump_json(),
                )
            )

    async def upsert_chunks(self, chunks: Sequence[FilingChunk]) -> None:
        unique: dict[str, FilingChunk] = {}
        for chunk in chunks:
            expected = make_chunk_id(
                chunk.document,
                parser_version=chunk.parser_version,
                splitter_version=chunk.splitter_version,
                position=chunk.position,
                source_locator=chunk.source_locator,
                text=chunk.text,
            )
            if chunk.chunk_id != expected:
                raise ValueError(
                    "Filing chunk ID does not match its content and versions"
                )
            if chunk.chunk_id in unique and unique[chunk.chunk_id] != chunk:
                raise ValueError("Conflicting filing chunks share an ID")
            unique[chunk.chunk_id] = chunk
        await self._database.initialize()
        async with self._database.session_factory() as session, session.begin():
            for chunk in unique.values():
                existing = await session.get(FilingChunkModel, chunk.chunk_id)
                if existing is not None:
                    if FilingChunk.model_validate_json(existing.chunk_json) != chunk:
                        raise ValueError(
                            "Conflicting filing chunk metadata for the same ID"
                        )
                    continue
                session.add(
                    FilingChunkModel(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document.document_id,
                        content_sha256=chunk.document.content_sha256,
                        parser_version=chunk.parser_version,
                        splitter_version=chunk.splitter_version,
                        chunk_json=chunk.model_dump_json(),
                    )
                )

    async def save_manifest(self, manifest: FilingCorpusManifest) -> None:
        if manifest.status == "ready":
            raise ValueError("Only mark_ready may publish a filing corpus")
        if manifest.index_version is None:
            raise ValueError("Persisted filing corpus requires an index version")
        if not manifest.documents or len(
            set((item.document_id, item.content_sha256) for item in manifest.documents)
        ) != len(manifest.documents):
            raise ValueError("A filing corpus needs distinct document versions")
        if manifest.corpus_id != make_corpus_id(
            asset=manifest.asset,
            issuer_cik=manifest.issuer_cik,
            as_of=manifest.as_of,
            documents=manifest.documents,
            index_version=manifest.index_version,
        ):
            raise ValueError("Filing corpus ID does not match its selection")
        await self._database.initialize()
        async with self._database.session_factory() as session, session.begin():
            for version in manifest.documents:
                document = await session.get(
                    FilingDocumentModel,
                    (version.document_id, version.content_sha256),
                )
                if document is None:
                    raise ValueError("Corpus references an unstored SEC document")
                if document.issuer_cik != manifest.issuer_cik:
                    raise ValueError("Corpus document belongs to another issuer")
                if datetime.fromisoformat(document.published_at_utc) > manifest.as_of:
                    raise ValueError("Corpus contains a document published after as_of")

            existing = await self._load_manifest(session, manifest.corpus_id)
            if existing is not None:
                if (
                    existing.asset != manifest.asset
                    or existing.issuer_cik != manifest.issuer_cik
                    or existing.as_of != manifest.as_of
                    or existing.documents != manifest.documents
                ):
                    raise ValueError("Corpus ID already belongs to another selection")
                if existing.index_version != manifest.index_version:
                    raise ValueError("Corpus ID already has another index version")
                if existing.status == "ready":
                    raise ValueError("A ready corpus cannot be reset or reindexed")
                if existing.status == "indexing" and manifest.status == "selected":
                    raise ValueError("A corpus cannot regress to selected")
                stored = await session.get(FilingCorpusModel, manifest.corpus_id)
                assert stored is not None
                stored.index_version = manifest.index_version
                stored.status = manifest.status
                return

            session.add(
                FilingCorpusModel(
                    corpus_id=manifest.corpus_id,
                    asset=manifest.asset,
                    issuer_cik=manifest.issuer_cik,
                    as_of_utc=manifest.as_of.astimezone(UTC).isoformat(
                        timespec="microseconds"
                    ),
                    index_version=manifest.index_version,
                    status=manifest.status,
                )
            )
            await session.flush()
            for position, version in enumerate(manifest.documents):
                session.add(
                    FilingCorpusDocumentModel(
                        corpus_id=manifest.corpus_id,
                        document_id=version.document_id,
                        content_sha256=version.content_sha256,
                        position=position,
                    )
                )

    async def get_manifest(self, corpus_id: str) -> FilingCorpusManifest | None:
        await self._database.initialize()
        async with self._database.session_factory() as session:
            return await self._load_manifest(session, corpus_id)

    async def get_ready_manifest(self, corpus_id: str) -> FilingCorpusManifest | None:
        manifest = await self.get_manifest(corpus_id)
        return manifest if manifest is not None and manifest.status == "ready" else None

    async def get_indexed_chunk_ids(self, corpus_id: str) -> list[str]:
        await self._database.initialize()
        async with self._database.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(FilingCorpusChunkModel.chunk_id).where(
                            FilingCorpusChunkModel.corpus_id == corpus_id
                        )
                    )
                ).all()
            )

    async def mark_ready(
        self, corpus_id: str, chunk_ids: Sequence[str]
    ) -> FilingCorpusManifest:
        expected = set(chunk_ids)
        if not expected or len(expected) != len(chunk_ids):
            raise ValueError("Ready corpus requires distinct indexed chunk IDs")
        await self._database.initialize()
        async with self._database.session_factory() as session, session.begin():
            manifest = await self._load_manifest(session, corpus_id)
            if manifest is None:
                raise ValueError("Filing corpus does not exist")
            if manifest.index_version is None:
                raise ValueError("Cannot publish a corpus without an index version")
            current = set(
                (
                    await session.scalars(
                        select(FilingCorpusChunkModel.chunk_id).where(
                            FilingCorpusChunkModel.corpus_id == corpus_id
                        )
                    )
                ).all()
            )
            if manifest.status == "ready":
                if current != expected:
                    raise ValueError("Ready corpus has a different indexed chunk set")
                return manifest
            if manifest.status != "indexing":
                raise ValueError("Corpus must be indexing before it is ready")
            chunks = (
                await session.scalars(
                    select(FilingChunkModel).where(
                        FilingChunkModel.chunk_id.in_(expected)
                    )
                )
            ).all()
            if len(chunks) != len(expected):
                raise ValueError("Not all indexed chunks have SQL records")
            selected = {
                (item.document_id, item.content_sha256) for item in manifest.documents
            }
            represented = {(item.document_id, item.content_sha256) for item in chunks}
            if represented != selected:
                raise ValueError("Indexed chunks must cover only selected documents")
            processing_versions = {
                (item.parser_version, item.splitter_version) for item in chunks
            }
            if len(processing_versions) != 1:
                raise ValueError("A corpus index must use one chunk processing version")
            for chunk_id in expected:
                session.add(
                    FilingCorpusChunkModel(corpus_id=corpus_id, chunk_id=chunk_id)
                )
            stored = await session.get(FilingCorpusModel, corpus_id)
            assert stored is not None
            stored.status = "ready"
            return manifest.model_copy(update={"status": "ready"})

    async def get_document(
        self, version: FilingDocumentVersion
    ) -> FilingDocument | None:
        await self._database.initialize()
        async with self._database.session_factory() as session:
            stored = await session.get(
                FilingDocumentModel, (version.document_id, version.content_sha256)
            )
            if stored is None:
                return None
            return FilingDocument.model_validate_json(stored.document_json)

    async def get_chunks(self, chunk_ids: Sequence[str]) -> list[FilingChunk]:
        if not chunk_ids:
            return []
        await self._database.initialize()
        async with self._database.session_factory() as session:
            rows = (
                await session.scalars(
                    select(FilingChunkModel).where(
                        FilingChunkModel.chunk_id.in_(chunk_ids)
                    )
                )
            ).all()
            by_id = {
                row.chunk_id: FilingChunk.model_validate_json(row.chunk_json)
                for row in rows
            }
            return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    @staticmethod
    async def _load_manifest(
        session: AsyncSession, corpus_id: str
    ) -> FilingCorpusManifest | None:
        stored = await session.get(FilingCorpusModel, corpus_id)
        if stored is None:
            return None
        members = (
            await session.scalars(
                select(FilingCorpusDocumentModel)
                .where(FilingCorpusDocumentModel.corpus_id == corpus_id)
                .order_by(FilingCorpusDocumentModel.position)
            )
        ).all()
        return FilingCorpusManifest.model_validate(
            {
                "corpus_id": stored.corpus_id,
                "asset": stored.asset,
                "issuer_cik": stored.issuer_cik,
                "as_of": stored.as_of_utc,
                "documents": [
                    FilingDocumentVersion(
                        document_id=member.document_id,
                        content_sha256=member.content_sha256,
                    )
                    for member in members
                ],
                "index_version": stored.index_version,
                "status": stored.status,
            }
        )
