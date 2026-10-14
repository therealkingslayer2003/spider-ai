import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import HttpUrl
from sqlalchemy import func, select

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.identity import (
    make_chunk_id,
    make_corpus_id,
    make_document_id,
    make_index_version,
)
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingDocument,
    FilingDocumentVersion,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from app.infrastructure.db.models import (
    FilingChunkModel,
    FilingCorpusChunkModel,
    FilingCorpusDocumentModel,
    FilingDocumentModel,
)

CIK = "0000000123"
ACCESSION = "0000000123-26-000001"
AS_OF = datetime(2026, 7, 1, 12, tzinfo=UTC)


def document(filename: str, *, published_at: datetime | None = None) -> FilingDocument:
    return FilingDocument(
        document_id=make_document_id(CIK, ACCESSION, filename),
        issuer_cik=CIK,
        accession_number=ACCESSION,
        filename=filename,
        form="10-Q",
        exhibit_type="EX-99.1" if filename != "quarter.htm" else None,
        source_url=HttpUrl(f"https://www.sec.gov/Archives/edgar/data/123/1/{filename}"),
        published_at=published_at or AS_OF - timedelta(days=1),
        report_period_end=date(2026, 6, 30),
    )


def chunk(version: FilingDocumentVersion, text: str, position: int) -> FilingChunk:
    locator = f"section-{position}"
    return FilingChunk(
        chunk_id=make_chunk_id(
            version,
            parser_version="html-v1",
            splitter_version="paragraph-v1",
            position=position,
            source_locator=locator,
            text=text,
        ),
        document=version,
        text=text,
        section_path=["Business", "Revenue"],
        position=position,
        source_locator=locator,
        token_count=8,
        parser_version="html-v1",
        splitter_version="paragraph-v1",
    )


def manifest(versions: list[FilingDocumentVersion]) -> FilingCorpusManifest:
    index_version = make_index_version(
        embedding_model_version="test-embedding-v1",
        parser_version="html-v1",
        splitter_version="paragraph-v1",
    )
    return FilingCorpusManifest(
        corpus_id=make_corpus_id(
            asset="MA",
            issuer_cik=CIK,
            as_of=AS_OF,
            documents=versions,
            index_version=index_version,
        ),
        asset="MA",
        issuer_cik=CIK,
        as_of=AS_OF,
        documents=versions,
        index_version=index_version,
        status="selected",
    )


@pytest.mark.asyncio
async def test_storage_round_trip_is_idempotent_and_keeps_exhibit_provenance(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    raw = FileRawFilingStore(tmp_path / "raw")
    vectors = ChromaFilingVectorIndex(tmp_path / "vectors")
    storage = FilingCorpusStorageService(raw, metadata, vectors)
    original = b"<html>primary\xff filing</html>"
    try:
        main = await storage.store_document(document("quarter.htm"), original)
        exhibit = await storage.store_document(
            document("ex991.htm"), b"<html>exhibit</html>"
        )
        assert main.document_id != exhibit.document_id
        assert await raw.read(main) == original
        selected = manifest([main, exhibit])
        await metadata.save_manifest(selected)
        assert await metadata.get_manifest(selected.corpus_id) == selected
        chunks = [chunk(main, "Card volume grew.", 0), chunk(exhibit, "New terms.", 0)]
        embeddings = {chunks[0].chunk_id: [1.0, 0.0], chunks[1].chunk_id: [0.0, 1.0]}

        ready = await storage.publish(selected, chunks, embeddings)
        assert ready.status == "ready"
        assert ready.corpus_id == selected.corpus_id
        assert ready.index_version == selected.index_version
        assert await metadata.get_ready_manifest(selected.corpus_id) == ready
        assert await storage.get_ready_corpus(selected.corpus_id) == ready
        assert await storage.publish(selected, chunks, embeddings) == ready
        with pytest.raises(ValueError, match="different vectors"):
            await storage.publish(
                selected,
                chunks,
                {chunks[0].chunk_id: [0.5, 0.5], chunks[1].chunk_id: [0.0, 1.0]},
            )
        assert await metadata.get_chunks([item.chunk_id for item in chunks]) == chunks
        stored_exhibit = await metadata.get_document(exhibit)
        assert stored_exhibit is not None
        assert stored_exhibit.exhibit_type == "EX-99.1"
        assert stored_exhibit.report_period_end == date(2026, 6, 30)
        assert stored_exhibit.published_at == AS_OF - timedelta(days=1)
        assert stored_exhibit.raw_file_ref is not None
        matches = await vectors.search(ready, [1.0, 0.0], 2)
        assert [item.chunk_id for item in matches] == [
            chunks[0].chunk_id,
            chunks[1].chunk_id,
        ]
        assert matches[0].distance == pytest.approx(0.0)
        assert matches[0].distance <= matches[1].distance

        async with database.session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingDocumentModel)
                )
                == 2
            )
            assert (
                await session.scalar(select(func.count()).select_from(FilingChunkModel))
                == 2
            )
            stored_chunk = await session.get(FilingChunkModel, chunks[0].chunk_id)
            assert stored_chunk is not None
            assert stored_chunk.text == chunks[0].text
            assert stored_chunk.token_count == chunks[0].token_count
            assert "text" not in json.loads(stored_chunk.chunk_json)
            assert "token_count" not in json.loads(stored_chunk.chunk_json)
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingCorpusDocumentModel)
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingCorpusChunkModel)
                )
                == 2
            )
    finally:
        await database.close()

    reopened = Database(tmp_path / "filings.db")
    try:
        assert (
            await SqlFilingMetadataRepository(reopened).get_ready_manifest(
                selected.corpus_id
            )
            == ready
        )
        reopened_index = ChromaFilingVectorIndex(tmp_path / "vectors")
        assert await reopened_index.contains_exactly(
            ready, [item.chunk_id for item in chunks]
        )
        assert (await reopened_index.search(ready, [1.0, 0.0], 1))[
            0
        ].chunk_id == chunks[0].chunk_id
        assert await FileRawFilingStore(tmp_path / "raw").read(exhibit) == (
            b"<html>exhibit</html>"
        )
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_existing_chunk_rows_are_backfilled_into_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy-filings.db"
    migrations = (
        Path(__file__).resolve().parents[2] / "app/infrastructure/db/migrations"
    )
    raw_hash = hashlib.sha256(b"<html>legacy filing</html>").hexdigest()
    original_document = document("quarter.htm").model_copy(
        update={
            "content_sha256": raw_hash,
            "raw_file_ref": f"sha256/{raw_hash[:2]}/{raw_hash}.html",
        }
    )
    version = FilingDocumentVersion(
        document_id=original_document.document_id, content_sha256=raw_hash
    )
    original_chunk = chunk(version, "Legacy revenue increased.", 0)

    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE schema_migration (version TEXT PRIMARY KEY, "
            "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP);"
        )
        for version_number, filename in (
            ("001", "001_initial_schema.sql"),
            ("002", "002_thesis_rag_storage.sql"),
        ):
            connection.executescript((migrations / filename).read_text())
            connection.execute(
                "INSERT INTO schema_migration (version) VALUES (?)", (version_number,)
            )
        connection.execute(
            "INSERT INTO filing_document_version VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                original_document.document_id,
                raw_hash,
                original_document.issuer_cik,
                original_document.accession_number,
                original_document.filename,
                original_document.published_at.isoformat(),
                original_document.model_dump_json(),
            ),
        )
        connection.execute(
            "INSERT INTO filing_chunk VALUES (?, ?, ?, ?, ?, ?)",
            (
                original_chunk.chunk_id,
                version.document_id,
                version.content_sha256,
                original_chunk.parser_version,
                original_chunk.splitter_version,
                original_chunk.model_dump_json(),
            ),
        )

    database = Database(path)
    metadata = SqlFilingMetadataRepository(database)
    try:
        await database.initialize()
        async with database.session_factory() as session:
            stored = await session.get(FilingChunkModel, original_chunk.chunk_id)
            assert stored is not None
            assert stored.text == original_chunk.text
            assert stored.token_count == original_chunk.token_count
            assert "text" not in json.loads(stored.chunk_json)
            assert "token_count" not in json.loads(stored.chunk_json)
        assert await metadata.get_chunks([original_chunk.chunk_id]) == [original_chunk]
        await metadata.upsert_chunks([original_chunk])
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_manifest_identity_is_fixed_before_first_persistence(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    storage = FilingCorpusStorageService(
        FileRawFilingStore(tmp_path / "raw"),
        metadata,
        ChromaFilingVectorIndex(tmp_path / "vectors"),
    )
    try:
        version = await storage.store_document(
            document("quarter.htm"), b"<html>A</html>"
        )
        selected = manifest([version])
        unversioned = selected.model_copy(update={"index_version": None})
        with pytest.raises(ValueError, match="requires an index version"):
            await metadata.save_manifest(unversioned)
        assert await metadata.get_manifest(selected.corpus_id) is None

        await metadata.save_manifest(selected)
        changed = selected.model_copy(update={"index_version": "different-model"})
        with pytest.raises(ValueError, match="ID does not match"):
            await metadata.save_manifest(changed)
        assert await metadata.get_manifest(selected.corpus_id) == selected
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_failed_vector_write_stays_unready_and_retry_recovers(
    tmp_path: Path,
) -> None:
    class InterruptedIndex(ChromaFilingVectorIndex):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.fail_once = True

        async def upsert(self, corpus, vectors):
            await super().upsert(corpus, vectors)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("interrupted after vector write")

    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    vector_index = InterruptedIndex(tmp_path / "vectors")
    storage = FilingCorpusStorageService(
        FileRawFilingStore(tmp_path / "raw"), metadata, vector_index
    )
    try:
        version = await storage.store_document(
            document("quarter.htm"), b"<html>A</html>"
        )
        selected = manifest([version])
        item = chunk(version, "Revenue increased.", 0)
        embeddings = {item.chunk_id: [1.0, 0.0]}

        with pytest.raises(RuntimeError, match="interrupted"):
            await storage.publish(selected, [item], embeddings)
        in_progress = await metadata.get_manifest(selected.corpus_id)
        assert in_progress is not None and in_progress.status == "indexing"
        assert await metadata.get_ready_manifest(selected.corpus_id) is None
        assert await storage.get_ready_corpus(selected.corpus_id) is None
        with pytest.raises(ValueError, match="ready"):
            await vector_index.search(selected, [1.0, 0.0], 1)

        with pytest.raises(ValueError, match="Conflicting vector"):
            await storage.publish(selected, [item], {item.chunk_id: [0.0, 1.0]})
        assert await metadata.get_ready_manifest(selected.corpus_id) is None

        ready = await storage.publish(selected, [item], embeddings)
        assert ready.status == "ready"
        assert await vector_index.contains_exactly(ready, [item.chunk_id])
        assert await storage.publish(selected, [item], embeddings) == ready
        with pytest.raises(RuntimeError, match="missing indexed vectors"):
            await FilingCorpusStorageService(
                FileRawFilingStore(tmp_path / "raw"),
                metadata,
                ChromaFilingVectorIndex(tmp_path / "different-vectors"),
            ).get_ready_corpus(selected.corpus_id)
        async with database.session_factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(FilingChunkModel))
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingCorpusChunkModel)
                )
                == 1
            )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_storage_rejects_future_documents_and_incomplete_chunk_coverage(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    storage = FilingCorpusStorageService(
        FileRawFilingStore(tmp_path / "raw"),
        metadata,
        ChromaFilingVectorIndex(tmp_path / "vectors"),
    )
    try:
        future = await storage.store_document(
            document("future.htm", published_at=AS_OF + timedelta(microseconds=1)),
            b"<html>future</html>",
        )
        with pytest.raises(ValueError, match="after as_of"):
            await storage.publish(
                manifest([future]),
                [chunk(future, "Future disclosure.", 0)],
                {chunk(future, "Future disclosure.", 0).chunk_id: [1.0, 0.0]},
            )

        main = await storage.store_document(document("quarter.htm"), b"<html>A</html>")
        exhibit = await storage.store_document(document("ex991.htm"), b"<html>B</html>")
        selected = manifest([main, exhibit])
        only_main = chunk(main, "Only primary content.", 0)
        with pytest.raises(ValueError, match="cover only selected"):
            await storage.publish(
                selected, [only_main], {only_main.chunk_id: [1.0, 0.0]}
            )
        assert await metadata.get_ready_manifest(selected.corpus_id) is None
        in_progress = await metadata.get_manifest(selected.corpus_id)
        assert in_progress is not None and in_progress.status == "indexing"

        mixed_exhibit = chunk(exhibit, "Exhibit content.", 0)
        mixed_exhibit = mixed_exhibit.model_copy(
            update={
                "splitter_version": "paragraph-v2",
                "chunk_id": make_chunk_id(
                    exhibit,
                    parser_version="html-v1",
                    splitter_version="paragraph-v2",
                    position=0,
                    source_locator="section-0",
                    text="Exhibit content.",
                ),
            }
        )
        with pytest.raises(ValueError, match="one chunk processing version"):
            await storage.publish(
                selected,
                [only_main, mixed_exhibit],
                {only_main.chunk_id: [1.0, 0.0], mixed_exhibit.chunk_id: [0.0, 1.0]},
            )
        assert await metadata.get_ready_manifest(selected.corpus_id) is None

        consistent_exhibit = chunk(exhibit, "Exhibit content.", 0)
        ready = await storage.publish(
            selected,
            [only_main, consistent_exhibit],
            {
                only_main.chunk_id: [1.0, 0.0],
                consistent_exhibit.chunk_id: [0.0, 1.0],
            },
        )
        assert ready.status == "ready"
        assert await storage.get_ready_corpus(selected.corpus_id) == ready
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_separate_corpus_versions_do_not_mix_vector_results(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    index = ChromaFilingVectorIndex(tmp_path / "vectors")
    storage = FilingCorpusStorageService(
        FileRawFilingStore(tmp_path / "raw"), metadata, index
    )
    try:
        version = await storage.store_document(
            document("quarter.htm"), b"<html>A</html>"
        )
        first = manifest([version])
        first_chunk = chunk(version, "First paragraph.", 0)
        second_chunk = chunk(version, "Second paragraph.", 1)
        ready_first = await storage.publish(
            first, [first_chunk], {first_chunk.chunk_id: [1.0, 0.0]}
        )
        second = first.model_copy(
            update={
                "index_version": "another-model-v2",
                "corpus_id": make_corpus_id(
                    asset="MA",
                    issuer_cik=CIK,
                    as_of=AS_OF,
                    documents=[version],
                    index_version="another-model-v2",
                ),
            }
        )
        ready_second = await storage.publish(
            second, [second_chunk], {second_chunk.chunk_id: [0.0, 1.0]}
        )
        assert [
            item.chunk_id for item in await index.search(ready_first, [1.0, 0.0], 2)
        ] == [first_chunk.chunk_id]
        assert [
            item.chunk_id for item in await index.search(ready_second, [0.0, 1.0], 2)
        ] == [second_chunk.chunk_id]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_raw_and_sql_reject_conflicting_versions(tmp_path: Path) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    raw = FileRawFilingStore(tmp_path / "raw")
    source = document("quarter.htm")
    try:
        stored = await raw.save(source, b"<html>A</html>")
        await metadata.upsert_document(stored)
        with pytest.raises(ValueError, match="content hash"):
            await raw.save(stored, b"<html>B</html>")
        with pytest.raises(ValueError, match="Conflicting SEC document metadata"):
            await metadata.upsert_document(
                stored.model_copy(update={"report_period_end": date(2026, 3, 31)})
            )
        assert stored.content_sha256 is not None
        version = FilingDocumentVersion(
            document_id=stored.document_id,
            content_sha256=stored.content_sha256,
        )
        assert stored.raw_file_ref is not None
        (tmp_path / "raw" / stored.raw_file_ref).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="content hash"):
            await raw.read(version)
        await raw.save(stored, b"<html>A</html>")
        assert await raw.read(version) == b"<html>A</html>"
        revised = await raw.save(source, b"<html>revised</html>")
        await metadata.upsert_document(revised)
        assert revised.document_id == stored.document_id
        assert revised.content_sha256 != stored.content_sha256
        assert await metadata.get_document(version) == stored
        item = chunk(version, "A statement.", 0)
        with pytest.raises(ValueError, match="chunk ID"):
            await metadata.upsert_chunks(
                [item.model_copy(update={"splitter_version": "paragraph-v2"})]
            )
    finally:
        await database.close()
