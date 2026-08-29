from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.agents.asset_snapshot.tools import CompanyFundamentalsTool, CompanyPeersTool
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext


def make_profile(asset: str = "MA") -> AssetProfileContext:
    return AssetProfileContext(
        asset=asset,
        asset_type=AssetType.STOCK,
        name="Test Company",
        sector="Financial Services",
        industry="Payments",
        business_summary="Global payment network and transaction processor.",
        exchange="NYSE",
        currency="USD",
        country="USA",
        provider="test",
    )


@pytest.mark.asyncio
async def test_company_peers_tool_returns_provider_peers() -> None:
    provider = AsyncMock()
    context = CompanyPeersContext(
        asset="MA",
        provider="fmp",
        peers=[CompanyPeer(ticker="V", provider="fmp")],
    )
    provider.get_company_peers.return_value = context
    profile = make_profile()

    result = await CompanyPeersTool(provider=provider).run(
        asset_profile_context=profile,
    )

    assert result == context
    provider.get_company_peers.assert_awaited_once_with(
        asset_profile=profile,
    )


@pytest.mark.asyncio
async def test_company_peers_tool_returns_empty_peers_when_provider_fails() -> None:
    provider = AsyncMock()
    provider.get_company_peers.side_effect = RuntimeError("fmp failed")
    profile = make_profile()

    result = await CompanyPeersTool(provider=provider).run(
        asset_profile_context=profile,
    )

    assert result.asset == "MA"
    assert result.peers == []
    assert result.provider == "unavailable"


@pytest.mark.asyncio
async def test_company_peers_tool_returns_empty_peers_without_provider() -> None:
    profile = make_profile()

    result = await CompanyPeersTool(provider=None).run(
        asset_profile_context=profile,
    )

    assert result.asset == "MA"
    assert result.peers == []
    assert result.provider == "unavailable"


@pytest.mark.asyncio
async def test_company_fundamentals_tool_returns_provider_context() -> None:
    provider = AsyncMock()
    context = CompanyFundamentalsContext(
        asset="MA",
        provider="fmp",
        revenue=10.0,
        operating_margin=0.4,
        debt_to_equity_ratio=2.09,
        financial_currency="USD",
        last_fiscal_year_end=date(2025, 12, 31),
    )
    provider.get_fundamentals.return_value = context
    profile = make_profile()

    result = await CompanyFundamentalsTool(provider=provider).run(
        asset_profile_context=profile,
    )

    assert result == context
    assert result.debt_to_equity_ratio == 2.09
    assert result.financial_currency == "USD"
    assert result.last_fiscal_year_end == date(2025, 12, 31)
    provider.get_fundamentals.assert_awaited_once_with(
        asset_profile=profile,
    )


@pytest.mark.asyncio
async def test_company_fundamentals_tool_returns_empty_on_provider_failure() -> None:
    provider = AsyncMock()
    provider.get_fundamentals.side_effect = RuntimeError("fmp failed")
    profile = make_profile()

    result = await CompanyFundamentalsTool(provider=provider).run(
        asset_profile_context=profile,
    )

    assert result.asset == "MA"
    assert result.provider == "unavailable"
    assert result.revenue is None


def test_sector_context_tool_is_not_exported_in_production_tools() -> None:
    import app.agents.asset_snapshot.tools as tools

    assert not hasattr(tools, "SectorContextTool")
