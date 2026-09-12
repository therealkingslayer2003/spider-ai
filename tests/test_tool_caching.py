from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.agents.asset_snapshot.tools import (
    CompanyFundamentalsTool,
    CompanyPeersTool,
    CompanyProfileTool,
)
from app.agents.asset_snapshot.tools.cache import InMemoryTTLCache
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import CompanyFundamentalsContext
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from tests.test_asset_snapshot_context_tools import make_profile


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.now


def make_tool(kind, cache=None):
    provider = AsyncMock()
    enrichment = AsyncMock(run=AsyncMock(return_value=make_profile("V")))
    if kind == "profile":
        fetch = provider.get_company_profile
        fetch.return_value = make_profile()
        tool = CompanyProfileTool(provider, None, cache=cache)
    elif kind == "peers":
        fetch = provider.get_company_peers
        fetch.return_value = CompanyPeersContext(
            asset="MA",
            provider="test",
            peers=[CompanyPeer(ticker="V")],
        )
        tool = CompanyPeersTool(provider, enrichment, cache=cache)
    else:
        fetch = provider.get_fundamentals
        fetch.return_value = CompanyFundamentalsContext(
            asset="MA",
            provider="test",
            revenue=0.0,
        )
        tool = CompanyFundamentalsTool(provider, cache=cache)
    return tool, fetch, enrichment


async def run_tool(tool, profile=None):
    profile = profile if profile is not None else make_profile()
    if isinstance(tool, CompanyProfileTool):
        return await tool.run(profile.asset, profile.asset_type)
    return await tool.run(profile)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "peers", "fundamentals"])
async def test_default_cache_expires_at_five_hours_without_sliding(kind, monkeypatch):
    clock = Clock()
    module = {
        "profile": "company_profile",
        "peers": "company_peers",
        "fundamentals": "company_fundamentals",
    }[kind]
    monkeypatch.setattr(
        f"app.agents.asset_snapshot.tools.{module}.InMemoryTTLCache",
        lambda: InMemoryTTLCache(now=clock),
    )
    tool, fetch, enrichment = make_tool(kind)
    first = await run_tool(tool)
    clock.now += timedelta(hours=5) - timedelta(seconds=1)
    cached = await run_tool(tool)
    assert cached == first
    assert cached is not first
    assert fetch.await_count == 1
    if kind == "peers":
        assert enrichment.run.await_count == 1
    clock.now += timedelta(seconds=1)
    await run_tool(tool)
    assert fetch.await_count == 2
    if kind == "peers":
        assert enrichment.run.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "peers", "fundamentals"])
async def test_cache_results_are_independent_deep_copies(kind):
    tool, fetch, _ = make_tool(kind)
    result = await run_tool(tool)
    expected = result.model_copy(deep=True)

    def mutate(context):
        if kind == "profile":
            context.business_summary = "Edited"
        elif kind == "peers":
            context.peers[0].profile.business_summary = "Edited"
            context.peers.clear()
        else:
            context.revenue = 123.0

    mutate(result)
    fetch.return_value.provider = "changed_at_source"
    cached = await run_tool(tool)
    assert cached == expected
    mutate(cached)
    assert await run_tool(tool) == expected
    assert fetch.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "peers", "fundamentals"])
async def test_cache_keys_normalize_symbols_and_separate_asset_types(kind):
    tool, fetch, _ = make_tool(kind)
    await run_tool(tool, make_profile(" ma "))
    await run_tool(tool, make_profile("MA"))
    assert fetch.await_count == 1
    await run_tool(tool, make_profile("OTHER"))
    assert fetch.await_count == 2
    await run_tool(
        tool, make_profile().model_copy(update={"asset_type": AssetType.ETF})
    )
    assert fetch.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "peers", "fundamentals"])
@pytest.mark.parametrize("failure", ["empty", "exception"])
async def test_empty_or_failed_results_are_not_cached(kind, failure):
    tool, fetch, _ = make_tool(kind)
    success = fetch.return_value
    if failure == "exception":
        empty = RuntimeError("temporarily offline")
    elif kind == "profile":
        empty = None
    elif kind == "peers":
        empty = CompanyPeersContext(asset="MA", provider="test", peers=[])
    else:
        empty = CompanyFundamentalsContext(asset="MA", provider="test")
    fetch.side_effect = [empty, success]

    await run_tool(tool)
    result = await run_tool(tool)
    assert result is not None
    assert fetch.await_count == 2
    await run_tool(tool)
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_fallback_profile_result_is_cached():
    primary = AsyncMock(get_company_profile=AsyncMock(return_value=None))
    fallback = AsyncMock(get_company_profile=AsyncMock(return_value=make_profile()))
    tool = CompanyProfileTool(primary, fallback)
    assert await run_tool(tool) == await run_tool(tool)
    primary.get_company_profile.assert_awaited_once()
    fallback.get_company_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_peer_enrichment_is_cached_without_losing_peer():
    tool, fetch, enrichment = make_tool("peers")
    enrichment.run.return_value = None
    first = await run_tool(tool)
    second = await run_tool(tool)
    assert first == second
    assert [peer.ticker for peer in second.peers] == ["V"]
    assert second.peers[0].profile is None
    fetch.assert_awaited_once()
    enrichment.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_fundamentals_cache_respects_profile_source():
    tool, fetch, _ = make_tool("fundamentals")
    await run_tool(tool, make_profile().model_copy(update={"provider": "yfinance"}))
    await run_tool(tool, make_profile().model_copy(update={"provider": "fmp"}))
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_tools_can_share_an_injected_cache_without_key_collisions():
    cache = InMemoryTTLCache(ttl=timedelta(hours=5))
    tools = [make_tool(kind, cache) for kind in ("profile", "peers", "fundamentals")]
    for tool, _, _ in tools:
        await run_tool(tool)
    for tool, fetch, _ in tools:
        await run_tool(tool)
        fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_injected_cache_controls_ttl():
    clock = Clock()
    cache = InMemoryTTLCache(ttl=timedelta(seconds=1), now=clock)
    tool, fetch, _ = make_tool("profile", cache)
    await run_tool(tool)
    clock.now += timedelta(seconds=1)
    await run_tool(tool)
    assert fetch.await_count == 2


def test_cache_expiry_removes_entry_and_new_value_gets_full_ttl():
    clock = Clock()
    cache = InMemoryTTLCache(now=clock)
    assert cache.get("missing") is None
    cache.set("profile:ma", "old")
    assert cache.get("PROFILE:MA") == "old"
    clock.now += timedelta(hours=5)
    assert cache.get("profile:ma") is None
    assert cache.get("profile:ma") is None
    cache.set("profile:ma", "new")
    clock.now += timedelta(hours=4)
    assert cache.get("profile:ma") == "new"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "fundamentals"])
async def test_yfinance_tool_expiry_refetches_vendor_data(kind):
    clock = Clock()
    cache = InMemoryTTLCache(now=clock)
    info = {"longName": "Original name", "totalRevenue": 100.0}
    ticker_factory = MagicMock(side_effect=lambda asset: MagicMock(info=info.copy()))
    provider = YFinanceCompanyProfileProvider(ticker_factory=ticker_factory)
    tool = (
        CompanyProfileTool(provider, None, cache=cache)
        if kind == "profile"
        else CompanyFundamentalsTool(provider, cache=cache)
    )
    profile = make_profile().model_copy(update={"provider": "yfinance"})

    first = await run_tool(tool, profile)
    info.update(longName="Updated name", totalRevenue=200.0)
    clock.now += timedelta(hours=5) - timedelta(seconds=1)
    assert await run_tool(tool, profile) == first
    ticker_factory.assert_called_once_with("MA")

    clock.now += timedelta(seconds=1)
    refreshed = await run_tool(tool, profile)
    assert ticker_factory.call_count == 2
    if kind == "profile":
        assert refreshed.name == "Updated name"
    else:
        assert refreshed.revenue == 200.0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["profile", "peers"])
async def test_fmp_tool_expiry_refetches_vendor_data(kind):
    clock = Clock()
    cache = InMemoryTTLCache(now=clock)
    requests = []
    rows = [{"companyName": "Original name", "symbol": "V"}]

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=rows)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = FmpProvider(enabled=True, api_key="test-key", client=client)
        primary = AsyncMock(get_company_profile=AsyncMock(return_value=None))
        enrichment = AsyncMock(run=AsyncMock(return_value=None))
        tool = (
            CompanyProfileTool(primary, provider, cache=cache)
            if kind == "profile"
            else CompanyPeersTool(provider, enrichment, cache=cache)
        )
        first = await run_tool(tool)
        rows[0]["companyName"] = "Updated name"
        clock.now += timedelta(hours=5) - timedelta(seconds=1)
        assert await run_tool(tool) == first
        assert len(requests) == 1

        clock.now += timedelta(seconds=1)
        refreshed = await run_tool(tool)
        assert len(requests) == 2
        if kind == "profile":
            assert refreshed.name == "Updated name"
            assert primary.get_company_profile.await_count == 2
        else:
            assert refreshed.peers[0].name == "Updated name"
            assert enrichment.run.await_count == 2
