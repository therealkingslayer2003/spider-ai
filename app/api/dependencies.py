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
from app.core.config import get_settings
from app.infrastructure.db.database import Database
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.chat_service import ChatService
from app.services.snapshot_artifact_persistence_service import (
    SnapshotArtifactPersistenceService,
)


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
