from datetime import timedelta
from functools import cache

from fastapi import Depends

from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.agents.asset_snapshot.tools import (
    CompanyPeersTool,
    SectorContextTool,
    StableAssetProfileSearchTool,
)
from app.core.config import get_settings
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.market_data.cache import InMemoryTTLAssetProfileCache
from app.market_data.yfinance_provider import YFinanceMarketDataProvider
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.chat_service import ChatService


def get_ollama_client() -> OllamaChatClient:
    return OllamaChatClient()


def get_prompt_builder() -> AssetSnapshotPromptBuilder:
    return AssetSnapshotPromptBuilder()


def get_sector_context_tool() -> SectorContextTool:
    return SectorContextTool()


def get_company_peers_tool() -> CompanyPeersTool:
    return CompanyPeersTool()


@cache
def get_profile_tool() -> StableAssetProfileSearchTool:
    settings = get_settings()
    cache = InMemoryTTLAssetProfileCache(
        ttl=timedelta(seconds=settings.asset_profile_cache_ttl_seconds),
    )
    provider = YFinanceMarketDataProvider(cache=cache)
    return StableAssetProfileSearchTool(market_data_provider=provider)


def get_graph_runner(
    profile_tool: StableAssetProfileSearchTool = Depends(get_profile_tool),
    sector_context_tool: SectorContextTool = Depends(get_sector_context_tool),
    company_peers_tool: CompanyPeersTool = Depends(get_company_peers_tool),
    prompt_builder: AssetSnapshotPromptBuilder = Depends(get_prompt_builder),
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> AssetSnapshotGraphRunner:
    return AssetSnapshotGraphRunner(
        profile_tool=profile_tool,
        sector_context_tool=sector_context_tool,
        company_peers_tool=company_peers_tool,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )


def get_chat_service(
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> ChatService:
    return ChatService(llm_client=llm_client)


def get_asset_snapshot_service(
    graph_runner: AssetSnapshotGraphRunner = Depends(get_graph_runner),
) -> AssetSnapshotService:
    return AssetSnapshotService(graph_runner=graph_runner)
