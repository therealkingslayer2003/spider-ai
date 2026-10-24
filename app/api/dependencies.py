import logging
from functools import cache

from fastapi import Depends

from app.agents.asset_snapshot.router.graph import AssetSnapshotRouterGraph
from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.agents.asset_snapshot.stock.graph import StockSnapshotSubgraph
from app.agents.asset_snapshot.tools import (
    CompanyFundamentalsTool,
    CompanyPeersTool,
    CompanyProfileTool,
)
from app.agents.asset_thesis.graph import AssetThesisGraph
from app.agents.asset_thesis.rag.analysis import SecFilingAnalyticalGenerator
from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.context_builder import SecFilingContextBuilder
from app.agents.asset_thesis.rag.embeddings import OllamaFilingEmbeddingGenerator
from app.agents.asset_thesis.rag.pipeline import SecFilingRagPipeline
from app.agents.asset_thesis.rag.reranking import LexicalFilingReranker
from app.agents.asset_thesis.rag.services import SecFilingRetrievalService
from app.agents.asset_thesis.runner import AssetThesisGraphRunner
from app.core.config import get_settings
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.llm.prompts.thesis_filing_prompt_builder import ThesisFilingPromptBuilder
from app.llm.tokenization import (
    ChatTokenCounter,
    ChatTokenizerUnavailableError,
    EstimatedChatTokenCounter,
    LocalChatTokenCounter,
    NomicTokenCounter,
)
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.asset_thesis_service import AssetThesisService
from app.services.chat_service import ChatService
from app.services.snapshot_artifact_persistence_service import (
    SnapshotArtifactPersistenceService,
)

logger = logging.getLogger(__name__)


def get_ollama_client() -> OllamaChatClient:
    return OllamaChatClient()


def get_stock_prompt_builder() -> StockSnapshotPromptBuilder:
    return StockSnapshotPromptBuilder()


@cache
def get_database() -> Database:
    return Database(path=get_settings().spider_ai_db_path)


@cache
def get_snapshot_artifact_persistence_service() -> SnapshotArtifactPersistenceService:
    settings = get_settings()
    return SnapshotArtifactPersistenceService(
        database=get_database(),
        model=settings.ollama_chat_model,
        prompt_version="stock_snapshot_peer_landscape_v4",
    )


@cache
def get_yfinance_provider() -> YFinanceCompanyProfileProvider:
    return YFinanceCompanyProfileProvider()


@cache
def get_optional_fmp_provider() -> FmpProvider | None:
    settings = get_settings()
    if (
        not settings.fmp_enabled
        or not settings.fmp_api_key
        or not settings.fmp_api_key.strip()
    ):
        return None

    return FmpProvider()


@cache
def get_company_peers_tool() -> CompanyPeersTool:
    return CompanyPeersTool(
        provider=get_optional_fmp_provider(),
        profile_tool=get_profile_tool(),
    )


@cache
def get_company_fundamentals_tool() -> CompanyFundamentalsTool:
    return CompanyFundamentalsTool(provider=get_yfinance_provider())


@cache
def get_profile_tool() -> CompanyProfileTool:
    return CompanyProfileTool(
        primary_provider=get_yfinance_provider(),
        fallback_provider=get_optional_fmp_provider(),
    )


def get_stock_snapshot_subgraph(
    profile_tool: CompanyProfileTool = Depends(get_profile_tool),
    company_peers_tool: CompanyPeersTool = Depends(get_company_peers_tool),
    company_fundamentals_tool: CompanyFundamentalsTool = Depends(
        get_company_fundamentals_tool
    ),
    prompt_builder: StockSnapshotPromptBuilder = Depends(get_stock_prompt_builder),
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> StockSnapshotSubgraph:
    return StockSnapshotSubgraph(
        company_profile_tool=profile_tool,
        company_peers_tool=company_peers_tool,
        company_fundamentals_tool=company_fundamentals_tool,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )


def get_asset_snapshot_router_graph(
    stock_snapshot_subgraph: StockSnapshotSubgraph = Depends(
        get_stock_snapshot_subgraph
    ),
) -> AssetSnapshotRouterGraph:
    return AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_snapshot_subgraph)


def get_graph_runner(
    router_graph: AssetSnapshotRouterGraph = Depends(get_asset_snapshot_router_graph),
) -> AssetSnapshotGraphRunner:
    return AssetSnapshotGraphRunner(router_graph=router_graph)


def get_chat_service(
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> ChatService:
    return ChatService(llm_client=llm_client)


def get_asset_snapshot_service(
    graph_runner: AssetSnapshotGraphRunner = Depends(get_graph_runner),
    persistence_service: SnapshotArtifactPersistenceService = Depends(
        get_snapshot_artifact_persistence_service
    ),
) -> AssetSnapshotService:
    return AssetSnapshotService(
        graph_runner=graph_runner,
        persistence_service=persistence_service,
    )


def get_asset_thesis_graph() -> AssetThesisGraph:
    return AssetThesisGraph()


@cache
def get_filing_retrieval_service() -> SecFilingRetrievalService:
    """Independent RAG entry point; graph wiring follows in a later stage."""
    settings = get_settings()
    counter = NomicTokenCounter(settings.thesis_rag_tokenizer_cache_path)
    embeddings = OllamaFilingEmbeddingGenerator(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
        model_revision=settings.ollama_embedding_model_revision,
        batch_size=settings.ollama_embedding_batch_size,
        max_input_chars=settings.ollama_embedding_max_input_chars,
        max_input_tokens=settings.ollama_embedding_max_input_tokens,
        token_counter=counter,
    )
    return SecFilingRetrievalService(
        SqlFilingMetadataRepository(get_database()),
        embeddings,
        ChromaFilingVectorIndex(settings.spider_ai_chroma_path),
        reranker=(
            LexicalFilingReranker()
            if settings.thesis_rag_retrieval_rerank_enabled else None
        ),
        candidate_k=settings.thesis_rag_retrieval_candidate_k,
    )


@cache
def get_thesis_filing_prompt_builder() -> ThesisFilingPromptBuilder:
    return ThesisFilingPromptBuilder()


@cache
def get_filing_chat_token_counter() -> ChatTokenCounter:
    settings = get_settings()
    if settings.ollama_chat_model != settings.thesis_rag_chat_tokenizer_model:
        logger.warning(
            "thesis_rag.chat_tokenizer.fallback model=%s reason=model_mismatch",
            settings.ollama_chat_model,
        )
        return EstimatedChatTokenCounter(settings.ollama_chat_model)
    counter = LocalChatTokenCounter(
        model=settings.ollama_chat_model,
        tokenizer_model=settings.thesis_rag_chat_tokenizer_model,
        tokenizer_id=settings.thesis_rag_chat_tokenizer_id,
        tokenizer_revision=settings.thesis_rag_chat_tokenizer_revision,
        cache_dir=settings.thesis_rag_tokenizer_cache_path,
    )
    try:
        counter.ensure_available()
    except ChatTokenizerUnavailableError as exc:
        logger.warning(
            "thesis_rag.chat_tokenizer.fallback model=%s reason=%s",
            settings.ollama_chat_model,
            exc,
        )
        return EstimatedChatTokenCounter(settings.ollama_chat_model)
    return counter


@cache
def get_filing_context_builder() -> SecFilingContextBuilder:
    settings = get_settings()
    counter = get_filing_chat_token_counter()
    margin = settings.thesis_rag_generation_safety_margin_tokens
    if counter.count_kind == "estimated":
        margin = max(
            margin, settings.thesis_rag_generation_fallback_safety_margin_tokens
        )
    return SecFilingContextBuilder(
        counter,
        get_thesis_filing_prompt_builder(),
        context_window_tokens=settings.ollama_num_ctx,
        reserved_output_tokens=settings.thesis_rag_generation_reserved_output_tokens,
        safety_margin_tokens=margin,
    )


def get_filing_analytical_generator() -> SecFilingAnalyticalGenerator:
    return SecFilingAnalyticalGenerator(
        get_ollama_client(),
        get_thesis_filing_prompt_builder(),
        get_filing_chat_token_counter(),
        model_version=get_settings().ollama_chat_model,
    )


def get_filing_rag_pipeline() -> SecFilingRagPipeline:
    return SecFilingRagPipeline(
        get_filing_retrieval_service(),
        get_filing_context_builder(),
        get_filing_analytical_generator(),
    )


def get_asset_thesis_graph_runner(
    thesis_graph: AssetThesisGraph = Depends(get_asset_thesis_graph),
) -> AssetThesisGraphRunner:
    return AssetThesisGraphRunner(thesis_graph=thesis_graph)


def get_asset_thesis_service(
    graph_runner: AssetThesisGraphRunner = Depends(get_asset_thesis_graph_runner),
) -> AssetThesisService:
    return AssetThesisService(graph_runner=graph_runner)
