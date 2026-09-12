import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.tools import CompanyPeersTool, CompanyProfileTool
from app.api import dependencies
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from tests.test_asset_snapshot_context_tools import make_profile


def peers_provider(*tickers: str | None) -> AsyncMock:
    return AsyncMock(
        get_company_peers=AsyncMock(
            return_value=CompanyPeersContext(
                asset="MA",
                provider="test",
                peers=[CompanyPeer(ticker=t) for t in tickers],
            )
        )
    )


@pytest.mark.asyncio
async def test_enrichment_preserves_provider_candidates_without_mutation() -> None:
    provider = peers_provider("V", " v ", None, "MA")
    original = provider.get_company_peers.return_value.model_copy(deep=True)
    profile = make_profile("V")
    tool = AsyncMock(run=AsyncMock(return_value=profile))

    result = await CompanyPeersTool(provider, tool).run(make_profile())

    assert result.peers[0].profile == profile
    assert result.peers[1].profile == profile
    assert result.peers[0].name == profile.name
    assert result.peers[2].profile is None
    assert result.peers[3].profile is None
    assert len(result.peers) == 4
    tool.run.assert_awaited_once()
    assert provider.get_company_peers.return_value == original
    result.peers[0].name = "Edited"
    assert provider.get_company_peers.return_value == original


@pytest.mark.asyncio
async def test_enrichment_reuses_tool_cache() -> None:
    ticker_factory = MagicMock(
        return_value=MagicMock(
            info={
                "shortName": "Visa",
                "longBusinessSummary": "Operates a payment network.",
            }
        )
    )
    profile_tool = CompanyProfileTool(
        primary_provider=YFinanceCompanyProfileProvider(ticker_factory=ticker_factory),
        fallback_provider=None,
    )
    tool = CompanyPeersTool(peers_provider("V"), profile_tool)

    first = await tool.run(make_profile())
    second = await tool.run(make_profile())

    assert first.peers[0].profile is not None
    assert second == first
    ticker_factory.assert_called_once_with("V")


@pytest.mark.asyncio
async def test_enrichment_uses_profile_tool_fallback() -> None:
    primary = AsyncMock(
        get_company_profile=AsyncMock(side_effect=RuntimeError("offline"))
    )
    fallback = AsyncMock(get_company_profile=AsyncMock(return_value=make_profile("V")))
    result = await CompanyPeersTool(
        peers_provider("V"),
        CompanyProfileTool(primary, fallback),
    ).run(make_profile())

    assert result.peers[0].profile is not None
    primary.get_company_profile.assert_awaited_once()
    fallback.get_company_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_enrichment_preserves_reported_peers() -> None:
    primary = AsyncMock(
        get_company_profile=AsyncMock(side_effect=RuntimeError("offline"))
    )
    fallback = AsyncMock(get_company_profile=AsyncMock(return_value=None))
    provider = peers_provider("V", "AXP")
    tool = CompanyPeersTool(provider, CompanyProfileTool(primary, fallback))

    result = await tool.run(make_profile())

    assert [peer.ticker for peer in result.peers] == ["V", "AXP"]
    assert all(peer.profile is None for peer in result.peers)
    assert result.provider == provider.get_company_peers.return_value.provider
    assert primary.get_company_profile.await_count == 2
    assert fallback.get_company_profile.await_count == 2


@pytest.mark.asyncio
async def test_one_failure_or_mismatch_does_not_discard_other_profiles() -> None:
    async def fetch(asset, asset_type):
        if asset == "FAIL":
            raise RuntimeError("offline")
        if asset == "WRONG":
            return make_profile("OTHER")
        return make_profile(asset)

    result = await CompanyPeersTool(
        peers_provider("FAIL", "V", "WRONG"),
        AsyncMock(run=AsyncMock(side_effect=fetch)),
    ).run(make_profile())

    assert [p.profile is not None for p in result.peers] == [False, True, False]


@pytest.mark.asyncio
async def test_enrichment_timeout_is_controlled() -> None:
    async def blocked(**kwargs):
        await asyncio.Event().wait()

    tool = CompanyPeersTool(
        peers_provider("V"),
        AsyncMock(run=AsyncMock(side_effect=blocked)),
        profile_timeout_seconds=0.01,
    )
    result = await tool.run(make_profile())
    assert len(result.peers) == 1
    assert result.peers[0].profile is None


@pytest.mark.asyncio
async def test_enrichment_caps_requests_and_concurrency() -> None:
    active = 0
    peak = 0

    async def fetch(asset, asset_type):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return make_profile(asset)

    profiles = AsyncMock(run=AsyncMock(side_effect=fetch))
    result = await CompanyPeersTool(
        peers_provider("A", "B", "C", "D"),
        profiles,
        max_profiles=3,
        concurrency=2,
    ).run(make_profile())

    assert profiles.run.await_count == 3
    assert peak == 2
    assert [p.profile is not None for p in result.peers] == [True, True, True, False]


@pytest.mark.asyncio
async def test_no_target_or_no_candidates_skips_profile_calls() -> None:
    provider = peers_provider()
    profiles = AsyncMock()
    tool = CompanyPeersTool(provider, profiles)
    assert (await tool.run(None)).peers == []
    provider.get_company_peers.assert_not_awaited()
    assert (await tool.run(make_profile())).peers == []
    profiles.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_composition_root_injects_shared_profile_tool(monkeypatch) -> None:
    dependencies.get_company_peers_tool.cache_clear()
    provider = peers_provider("V")
    profiles = AsyncMock(run=AsyncMock(return_value=make_profile("V")))
    monkeypatch.setattr(dependencies, "get_optional_fmp_provider", lambda: provider)
    monkeypatch.setattr(dependencies, "get_profile_tool", lambda: profiles)
    tool = dependencies.get_company_peers_tool()
    dependencies.get_company_peers_tool.cache_clear()
    result = await tool.run(make_profile())
    assert result.peers[0].profile is not None
    profiles.run.assert_awaited_once()
