from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.cache import InMemoryTTLAssetProfileCache
from app.market_data.yfinance_provider import YFinanceMarketDataProvider
from app.tools.asset_snapshot.stable_asset_profile_search import (
    StableAssetProfileSearchTool,
)


def raw_yfinance_info() -> dict[str, str]:
    return {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "longBusinessSummary": "Apple designs consumer electronics and services.",
        "exchange": "NMS",
        "currency": "USD",
        "country": "United States",
        "website": "https://www.apple.com",
    }


def ticker_factory(info: dict[str, str], calls: list[str]):
    class FakeTicker:
        def __init__(self, asset: str) -> None:
            calls.append(asset)
            self.info = info

    return FakeTicker


@pytest.mark.asyncio
async def test_yfinance_provider_maps_raw_data_to_asset_profile_context() -> None:
    calls: list[str] = []
    provider = YFinanceMarketDataProvider(
        ticker_factory=ticker_factory(raw_yfinance_info(), calls),
    )

    profile = await provider.get_asset_profile("aapl", AssetType.STOCK)

    assert isinstance(profile, AssetProfileContext)
    assert profile.asset == "AAPL"
    assert profile.asset_type == AssetType.STOCK
    assert profile.name == "Apple Inc."
    assert profile.sector == "Technology"
    assert profile.industry == "Consumer Electronics"
    assert (
        profile.business_summary == "Apple designs consumer electronics and services."
    )
    assert profile.exchange == "NMS"
    assert profile.currency == "USD"
    assert profile.country == "United States"
    assert profile.website == "https://www.apple.com"
    assert profile.provider == "yfinance"


@pytest.mark.asyncio
async def test_yfinance_provider_uses_cache_on_second_call() -> None:
    calls: list[str] = []
    provider = YFinanceMarketDataProvider(
        cache=InMemoryTTLAssetProfileCache(),
        ticker_factory=ticker_factory(raw_yfinance_info(), calls),
    )

    first = await provider.get_asset_profile("AAPL", AssetType.STOCK)
    second = await provider.get_asset_profile("AAPL", AssetType.STOCK)

    assert first == second
    assert calls == ["AAPL"]


@pytest.mark.asyncio
async def test_asset_profile_cache_expires_after_ttl() -> None:
    current_time = datetime(2026, 1, 1, tzinfo=UTC)

    def now() -> datetime:
        return current_time

    cache = InMemoryTTLAssetProfileCache(ttl=timedelta(seconds=1), now=now)
    profile = AssetProfileContext(
        asset="AAPL",
        asset_type=AssetType.STOCK,
        name="Apple Inc.",
        sector=None,
        industry=None,
        business_summary=None,
        exchange=None,
        currency=None,
        country=None,
        provider="test",
    )

    cache.set(profile)
    assert cache.get("AAPL", AssetType.STOCK) == profile

    current_time = current_time + timedelta(seconds=2)

    assert cache.get("AAPL", AssetType.STOCK) is None


@pytest.mark.asyncio
async def test_stable_asset_profile_search_tool_returns_provider_result() -> None:
    profile = AssetProfileContext(
        asset="AAPL",
        asset_type=AssetType.STOCK,
        name="Apple Inc.",
        sector=None,
        industry=None,
        business_summary=None,
        exchange=None,
        currency=None,
        country=None,
        provider="test",
    )
    provider = AsyncMock()
    provider.get_asset_profile.return_value = profile
    tool = StableAssetProfileSearchTool(market_data_provider=provider)

    result = await tool.run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result == profile
    provider.get_asset_profile.assert_awaited_once_with(
        asset="AAPL",
        asset_type=AssetType.STOCK,
    )
