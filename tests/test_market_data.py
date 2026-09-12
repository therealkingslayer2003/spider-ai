from datetime import date
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from app.agents.asset_snapshot.tools import CompanyProfileTool
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider


def raw_yfinance_info() -> dict[str, Any]:
    return {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "longBusinessSummary": "Apple designs consumer electronics and services.",
        "exchange": "NMS",
        "currency": "USD",
        "country": "United States",
        "website": "https://www.apple.com",
        "operatingMargins": 0.31,
        "debtToEquity": 209.0,
        "totalRevenue": 390_000_000_000,
        "revenueGrowth": 0.05,
        "financialCurrency": "USD",
        "lastFiscalYearEnd": 1_735_603_200,
        "mostRecentQuarter": 1_751_241_600,
    }


def ticker_factory(info: dict[str, Any], calls: list[str]):
    class FakeTicker:
        def __init__(self, asset: str) -> None:
            calls.append(asset)
            self.info = info

    return FakeTicker


def make_asset_profile(asset: str = "AAPL") -> AssetProfileContext:
    return AssetProfileContext(
        asset=asset,
        asset_type=AssetType.STOCK,
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        business_summary="Apple designs consumer electronics and services.",
        exchange="NASDAQ",
        currency="USD",
        country="US",
        provider="test",
    )


@pytest.mark.asyncio
async def test_yfinance_provider_maps_raw_data_to_asset_profile_context() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(raw_yfinance_info(), calls),
    )

    profile = await provider.get_company_profile("aapl", AssetType.STOCK)

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
async def test_yfinance_provider_requires_useful_company_profile_data() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(
            {"exchange": "NMS", "currency": "USD"},
            calls,
        ),
    )

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)

    assert profile is None
    assert calls == ["AAPL"]


@pytest.mark.asyncio
async def test_yfinance_provider_fetches_fresh_data_on_every_call() -> None:
    calls: list[str] = []
    info = raw_yfinance_info()
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(info, calls),
    )

    first = await provider.get_company_profile("AAPL", AssetType.STOCK)
    info["longName"] = "Updated company name"
    second = await provider.get_company_profile("AAPL", AssetType.STOCK)

    assert first is not None and first.name == "Apple Inc."
    assert second is not None and second.name == "Updated company name"
    assert calls == ["AAPL", "AAPL"]


@pytest.mark.asyncio
async def test_yfinance_provider_normalizes_optional_financial_signals() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(raw_yfinance_info(), calls),
    )

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)
    fundamentals = await provider.get_fundamentals(profile)

    assert fundamentals.provider == "yfinance"
    assert fundamentals.revenue == 390_000_000_000.0
    assert fundamentals.revenue_growth == 0.05
    assert fundamentals.operating_margin == 0.31
    assert fundamentals.debt_to_equity_ratio == 2.09
    assert fundamentals.financial_currency == "USD"
    assert fundamentals.last_fiscal_year_end == date(2024, 12, 31)
    assert fundamentals.most_recent_quarter == date(2025, 6, 30)
    serialized = fundamentals.model_dump()
    assert "debt_to_equity" not in serialized
    assert "debtToEquity" not in serialized
    assert "market_cap" not in serialized
    assert "marketCap" not in serialized
    assert calls == ["AAPL", "AAPL"]


@pytest.mark.asyncio
async def test_yfinance_provider_keeps_missing_optional_signals_none() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(
            {
                "longName": "Apple Inc.",
                "longBusinessSummary": "Makes devices and services.",
            },
            calls,
        ),
    )

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)
    fundamentals = await provider.get_fundamentals(profile)

    assert fundamentals.revenue is None
    assert fundamentals.revenue_growth is None
    assert fundamentals.operating_margin is None
    assert fundamentals.debt_to_equity_ratio is None
    assert fundamentals.financial_currency is None
    assert fundamentals.last_fiscal_year_end is None
    assert fundamentals.most_recent_quarter is None


@pytest.mark.parametrize(
    ("raw_value", "expected_ratio"),
    [
        (0, 0.0),
        (None, None),
        ("not-a-number", None),
        (True, None),
    ],
)
@pytest.mark.asyncio
async def test_yfinance_provider_normalizes_debt_to_equity_ratio_edge_cases(
    raw_value: object,
    expected_ratio: float | None,
) -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(
            {
                "longName": "Apple Inc.",
                "debtToEquity": raw_value,
            },
            calls,
        ),
    )

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)
    fundamentals = await provider.get_fundamentals(profile)

    assert fundamentals.debt_to_equity_ratio == expected_ratio


@pytest.mark.asyncio
async def test_yfinance_provider_handles_malformed_financial_metadata() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(
            {
                "longName": "Apple Inc.",
                "currency": "USD",
                "financialCurrency": 123,
                "lastFiscalYearEnd": "not-a-timestamp",
                "mostRecentQuarter": -1,
            },
            calls,
        ),
    )

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)
    fundamentals = await provider.get_fundamentals(profile)

    assert fundamentals.financial_currency is None
    assert fundamentals.last_fiscal_year_end is None
    assert fundamentals.most_recent_quarter is None
    assert calls == ["AAPL", "AAPL"]


@pytest.mark.asyncio
async def test_yfinance_provider_does_not_refetch_for_fmp_profile() -> None:
    calls: list[str] = []
    provider = YFinanceCompanyProfileProvider(
        ticker_factory=ticker_factory(raw_yfinance_info(), calls),
    )
    profile = make_asset_profile()
    profile.provider = "fmp"

    fundamentals = await provider.get_fundamentals(profile)

    assert fundamentals.provider == "yfinance_unavailable"
    assert fundamentals.revenue is None
    assert fundamentals.financial_currency is None
    assert calls == []


@pytest.mark.asyncio
async def test_company_profile_tool_returns_yfinance_profile_when_available() -> None:
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
    primary = AsyncMock()
    fallback = AsyncMock()
    primary.get_company_profile.return_value = profile
    tool = CompanyProfileTool(primary_provider=primary, fallback_provider=fallback)

    result = await tool.run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result == profile
    primary.get_company_profile.assert_awaited_once_with(
        asset="AAPL",
        asset_type=AssetType.STOCK,
    )
    fallback.get_company_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_profile_tool_falls_back_to_fmp_profile() -> None:
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
        provider="fmp",
    )
    primary = AsyncMock()
    fallback = AsyncMock()
    primary.get_company_profile.return_value = None
    fallback.get_company_profile.return_value = profile

    result = await CompanyProfileTool(
        primary_provider=primary,
        fallback_provider=fallback,
    ).run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result == profile


@pytest.mark.asyncio
async def test_company_profile_tool_returns_none_without_configured_fallback() -> None:
    primary = AsyncMock()
    primary.get_company_profile.return_value = None

    result = await CompanyProfileTool(
        primary_provider=primary,
        fallback_provider=None,
    ).run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result is None
    primary.get_company_profile.assert_awaited_once_with(
        asset="AAPL",
        asset_type=AssetType.STOCK,
    )


@pytest.mark.asyncio
async def test_company_profile_tool_returns_none_when_both_unavailable() -> None:
    primary = AsyncMock()
    fallback = AsyncMock()
    primary.get_company_profile.side_effect = RuntimeError("yf failed")
    fallback.get_company_profile.return_value = None

    result = await CompanyProfileTool(
        primary_provider=primary,
        fallback_provider=fallback,
    ).run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result is None


class FakeResponse:
    def __init__(self, data, status_code: int = 200) -> None:  # noqa: ANN001
        self._data = data
        self.status_code = status_code
        self.text = str(data)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):  # noqa: ANN201
        return self._data


class FakeAsyncClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    async def get(
        self,
        url: str,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        request_url = f"{url}?{urlencode(params)}"
        self.urls.append(request_url)
        for key, response in self.responses.items():
            if key in request_url:
                return response
        return FakeResponse([], status_code=404)


@pytest.mark.asyncio
async def test_fmp_missing_api_key_disables_gracefully() -> None:
    provider = FmpProvider(enabled=True, api_key="")
    profile = make_asset_profile()

    assert await provider.get_company_profile("AAPL", AssetType.STOCK) is None
    peers = await provider.get_company_peers(asset_profile=profile)
    fundamentals = await provider.get_fundamentals(asset_profile=profile)
    assert peers.peers == []
    assert peers.asset == "AAPL"
    assert fundamentals.revenue is None
    assert fundamentals.asset == "AAPL"


@pytest.mark.asyncio
async def test_fmp_peers_and_fundamentals_without_profile_do_not_call_api() -> None:
    client = FakeAsyncClient({})
    provider = FmpProvider(enabled=True, api_key="key", client=client)

    peers = await provider.get_company_peers()
    fundamentals = await provider.get_fundamentals()

    assert peers.asset == ""
    assert peers.peers == []
    assert fundamentals.asset == ""
    assert fundamentals.revenue is None
    assert client.urls == []


@pytest.mark.asyncio
async def test_fmp_profile_response_maps_to_asset_profile_context() -> None:
    client = FakeAsyncClient(
        {
            "/profile?symbol=AAPL": FakeResponse(
                [
                    {
                        "companyName": "Apple Inc.",
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                        "description": "Designs devices and services.",
                        "exchangeShortName": "NASDAQ",
                        "currency": "USD",
                        "country": "US",
                        "website": "https://apple.com",
                    }
                ]
            )
        }
    )
    provider = FmpProvider(enabled=True, api_key="key", client=client)

    profile = await provider.get_company_profile("AAPL", AssetType.STOCK)

    assert profile is not None
    assert profile.name == "Apple Inc."
    assert profile.provider == "fmp"


@pytest.mark.asyncio
async def test_fmp_peers_response_maps_to_company_peers_context() -> None:
    client = FakeAsyncClient(
        {"/stock-peers?symbol=AAPL": FakeResponse([{"peersList": ["MSFT"]}])}
    )
    provider = FmpProvider(enabled=True, api_key="key", client=client)
    profile = make_asset_profile()

    context = await provider.get_company_peers(asset_profile=profile)

    assert context.provider == "fmp"
    assert context.peers[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_fmp_fundamentals_returns_empty_without_api_calls() -> None:
    client = FakeAsyncClient({})
    provider = FmpProvider(enabled=True, api_key="key", client=client)
    profile = make_asset_profile()

    context = await provider.get_fundamentals(asset_profile=profile)

    assert context.asset == "AAPL"
    assert context.revenue is None
    assert context.revenue_growth is None
    assert context.operating_margin is None
    assert context.debt_to_equity_ratio is None
    assert context.financial_currency is None
    assert context.last_fiscal_year_end is None
    assert context.most_recent_quarter is None
    assert client.urls == []


@pytest.mark.asyncio
async def test_fmp_http_errors_are_controlled() -> None:
    client = FakeAsyncClient(
        {"/profile?symbol=AAPL": FakeResponse([], status_code=429)}
    )
    provider = FmpProvider(enabled=True, api_key="key", client=client)

    assert await provider.get_company_profile("AAPL", AssetType.STOCK) is None


@pytest.mark.asyncio
async def test_fmp_403_disables_provider_for_follow_up_calls() -> None:
    client = FakeAsyncClient(
        {
            "/profile?symbol=AAPL": FakeResponse(
                {"error": "Invalid API Key"},
                status_code=403,
            ),
        }
    )
    provider = FmpProvider(enabled=True, api_key="key", client=client)
    profile = make_asset_profile()

    assert await provider.get_company_profile("AAPL", AssetType.STOCK) is None
    peers = await provider.get_company_peers(asset_profile=profile)
    fundamentals = await provider.get_fundamentals(asset_profile=profile)

    assert fundamentals.provider == "fmp_unavailable"
    assert fundamentals.revenue is None
    assert peers.provider == "fmp_unavailable"
    assert peers.peers == []
    assert client.urls == [
        "https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=key"
    ]
