import asyncio
import gzip
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl
from sqlalchemy import func, select

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.embeddings import OllamaFilingEmbeddingGenerator
from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.identity import make_document_id
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.services import SecFilingIngestionService
from app.agents.asset_thesis.rag.splitter import (
    SecFilingChunkSplitter,
    SplitterSettings,
)
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.core.config import Settings
from app.domain.schemas.thesis_rag import FilingDocument
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from app.infrastructure.db.models import (
    FilingChunkModel,
    FilingCorpusModel,
    FilingDocumentModel,
)
from app.llm.tokenization import NomicTokenCounter, TokenCounter
from tests.rag.test_inspect_thesis_rag_cli import (
    _processing_components,
    _sql_counts,
    _vector_inventory,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/sec/MA/ma-20260630.html.gz"
AS_OF = datetime(2026, 7, 31, tzinfo=UTC)


def filing() -> FilingDocument:
    return FilingDocument(
        document_id=make_document_id(
            "0001141391", "0001141391-26-000083", "ma-20260630.htm"
        ),
        issuer_cik="0001141391",
        accession_number="0001141391-26-000083",
        filename="ma-20260630.htm",
        form="10-Q",
        source_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/1141391/"
            "000114139126000083/ma-20260630.htm"
        ),
        published_at=datetime(2026, 7, 30, 14, 28, 40, tzinfo=UTC),
        report_period_end=date(2026, 6, 30),
    )


def sample_html() -> bytes:
    with gzip.open(FIXTURE, "rb") as file:
        return file.read()


class FakeEncoder:
    def __init__(self) -> None:
        self.calls = 0
        self.fail_at: int | None = None
        self.inputs: list[str] = []

    @staticmethod
    def vector(text: str) -> list[float]:
        for prefix in ("search_document: ", "search_query: "):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        digest = hashlib.sha256(text.encode()).digest()
        return [float(digest[index] + 1) for index in range(4)]

    async def embed(
        self, *, model: str, input: list[str], truncate: bool
    ) -> SimpleNamespace:
        assert model == "nomic-embed-text"
        assert truncate is False
        self.inputs.extend(input)
        self.calls += 1
        if self.fail_at == self.calls:
            raise RuntimeError("transient embedding failure")
        return SimpleNamespace(embeddings=[self.vector(text) for text in input])


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[bool, bool]] = []

    def encode(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> list[int]:
        self.calls.append((add_special_tokens, truncation))
        count = len(text.split())
        return list(range(count + (2 if add_special_tokens else 0)))


def token_counter() -> NomicTokenCounter:
    return NomicTokenCounter(Path("/unused-test-cache"), tokenizer=FakeTokenizer())


def embeddings(
    encoder: FakeEncoder, counter: TokenCounter | None = None
) -> OllamaFilingEmbeddingGenerator:
    return OllamaFilingEmbeddingGenerator(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        model_revision="fixed-test-revision",
        batch_size=32,
        max_input_chars=1600,
        max_input_tokens=450,
        token_counter=counter or token_counter(),
        client=encoder,
    )


def splitter(counter: TokenCounter | None = None) -> SecFilingChunkSplitter:
    return SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=450,
            max_chars=1600,
            overlap_tokens=40,
            embedding_max_tokens=450,
            embedding_max_chars=1600,
        ),
        counter or token_counter(),
    )


def test_env_configures_embedding_and_splitter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = (
        "OLLAMA_BASE_URL",
        "OLLAMA_EMBEDDING_MODEL",
        "OLLAMA_EMBEDDING_MODEL_REVISION",
        "OLLAMA_EMBEDDING_BATCH_SIZE",
        "OLLAMA_EMBEDDING_EXPECTED_DIMENSIONS",
        "OLLAMA_EMBEDDING_MAX_INPUT_CHARS",
        "OLLAMA_EMBEDDING_MAX_INPUT_TOKENS",
        "THESIS_RAG_CHUNK_MAX_CHARS",
        "THESIS_RAG_CHUNK_MAX_TOKENS",
        "THESIS_RAG_CHUNK_OVERLAP_TOKENS",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
        "OLLAMA_EMBEDDING_MODEL=nomic-embed-text\n"
        "OLLAMA_EMBEDDING_MODEL_REVISION=weights-2\n"
        "OLLAMA_EMBEDDING_BATCH_SIZE=7\n"
        "OLLAMA_EMBEDDING_EXPECTED_DIMENSIONS=768\n"
        "OLLAMA_EMBEDDING_MAX_INPUT_CHARS=900\n"
        "OLLAMA_EMBEDDING_MAX_INPUT_TOKENS=200\n"
        "THESIS_RAG_CHUNK_MAX_CHARS=800\n"
        "THESIS_RAG_CHUNK_MAX_TOKENS=160\n"
        "THESIS_RAG_CHUNK_OVERLAP_TOKENS=20\n"
    )
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    splitter, embedder = _processing_components(settings)
    assert embedder.model == "nomic-embed-text"
    assert embedder.base_url == "http://127.0.0.1:11434"
    assert embedder.batch_size == 7
    assert settings.ollama_embedding_expected_dimensions == 768
    assert embedder.max_input_chars == 900
    assert embedder.max_input_tokens == 200
    assert splitter.settings.max_chars == 800
    assert splitter.settings.max_tokens == 160
    assert splitter.settings.overlap_tokens == 20
    monkeypatch.setenv("THESIS_RAG_CHUNK_MAX_TOKENS", "201")
    with pytest.raises(ValueError, match="exceed the embedding token limit"):
        Settings(_env_file=env_file)  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_real_sec_html_preserves_qualifications_table_units_and_locations() -> (
    None
):
    raw = sample_html()
    document = filing().model_copy(
        update={"content_sha256": hashlib.sha256(raw).hexdigest()}
    )
    parsed = await SecHtmlFilingParser().parse(document, raw)
    chunks = await splitter().split(parsed)

    assert len(parsed.blocks) > 300
    assert len(chunks) > 100
    assert [block.order for block in parsed.blocks] == list(range(len(parsed.blocks)))
    assert any(
        "Net revenue increased 14%, or 12% on a currency-neutral basis" in block.text
        and "ITEM 2." in " ".join(block.section_path)
        for block in parsed.blocks
    )
    assert any(
        "(in millions, except per share data)" in block.text
        and "Three Months Ended June 30" in block.text
        and "Net Revenue" in block.text
        for block in parsed.blocks
        if block.kind == "table"
    )
    assert any(
        "(in millions, except per share data)" in chunk.text
        and "Net Revenue" in chunk.text
        for chunk in chunks
    )
    assert any(
        block.kind == "heading"
        and "Risk factors" in block.text
        and block.section_path[0] == "PART II"
        for block in parsed.blocks
    )
    assert any(
        block.text == "Net Revenue"
        and block.kind == "heading"
        and block.section_path[-1] == "Net Revenue"
        for block in parsed.blocks
    )
    assert all(chunk.document == parsed.document for chunk in chunks)
    assert all(chunk.source_locator for chunk in chunks)
    counter = token_counter()
    assert all(chunk.token_count == counter.count_text(chunk.text) for chunk in chunks)
    assert max(chunk.token_count for chunk in chunks) <= 450
    assert max(len(chunk.text) for chunk in chunks) <= 1600


@pytest.mark.asyncio
async def test_splitter_version_tracks_limits_and_keeps_sentence_boundary() -> None:
    raw = (
        b"<html><body><div>Item 2. Results</div><p>"
        + b"Net revenue rose. Incentives reduced reported growth. " * 30
        + b"</p></body></html>"
    )
    doc = filing().model_copy(
        update={"content_sha256": hashlib.sha256(raw).hexdigest()}
    )
    parsed = await SecHtmlFilingParser().parse(doc, raw)
    small = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=65,
            max_chars=250,
            overlap_tokens=3,
            embedding_max_tokens=70,
            embedding_max_chars=270,
        ),
        token_counter(),
    )
    large = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=90,
            max_chars=350,
            overlap_tokens=3,
            embedding_max_tokens=95,
            embedding_max_chars=370,
        ),
        token_counter(),
    )
    chunks = await small.split(parsed)
    assert small.version != large.version
    assert len(chunks) > 2
    assert all(chunk.token_count <= 65 and len(chunk.text) <= 250 for chunk in chunks)
    assert all(chunk.section_path == ["Item 2. Results"] for chunk in chunks)
    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert chunks[1].text.splitlines()[0] == chunks[0].text.splitlines()[-1]
    assert token_counter().count_text(chunks[0].text.splitlines()[-1]) <= 3
    changed_tokenizer = token_counter()
    changed_tokenizer.version += ";different-revision"
    assert (
        SecFilingChunkSplitter(small.settings, changed_tokenizer).version
        != small.version
    )


@pytest.mark.asyncio
async def test_splitter_reserves_document_prefix_and_special_token_overhead() -> None:
    raw = b"<html><body><p>" + b"Revenue rose. " * 70 + b"</p></body></html>"
    doc = filing().model_copy(
        update={"content_sha256": hashlib.sha256(raw).hexdigest()}
    )
    parsed = await SecHtmlFilingParser().parse(doc, raw)
    counter = token_counter()
    split = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=50,
            max_chars=500,
            overlap_tokens=0,
            embedding_max_tokens=50,
            embedding_max_chars=500,
        ),
        counter,
    )
    chunks = await split.split(parsed)
    assert len(chunks) > 1
    assert all(chunk.token_count == counter.count_text(chunk.text) for chunk in chunks)
    assert all(chunk.token_count <= 50 for chunk in chunks)
    assert all(
        counter.count_embedding_input(chunk.text, "document") <= 50 for chunk in chunks
    )
    assert all(
        len(counter.format_embedding_input(chunk.text, "document")) <= 500
        for chunk in chunks
    )
    assert max(chunk.token_count for chunk in chunks) < 50


@pytest.mark.asyncio
async def test_splitter_reserves_document_prefix_character_overhead() -> None:
    text = "word " * 39
    raw = f"<html><body><p>{text}</p></body></html>".encode()
    doc = filing().model_copy(
        update={"content_sha256": hashlib.sha256(raw).hexdigest()}
    )
    parsed = await SecHtmlFilingParser().parse(doc, raw)
    counter = token_counter()
    split = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=50,
            max_chars=200,
            overlap_tokens=0,
            embedding_max_tokens=50,
            embedding_max_chars=200,
        ),
        counter,
    )
    chunks = await split.split(parsed)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 200 for chunk in chunks)
    assert all(
        len(counter.format_embedding_input(chunk.text, "document")) <= 200
        for chunk in chunks
    )


@pytest.mark.asyncio
async def test_embedding_model_version_and_input_bounds() -> None:
    client = FakeEncoder()
    model = embeddings(client)
    changed_revision = OllamaFilingEmbeddingGenerator(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        model_revision="another-revision",
        batch_size=32,
        max_input_chars=1600,
        max_input_tokens=450,
        token_counter=token_counter(),
        client=client,
    )
    assert model.version != changed_revision.version
    with pytest.raises(ValueError, match="exceeds configured bounds"):
        await model.embed_query("x " * 1000)
    assert client.calls == 0
    assert await model.embed_query("revenue") == client.vector("revenue")
    assert client.inputs == ["search_query: revenue"]
    assert await model.embed_query("search_query: revenue") == client.vector("revenue")
    assert client.inputs[-1] == "search_query: revenue"
    strict = OllamaFilingEmbeddingGenerator(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        model_revision="fixed-test-revision",
        batch_size=32,
        max_input_chars=1600,
        max_input_tokens=3,
        token_counter=token_counter(),
        client=client,
    )
    with pytest.raises(ValueError, match="exceeds configured bounds"):
        await strict.embed_query("revenue")
    assert len(client.inputs) == 2


@pytest.mark.asyncio
async def test_real_filing_indexes_once_and_ready_corpus_is_searchable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    raw_store = FileRawFilingStore(tmp_path / "raw")
    vector_index = ChromaFilingVectorIndex(tmp_path / "vectors")
    upsert = AsyncMock(wraps=vector_index.upsert)
    monkeypatch.setattr(vector_index, "upsert", upsert)
    storage = FilingCorpusStorageService(raw_store, metadata, vector_index)
    encoder = FakeEncoder()
    counter = token_counter()
    embedder = embeddings(encoder, counter)
    service = SecFilingIngestionService(
        storage, SecHtmlFilingParser(), splitter(counter), embedder
    )
    raw = sample_html()
    try:
        first = await service.ingest_documents(
            asset="MA", as_of=AS_OF, documents=[(filing(), raw)]
        )
        assert first.status == "ready"
        assert await storage.get_ready_corpus(first.corpus_id) == first
        calls = encoder.calls
        assert calls > 1  # A real filing spans multiple embedding batches.
        assert encoder.inputs and all(
            item.startswith("search_document: ") for item in encoder.inputs
        )
        chunk_ids = await metadata.get_indexed_chunk_ids(first.corpus_id)
        assert len(chunk_ids) == len(set(chunk_ids))
        assert await asyncio.to_thread(
            _vector_inventory, vector_index, first, set(chunk_ids), 4
        ) == len(chunk_ids)
        cold_sql = await _sql_counts(database)
        stored = await metadata.get_document(first.documents[0])
        assert stored is not None and stored.raw_file_ref is not None
        raw_path = tmp_path / "raw" / stored.raw_file_ref
        raw_mtime = raw_path.stat().st_mtime_ns
        assert upsert.call_count == 1
        second = await service.ingest_documents(
            asset="MA", as_of=AS_OF, documents=[(filing(), raw)]
        )
        assert second == first
        assert encoder.calls == calls
        assert upsert.call_count == 1
        assert await _sql_counts(database) == cold_sql
        assert raw_path.stat().st_mtime_ns == raw_mtime
        assert await metadata.get_indexed_chunk_ids(first.corpus_id) == chunk_ids
        assert chunk_ids
        chunks = await metadata.get_chunks(chunk_ids)
        target = next(
            chunk for chunk in chunks if "Net revenue increased 14%" in chunk.text
        )
        matches = await vector_index.search(
            first, await embedder.embed_query(target.text), 3
        )
        assert encoder.inputs[-1].startswith("search_query: ")
        assert matches[0].chunk_id == target.chunk_id
        assert matches[0].distance == pytest.approx(0.0)
        assert await raw_store.read(first.documents[0]) == raw
        async with database.session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingDocumentModel)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingCorpusModel)
                )
                == 1
            )
            assert await session.scalar(
                select(func.count()).select_from(FilingChunkModel)
            ) == len(chunks)
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_embedding_failure_can_retry_without_publishing(tmp_path: Path) -> None:
    database = Database(tmp_path / "filings.db")
    metadata = SqlFilingMetadataRepository(database)
    storage = FilingCorpusStorageService(
        FileRawFilingStore(tmp_path / "raw"),
        metadata,
        ChromaFilingVectorIndex(tmp_path / "vectors"),
    )
    encoder = FakeEncoder()
    encoder.fail_at = 2
    service = SecFilingIngestionService(
        storage, SecHtmlFilingParser(), splitter(), embeddings(encoder)
    )
    try:
        with pytest.raises(RuntimeError, match="transient embedding failure"):
            await service.ingest_documents(
                asset="MA", as_of=AS_OF, documents=[(filing(), sample_html())]
            )
        async with database.session_factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(FilingCorpusModel)
                )
                == 0
            )
        encoder.fail_at = None
        ready = await service.ingest_documents(
            asset="MA", as_of=AS_OF, documents=[(filing(), sample_html())]
        )
        assert ready.status == "ready"
        assert await storage.get_ready_corpus(ready.corpus_id) == ready
    finally:
        await database.close()
