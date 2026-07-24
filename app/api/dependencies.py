from datetime import timedelta
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
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.market_data.cache import InMemoryTTLAssetProfileCache, InMemoryTTLCache
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.chat_service import ChatService


def get_ollama_client() -> OllamaChatClient:
    return OllamaChatClient()


def get_stock_prompt_builder() -> StockSnapshotPromptBuilder:
    return StockSnapshotPromptBuilder()


@cache
def get_yfinance_provider() -> YFinanceCompanyProfileProvider:
    settings = get_settings()
    return YFinanceCompanyProfileProvider(
        cache=InMemoryTTLAssetProfileCache(
            ttl=timedelta(seconds=settings.asset_profile_cache_ttl_seconds),
        ),
        fundamentals_cache=InMemoryTTLCache(
            ttl=timedelta(seconds=settings.asset_profile_cache_ttl_seconds),
        ),
    )


@cache
def get_optional_fmp_provider() -> FmpProvider | None:
    settings = get_settings()
    if (
        not settings.fmp_enabled
        or not settings.fmp_api_key
        or not settings.fmp_api_key.strip()
    ):
        return None

    return FmpProvider(
        cache=InMemoryTTLCache(
            ttl=timedelta(seconds=settings.fmp_cache_ttl_seconds),
        ),
    )


def get_company_peers_tool() -> CompanyPeersTool:
    return CompanyPeersTool(provider=get_optional_fmp_provider())


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
) -> AssetSnapshotService:
    return AssetSnapshotService(graph_runner=graph_runner)
