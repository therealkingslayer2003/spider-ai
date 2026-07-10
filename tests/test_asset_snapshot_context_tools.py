import pytest

from app.agents.asset_snapshot.tools import CompanyPeersTool, SectorContextTool
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType


def make_profile(
    asset: str = "MA",
    sector: str | None = "Financial Services",
    industry: str | None = "Credit Services",
    business_summary: str | None = "Global payment network and transaction processor.",
) -> AssetProfileContext:
    return AssetProfileContext(
        asset=asset,
        asset_type=AssetType.STOCK,
        name="Test Company",
        sector=sector,
        industry=industry,
        business_summary=business_summary,
        exchange="NYSE",
        currency="USD",
        country="USA",
        provider="test",
    )


@pytest.mark.asyncio
async def test_company_peers_tool_returns_mastercard_peers() -> None:
    context = await CompanyPeersTool().run(
        asset="MA",
        asset_profile_context=make_profile(),
    )
    tickers = {peer.ticker for peer in context.peers}
    names = {peer.name for peer in context.peers}

    assert {"V", "AXP", "PYPL", "SQ", "ADYEN.AS"}.issubset(tickers)
    assert "Visa" in names
    assert context.confidence == "high"


@pytest.mark.asyncio
async def test_company_peers_tool_returns_google_peers() -> None:
    context = await CompanyPeersTool().run(
        asset="GOOGL",
        asset_profile_context=make_profile(asset="GOOGL"),
    )
    tickers = {peer.ticker for peer in context.peers}
    names = {peer.name for peer in context.peers}

    assert {"MSFT", "META", "AMZN", "AAPL"}.issubset(tickers)
    assert "TikTok / ByteDance" in names


@pytest.mark.asyncio
async def test_company_peers_tool_unknown_ticker_returns_empty_peers() -> None:
    context = await CompanyPeersTool().run(
        asset="UNKNOWN",
        asset_profile_context=None,
    )

    assert context.peers == []
    assert context.confidence == "low"


@pytest.mark.asyncio
async def test_sector_context_tool_returns_payments_context() -> None:
    context = await SectorContextTool().run(
        asset_profile_context=make_profile(
            industry="Transaction & Payment Processing Services",
            business_summary="Provides card payment network processing.",
        )
    )

    assert "Payment" in context.industry
    assert any(
        "interchange" in risk.explanation.lower() for risk in context.common_risks
    )


@pytest.mark.asyncio
async def test_sector_context_tool_returns_digital_advertising_context() -> None:
    context = await SectorContextTool().run(
        asset_profile_context=make_profile(
            sector="Communication Services",
            industry="Internet Content & Information",
            business_summary="Search advertising and YouTube video advertising.",
        )
    )

    assert "Digital Advertising" in context.industry
    assert any("AI search" in risk.title for risk in context.common_risks)


@pytest.mark.asyncio
async def test_sector_context_tool_returns_semiconductor_context() -> None:
    context = await SectorContextTool().run(
        asset_profile_context=make_profile(
            sector="Technology",
            industry="Semiconductors",
            business_summary="Designs GPUs and AI accelerators.",
        )
    )

    assert "Semiconductors" in context.industry
    assert any("AI accelerator" in driver.title for driver in context.common_drivers)


@pytest.mark.asyncio
async def test_sector_context_tool_unknown_industry_returns_generic_context() -> None:
    context = await SectorContextTool().run(
        asset_profile_context=make_profile(
            sector="Industrials",
            industry="Specialty Business Services",
            business_summary="Provides services to businesses.",
        )
    )

    assert context.business_model_pattern == "Public company business economics."
    assert context.provider == "static_sector_context_v1"
