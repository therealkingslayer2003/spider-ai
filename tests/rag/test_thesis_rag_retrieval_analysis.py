"""Offline checks for the three independent Thesis filing RAG stages."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from app.agents.asset_thesis.rag.analysis import SecFilingAnalyticalGenerator
from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.context_builder import SecFilingContextBuilder
from app.agents.asset_thesis.rag.embeddings import OllamaFilingEmbeddingGenerator
from app.agents.asset_thesis.rag.identity import make_index_version
from app.agents.asset_thesis.rag.pipeline import SecFilingRagPipeline
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.reranking import LexicalFilingReranker
from app.agents.asset_thesis.rag.retrieval import (
    NoVectorsFoundError,
    SecFilingRetrievalService,
)
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.api import dependencies as wiring
from app.core.config import Settings
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    FilingCorpusManifest,
    FilingCorpusVersion,
    FilingDocument,
    FilingDocumentVersion,
    FilingEvidenceBundle,
    FilingEvidenceExcerpt,
    FilingEvidenceSource,
    FilingResearchAnswer,
    FilingRetrievalRequest,
    FilingVectorMatch,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from app.llm import tokenization
from app.llm.prompts.thesis_filing_prompt_builder import ThesisFilingPromptBuilder
from app.llm.tokenization import (
    ChatTokenizerUnavailableError,
    EstimatedChatTokenCounter,
    LocalChatTokenCounter,
    NomicTokenCounter,
)
from tests.rag.test_thesis_rag_storage import (
    chunk as stored_chunk,
)
from tests.rag.test_thesis_rag_storage import (
    document as stored_document,
)
from tests.rag.test_thesis_rag_storage import (
    manifest as stored_manifest,
)

AS_OF = datetime(2026, 7, 2, tzinfo=UTC)
CIK = "0000000123"
VERSION = FilingDocumentVersion(document_id="doc-1", content_sha256="a" * 64)
EMBEDDING_VERSION = "fake-embedding-v1"
INDEX_VERSION = make_index_version(
    embedding_model_version=EMBEDDING_VERSION,
    parser_version="p1",
    splitter_version="s1",
)
CORPUS = FilingCorpusVersion(corpus_id="corpus-1", index_version=INDEX_VERSION)


def _request(**changes: Any) -> FilingRetrievalRequest:
    values = {
        "research_id": "research-1",
        "question": "What drives revenue?",
        "asset": "TEST",
        "issuer_cik": CIK,
        "as_of": AS_OF,
        "corpus": CORPUS,
        "top_k": 2,
    }
    values.update(changes)
    return FilingRetrievalRequest.model_validate(values)


def _document(**changes: Any) -> FilingDocument:
    values = {
        "document_id": VERSION.document_id,
        "content_sha256": VERSION.content_sha256,
        "issuer_cik": CIK,
        "accession_number": "0000000123-26-000001",
        "filename": "report.htm",
        "form": "10-Q",
        "source_url": "https://www.sec.gov/Archives/edgar/data/123/1/report.htm",
        "published_at": AS_OF - timedelta(days=1),
        "report_period_end": date(2026, 6, 30),
        "raw_file_ref": "raw/report.htm",
    }
    values.update(changes)
    return FilingDocument.model_validate(values)


def _chunk(position: int, text: str | None = None) -> FilingChunk:
    return FilingChunk(
        chunk_id=f"chunk-{position}",
        document=VERSION,
        text=text or f"Revenue passage {position} with reported dollars.",
        section_path=["Note 3. Revenue"],
        position=position,
        source_locator=f"body > table:nth-of-type({position + 1})",
        token_count=7,
        parser_version="p1",
        splitter_version="s1",
    )


class _Metadata:
    def __init__(self) -> None:
        self.document = _document()
        self.chunks = [_chunk(0), _chunk(1), _chunk(2)]
        self.chunk_reads: list[list[str]] = []
        self.manifest = FilingCorpusManifest(
            corpus_id=CORPUS.corpus_id,
            asset="TEST",
            issuer_cik=CIK,
            as_of=AS_OF,
            documents=[VERSION],
            index_version=INDEX_VERSION,
            status="ready",
        )

    async def get_ready_manifest(self, corpus_id: str) -> FilingCorpusManifest | None:
        return self.manifest if corpus_id == CORPUS.corpus_id else None

    async def get_document(self, version: FilingDocumentVersion) -> FilingDocument:
        assert version == VERSION
        return self.document

    async def get_processing_versions(self, corpus_id: str) -> tuple[str, str]:
        return ("p1", "s1")

    async def get_chunks(self, chunk_ids: list[str]) -> list[FilingChunk]:
        self.chunk_reads.append(chunk_ids)
        # SQL is allowed to return a different row order; retrieval must restore rank.
        return list(
            reversed([item for item in self.chunks if item.chunk_id in chunk_ids])
        )


class _Embeddings:
    version = EMBEDDING_VERSION

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [1.0, 0.0]


class _Index:
    def __init__(self) -> None:
        self.calls = 0
        self.matches = [
            FilingVectorMatch(chunk_id="chunk-0", distance=0.8),
            FilingVectorMatch(chunk_id="chunk-1", distance=0.1),
        ]

    async def search(
        self, corpus: FilingCorpusManifest, query_vector: list[float], limit: int
    ) -> list[FilingVectorMatch]:
        self.calls += 1
        return self.matches[:limit]


def _retriever(
    metadata: _Metadata | SqlFilingMetadataRepository,
    embeddings: _Embeddings | OllamaFilingEmbeddingGenerator,
    index: _Index | ChromaFilingVectorIndex,
) -> SecFilingRetrievalService:
    return SecFilingRetrievalService(metadata, embeddings, index)


def _excerpt(rank: int, chunk_id: str, text: str) -> FilingEvidenceExcerpt:
    doc = _document()
    return FilingEvidenceExcerpt(
        rank=rank,
        chunk_id=chunk_id,
        text=text,
        retrieval_distance=float(rank) / 10,
        source=FilingEvidenceSource(
            document=VERSION,
            accession_number=doc.accession_number,
            filename=doc.filename,
            form=doc.form,
            source_url=doc.source_url,
            published_at=doc.published_at,
            report_period_end=doc.report_period_end,
            section_path=["Note 3. Revenue"],
            source_locator=f"body > table:nth-of-type({rank})",
        ),
    )


def _bundle(excerpts: list[FilingEvidenceExcerpt]) -> FilingEvidenceBundle:
    return FilingEvidenceBundle(
        request=_request(),
        parser_version="p1",
        splitter_version="s1",
        embedding_version=EMBEDDING_VERSION,
        excerpts=excerpts,
    )


class _ChatCounter:
    count_kind: Literal["local_tokenizer"] = "local_tokenizer"
    version = "test-chat-tokenizer-v1"

    def count_text(self, text: str) -> int:
        return len(text)

    def count_prompt(self, prompt: str) -> int:
        return len(prompt) + 4


class _ChatTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def encode(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> list[int]:
        assert not add_special_tokens and not truncation
        self.calls.append(("text", text))
        return [1] * len(text.split())

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        truncation: bool,
    ) -> list[int]:
        assert tokenize and add_generation_prompt and not truncation
        assert len(messages) == 1 and messages[0]["role"] == "user"
        self.calls.append(("prompt", messages[0]["content"]))
        return [1] * (len(messages[0]["content"].split()) + 4)


def test_local_chat_tokenizer_counts_prompt_and_pins_model(tmp_path: Path) -> None:
    tokenizer = _ChatTokenizer()
    counter = LocalChatTokenCounter(
        model="qwen3:14b",
        tokenizer_model="qwen3:14b",
        tokenizer_id="Qwen/Qwen3-14B",
        tokenizer_revision="revision-a",
        cache_dir=tmp_path,
        tokenizer=tokenizer,
    )
    assert counter.count_text("two words") == 2
    assert counter.count_prompt("two words") == 6
    assert tokenizer.calls == [("text", "two words"), ("prompt", "two words")]
    newer = LocalChatTokenCounter(
        model="qwen3:14b",
        tokenizer_model="qwen3:14b",
        tokenizer_id="Qwen/Qwen3-14B",
        tokenizer_revision="revision-b",
        cache_dir=tmp_path,
        tokenizer=tokenizer,
    )
    assert newer.version != counter.version
    with pytest.raises(ValueError, match="another Ollama model"):
        LocalChatTokenCounter(
            model="llama3.1:8b",
            tokenizer_model="qwen3:14b",
            tokenizer_id="Qwen/Qwen3-14B",
            tokenizer_revision="revision-a",
            cache_dir=tmp_path,
            tokenizer=tokenizer,
        )


@pytest.mark.parametrize("cause", ["model_mismatch", "missing_assets"])
def test_chat_counter_falls_back_with_larger_margin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    monkeypatch.chdir(tmp_path)
    model = "other:8b" if cause == "model_mismatch" else "qwen3:14b"
    settings = Settings(ollama_chat_model=model)
    monkeypatch.setattr(wiring, "get_settings", lambda: settings)

    def unavailable(*args: Any) -> Any:
        raise ChatTokenizerUnavailableError("assets missing")

    monkeypatch.setattr(tokenization, "_load_chat_tokenizer", unavailable)
    wiring.get_filing_chat_token_counter.cache_clear()
    wiring.get_filing_context_builder.cache_clear()
    try:
        counter = wiring.get_filing_chat_token_counter()
        assert isinstance(counter, EstimatedChatTokenCounter)
        assert counter.count_kind == "estimated"
        assert model in counter.version
        assert counter.count_prompt("Revenue $1,234") == counter.count_text(
            "Revenue $1,234"
        )
        packed = wiring.get_filing_context_builder().build(
            _bundle([_excerpt(1, "chunk-1", "Revenue was $1,234")]),
            task="answer",
        )
        assert packed.budget.count_kind == "estimated"
        assert packed.budget.safety_margin_tokens == 512
        assert packed.budget.counter_version == counter.version
    finally:
        wiring.get_filing_context_builder.cache_clear()
        wiring.get_filing_chat_token_counter.cache_clear()


def test_chat_counter_uses_local_assets_and_smaller_margin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    monkeypatch.setattr(wiring, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tokenization, "_load_chat_tokenizer", lambda *args: _ChatTokenizer()
    )
    wiring.get_filing_chat_token_counter.cache_clear()
    wiring.get_filing_context_builder.cache_clear()
    try:
        counter = wiring.get_filing_chat_token_counter()
        assert isinstance(counter, LocalChatTokenCounter)
        packed = wiring.get_filing_context_builder().build(
            _bundle([_excerpt(1, "chunk-1", "Revenue was $1,234")]),
            task="answer",
        )
        assert packed.budget.count_kind == "local_tokenizer"
        assert packed.budget.safety_margin_tokens == 128
    finally:
        wiring.get_filing_context_builder.cache_clear()
        wiring.get_filing_chat_token_counter.cache_clear()


def test_fallback_margin_must_fit_context_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="output reserve exceeds"):
        Settings(ollama_num_ctx=2560)


def test_missing_chat_tokenizer_snapshot_is_an_offline_fallback_condition(
    tmp_path: Path,
) -> None:
    with pytest.raises(ChatTokenizerUnavailableError, match="unavailable locally"):
        tokenization._load_chat_tokenizer(
            "Qwen/Qwen3-14B", "missing-revision", str(tmp_path)
        )


def _builder(
    *, window: int = 5000, output: int = 500, margin: int = 100
) -> SecFilingContextBuilder:
    return SecFilingContextBuilder(
        _ChatCounter(),
        ThesisFilingPromptBuilder(),
        context_window_tokens=window,
        reserved_output_tokens=output,
        safety_margin_tokens=margin,
    )


class _Model:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def generate(self, message: str, *, response_schema: Any) -> Any:
        self.calls.append(message)
        return response_schema.model_validate(self.payload)


ANSWER = {
    "status": "answered",
    "answer": {"text": "Revenue increased.", "evidence_ids": ["E1"]},
    "supported_claims": [
        {"text": "The filing reports higher revenue.", "evidence_ids": ["E1"]}
    ],
    "interpretations": [],
    "assumptions": [],
    "uncertainties": [],
    "missing_data": [],
}


@pytest.mark.asyncio
async def test_retrieval_enforces_scope_and_preserves_rank_with_one_content_read() -> (
    None
):
    metadata, embeddings, index = _Metadata(), _Embeddings(), _Index()
    result = await _retriever(metadata, embeddings, index).retrieve(_request())
    assert [item.chunk_id for item in result.excerpts] == ["chunk-1", "chunk-0"]
    assert [item.rank for item in result.excerpts] == [1, 2]
    assert [item.retrieval_distance for item in result.excerpts] == [0.1, 0.8]
    assert result.excerpts[0].text == metadata.chunks[1].text
    assert result.excerpts[0].source.report_period_end == date(2026, 6, 30)
    assert result.excerpts[0].source.section_path == ["Note 3. Revenue"]
    assert metadata.chunk_reads == [["chunk-1", "chunk-0"]]
    assert embeddings.queries == ["What drives revenue?"]
    assert index.calls == 1


@pytest.mark.asyncio
async def test_reranking_prefers_matching_metric_and_period_after_dense_search() -> (
    None
):
    metadata, embeddings, index = _Metadata(), _Embeddings(), _Index()
    metadata.chunks = [
        _chunk(0, "Revenue recognized from obligations for three months was $10."),
        _chunk(
            1,
            "Three Months Ended June 30, | 2026\n"
            "Net revenue | $ | 100\nOperating income | $ | 50",
        ),
        _chunk(2, "Six months ended June 30, 2026: other financial highlights."),
    ]
    index.matches = [
        FilingVectorMatch(chunk_id="chunk-0", distance=0.1),
        FilingVectorMatch(chunk_id="chunk-1", distance=0.2),
        FilingVectorMatch(chunk_id="chunk-2", distance=0.3),
    ]
    request = _request(
        question="What was net revenue for three months ended June 30, 2026?",
        top_k=1,
    )
    dense = await _retriever(metadata, embeddings, index).retrieve(request)
    assert [item.chunk_id for item in dense.excerpts] == ["chunk-0"]
    reranked = await SecFilingRetrievalService(
        metadata,
        embeddings,
        index,
        reranker=LexicalFilingReranker(),
        candidate_k=3,
    ).retrieve(request)
    assert [item.chunk_id for item in reranked.excerpts] == ["chunk-1"]
    assert reranked.excerpts[0].retrieval_distance == 0.2
    assert reranked.ranking_version == "dense-lexical-v1"
    assert metadata.chunk_reads == [["chunk-0"], ["chunk-0", "chunk-1", "chunk-2"]]


@pytest.mark.asyncio
async def test_retrieval_rejects_wrong_scope_future_filing_and_embedding_version() -> (
    None
):
    metadata, embeddings, index = _Metadata(), _Embeddings(), _Index()
    service = _retriever(metadata, embeddings, index)
    for changes in (
        {"issuer_cik": "0000000456"},
        {"asset": "OTHER"},
        {"as_of": AS_OF - timedelta(days=1)},
        {"corpus": FilingCorpusVersion(corpus_id="corpus-1", index_version="old")},
    ):
        with pytest.raises(ValueError, match="selection"):
            await service.retrieve(_request(**changes))
    metadata.document = _document(published_at=AS_OF + timedelta(days=1))
    with pytest.raises(RuntimeError, match="future document"):
        await service.retrieve(_request())
    metadata.document = _document()
    embeddings.version = "changed-weights"
    with pytest.raises(ValueError, match="embedding configuration"):
        await service.retrieve(_request())
    assert not embeddings.queries and index.calls == 0
    assert metadata.chunk_reads == []


@pytest.mark.asyncio
async def test_empty_result_from_ready_index_is_an_error() -> None:
    metadata, embeddings, index = _Metadata(), _Embeddings(), _Index()
    index.matches = []
    with pytest.raises(NoVectorsFoundError, match="search returned no vectors"):
        await _retriever(metadata, embeddings, index).retrieve(_request())
    assert metadata.chunk_reads == []


class _Tokenizer:
    def encode(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> list[int]:
        assert truncation is False
        count = len(text.split()) + (2 if add_special_tokens else 0)
        return list(range(count))


class _OllamaEmbeddingsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], bool]] = []

    async def embed(self, *, model: str, input: list[str], truncate: bool) -> Any:
        self.calls.append((model, input, truncate))
        return SimpleNamespace(embeddings=[[1.0, 0.0] for _ in input])


@pytest.mark.asyncio
async def test_query_uses_one_nomic_prefix_and_matching_index_version(
    tmp_path: Path,
) -> None:
    client = _OllamaEmbeddingsClient()
    counter = NomicTokenCounter(tmp_path, tokenizer=_Tokenizer())
    embeddings = OllamaFilingEmbeddingGenerator(
        model="nomic-embed-text:v1.5",
        base_url="http://localhost:11434",
        model_revision="test-weight-revision",
        batch_size=2,
        max_input_chars=1600,
        max_input_tokens=450,
        token_counter=counter,
        client=client,
    )
    metadata, index = _Metadata(), _Index()
    metadata.manifest.index_version = make_index_version(
        embedding_model_version=embeddings.version,
        parser_version="p1",
        splitter_version="s1",
    )
    request = _request(
        corpus=FilingCorpusVersion(
            corpus_id="corpus-1", index_version=metadata.manifest.index_version
        ),
        question="search_query: revenue",
    )
    await _retriever(metadata, embeddings, index).retrieve(request)
    assert client.calls == [("nomic-embed-text:v1.5", ["search_query: revenue"], False)]


def test_context_builder_deduplicates_and_packs_complete_chunks() -> None:
    first = _excerpt(1, "chunk-1", "Revenue | 2026 | USD millions\nCard volume | 42")
    repeated_id = first.model_copy(update={"rank": 2})
    repeated_text = _excerpt(
        3, "chunk-3", "Revenue | 2026 | USD millions  Card volume | 42"
    )
    extra = _excerpt(4, "chunk-4", "Other disclosed operating details")
    bundle = _bundle([first, repeated_id, repeated_text, extra])
    prompts = ThesisFilingPromptBuilder()
    counter = _ChatCounter()
    one_context = prompts.format_excerpt("E1", first)
    input_limit = counter.count_prompt(
        prompts.build(
            task="answer", request=bundle.request, formatted_context=one_context
        )
    )
    packed = _builder(window=input_limit + 100 + 20, output=100, margin=20).build(
        bundle, task="answer"
    )
    assert packed.included_chunk_ids == ["chunk-1"]
    assert packed.excluded_chunk_ids == ["chunk-3", "chunk-4"]
    assert list(packed.citations) == ["E1"]
    assert packed.citations["E1"].chunk_id == "chunk-1"
    assert first.text in packed.formatted_context  # complete table context, no slicing
    assert packed.budget.count_kind == "local_tokenizer"
    assert packed.budget.prompt_tokens_estimated == input_limit
    assert packed.budget.deduplicated_chunks == 2
    assert packed.budget.budget_excluded_chunks == 1


def test_context_keeps_source_dates_and_section_without_technical_ids() -> None:
    item = _excerpt(1, "chunk-1", "Net revenue | $ | 100")
    packed = _builder().build(_bundle([item]), task="answer")
    assert "[E1] form=10-Q" in packed.formatted_context
    assert "published=2026-07-01" in packed.formatted_context
    assert "report_period_end=2026-06-30" in packed.formatted_context
    assert "section=Note 3. Revenue" in packed.formatted_context
    assert "chunk_id=" not in packed.formatted_context
    assert "document_id=" not in packed.formatted_context
    assert "locator=" not in packed.formatted_context
    assert "https://" not in packed.formatted_context
    assert packed.citations["E1"].source.source_locator == item.source.source_locator


def test_context_builder_counts_question_instructions_and_output_reserve() -> None:
    item = _excerpt(1, "chunk-1", "A short filing passage")
    bundle = _bundle([item])
    counter = _ChatCounter()
    prompts = ThesisFilingPromptBuilder()
    base = counter.count_prompt(
        prompts.build(task="answer", request=bundle.request, formatted_context="")
    )
    with pytest.raises(ValueError, match="instructions and question"):
        _builder(window=base + 100 + 20 - 1, output=100, margin=20).build(
            bundle, task="answer"
        )
    packed = _builder(window=base + 100 + 20, output=100, margin=20).build(
        bundle, task="answer"
    )
    assert packed.excluded_chunk_ids == ["chunk-1"]
    assert packed.budget.prompt_tokens_estimated == base
    assert packed.budget.remaining_input_tokens_estimated == 0


@pytest.mark.asyncio
async def test_generation_validates_structure_and_supplied_citations() -> None:
    packed = _builder().build(
        _bundle([_excerpt(1, "chunk-1", "Revenue increased in USD millions.")]),
        task="answer",
    )
    model = _Model(ANSWER)
    generator = SecFilingAnalyticalGenerator(
        model,
        ThesisFilingPromptBuilder(),
        _ChatCounter(),
        model_version="test-chat-v1",
    )
    output = await generator.generate(packed, task="answer")
    assert output.answer.status == "answered"
    assert output.answer.answer.evidence_ids == ["E1"]
    assert output.references["E1"].document == VERSION
    assert output.model_version == "test-chat-v1"
    assert output.estimated_output_tokens > 0
    assert packed.formatted_context in model.calls[0]
    assert _ChatCounter().count_prompt(model.calls[0]) == (
        packed.budget.prompt_tokens_estimated
    )
    assert "What drives revenue?" in model.calls[0]
    assert "untrusted data" in model.calls[0]
    assert "State the reported unit and scale" in model.calls[0]
    model.payload = {
        **ANSWER,
        "answer": {"text": "Unsupported", "evidence_ids": ["E9"]},
    }
    with pytest.raises(ValueError, match="unavailable evidence IDs"):
        await generator.generate(packed, task="answer")
    model.payload = {
        **ANSWER,
        "supported_claims": [{"text": "Uncited fact", "evidence_ids": []}],
    }
    with pytest.raises(ValidationError, match="Supported factual claims"):
        await generator.generate(packed, task="answer")
    model.payload = {
        **ANSWER,
        "assumptions": [
            {"text": "The filing says E9 is important.", "evidence_ids": ["E9"]}
        ],
    }
    with pytest.raises(ValueError, match="unavailable evidence IDs"):
        await generator.generate(packed, task="answer")
    model.payload = {
        **ANSWER,
        "assumptions": [
            {"text": "The filing says E1 is important.", "evidence_ids": []}
        ],
    }
    with pytest.raises(ValidationError, match="Inline evidence labels"):
        await generator.generate(packed, task="answer")
    model.payload = {key: value for key, value in ANSWER.items() if key != "answer"}
    derived = await generator.generate(packed, task="answer")
    assert derived.answer.answer == derived.answer.supported_claims[0]


@pytest.mark.parametrize(
    "field",
    ["supported_claims", "interpretations", "assumptions", "uncertainties"],
)
@pytest.mark.asyncio
async def test_generation_rejects_unknown_citations_in_every_narrative_field(
    field: str,
) -> None:
    packed = _builder().build(
        _bundle([_excerpt(1, "chunk-1", "Revenue increased.")]), task="answer"
    )
    model = _Model(
        {
            **ANSWER,
            field: [{"text": "Unsupported detail", "evidence_ids": ["E7"]}],
        }
    )
    generator = SecFilingAnalyticalGenerator(
        model, ThesisFilingPromptBuilder(), _ChatCounter(), model_version="chat-v1"
    )
    with pytest.raises(ValueError, match="unavailable evidence IDs: E7"):
        await generator.generate(packed, task="answer")


@pytest.mark.asyncio
async def test_generation_rejects_unknown_citation_in_missing_data() -> None:
    packed = _builder().build(
        _bundle([_excerpt(1, "chunk-1", "Revenue increased.")]), task="answer"
    )
    model = _Model(
        {
            **ANSWER,
            "status": "partial_evidence",
            "missing_data": [
                {"text": "Second requested metric", "evidence_ids": ["E7"]}
            ],
        }
    )
    generator = SecFilingAnalyticalGenerator(
        model, ThesisFilingPromptBuilder(), _ChatCounter(), model_version="chat-v1"
    )
    with pytest.raises(ValueError, match="unavailable evidence IDs: E7"):
        await generator.generate(packed, task="answer")


def test_answer_status_distinguishes_complete_partial_and_insufficient() -> None:
    assert FilingResearchAnswer.model_validate(ANSWER).missing_data == []
    partial = {
        **ANSWER,
        "status": "partial_evidence",
        "missing_data": [
            {"text": "The second requested value is missing", "evidence_ids": []}
        ],
    }
    assert FilingResearchAnswer.model_validate(partial).status == "partial_evidence"
    with pytest.raises(ValidationError, match="Missing requested data"):
        FilingResearchAnswer.model_validate(
            {**ANSWER, "missing_data": partial["missing_data"]}
        )
    with pytest.raises(ValidationError, match="must identify missing data"):
        FilingResearchAnswer.model_validate({**ANSWER, "status": "partial_evidence"})
    with pytest.raises(ValidationError, match="Insufficient evidence"):
        FilingResearchAnswer.model_validate(
            {
                "status": "insufficient_evidence",
                "assumptions": [{"text": "Unrelated premise", "evidence_ids": []}],
                "missing_data": partial["missing_data"],
            }
        )


@pytest.mark.asyncio
async def test_empty_context_returns_explicit_result_without_llm() -> None:
    bundle = _bundle([_excerpt(1, "chunk-1", "Revenue " * 5000)])
    packed = _builder().build(bundle, task="answer")
    assert packed.citations == {}
    model = _Model(ANSWER)
    generator = SecFilingAnalyticalGenerator(
        model,
        ThesisFilingPromptBuilder(),
        _ChatCounter(),
        model_version="test-chat-v1",
    )
    result = await generator.generate(packed, task="answer")
    assert result.answer.status == "insufficient_evidence"
    assert result.answer.answer is None
    assert result.answer.missing_data
    assert result.references == {}
    assert model.calls == []


@pytest.mark.asyncio
async def test_isolated_sql_chroma_pipeline_retains_all_stage_outputs(
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
            stored_document("quarter.htm"), b"<html>Revenue and debt</html>"
        )
        chunks = [
            stored_chunk(version, "Revenue increased.", 0),
            stored_chunk(version, "Debt remained stable.", 1),
        ]
        ready = await storage.publish(
            stored_manifest([version]),
            chunks,
            {chunks[0].chunk_id: [1.0, 0.0], chunks[1].chunk_id: [0.0, 1.0]},
        )
        assert ready.index_version is not None
        embeddings = _Embeddings()
        embeddings.version = "test-embedding-v1"
        model = _Model(ANSWER)
        prompts = ThesisFilingPromptBuilder()
        pipeline = SecFilingRagPipeline(
            _retriever(metadata, embeddings, index),
            SecFilingContextBuilder(
                _ChatCounter(),
                prompts,
                context_window_tokens=5000,
                reserved_output_tokens=500,
                safety_margin_tokens=100,
            ),
            SecFilingAnalyticalGenerator(
                model,
                prompts,
                _ChatCounter(),
                model_version="test-chat-v1",
            ),
        )
        request = FilingRetrievalRequest(
            research_id="isolated-smoke",
            question="revenue",
            asset="MA",
            issuer_cik=ready.issuer_cik,
            as_of=ready.as_of,
            corpus=FilingCorpusVersion(
                corpus_id=ready.corpus_id, index_version=ready.index_version
            ),
            top_k=5,
        )
        run = await pipeline.run(request)
        assert len(run.retrieval.excerpts) == 2
        assert run.retrieval.excerpts[0].chunk_id == chunks[0].chunk_id
        assert run.context.citations["E1"].text == "Revenue increased."
        assert run.generation.answer.answer.evidence_ids == ["E1"]
        assert run.generation.references["E1"].document == version
        assert (
            run.model_dump(mode="json")["retrieval"]["request"]["question"] == "revenue"
        )
    finally:
        await database.close()
