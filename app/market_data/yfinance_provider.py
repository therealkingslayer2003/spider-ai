import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any

import yfinance  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.market_data.cache import (
    AssetProfileCache,
    InMemoryTTLAssetProfileCache,
    InMemoryTTLCache,
)
from app.market_data.providers import MarketDataProviderError

logger = logging.getLogger(__name__)


class YFinanceCompanyProfileProvider:
    _SUPPORTED_TYPES = {AssetType.STOCK, AssetType.ETF}

    def __init__(
        self,
        cache: AssetProfileCache | None = None,
        fundamentals_cache: InMemoryTTLCache | None = None,
        ticker_factory: Callable[[str], Any] = yfinance.Ticker,
    ) -> None:
        self._cache = cache or InMemoryTTLAssetProfileCache()
        self._fundamentals_cache = fundamentals_cache or InMemoryTTLCache()
        self._ticker_factory = ticker_factory

    async def get_company_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        settings = get_settings()

        if asset_type not in self._SUPPORTED_TYPES:
            if settings.app_log_flow_steps:
                logger.info(
                    "yfinance_provider.unsupported_asset_type asset=%s asset_type=%s",
                    asset,
                    asset_type.value,
                )
            return None

        normalized_asset = asset.upper()
        cached = self._cache.get(normalized_asset, asset_type)

        if cached is not None:
            if settings.app_log_flow_steps:
                logger.info(
                    "yfinance_provider.cache_hit asset=%s asset_type=%s",
                    normalized_asset,
                    asset_type.value,
                )
            return cached

        try:
            if settings.app_log_flow_steps:
                logger.info(
                    "yfinance_provider.fetch.start asset=%s asset_type=%s",
                    normalized_asset,
                    asset_type.value,
                )
            info = await asyncio.to_thread(self._fetch_info, normalized_asset)
        except Exception as exc:
            logger.exception(
                "yfinance_provider.fetch.failed asset=%s", normalized_asset
            )
            raise MarketDataProviderError(
                "Failed to fetch asset profile from yfinance"
            ) from exc

        profile = self._normalize_info(normalized_asset, asset_type, info)

        if profile is not None:
            self._cache.set(profile)
            self._fundamentals_cache.set(
                self._fundamentals_cache_key(normalized_asset),
                self._normalize_fundamentals(normalized_asset, info),
            )
            if settings.app_log_flow_steps:
                logger.info(
                    "yfinance_provider.fetch.success asset=%s provider=%s",
                    normalized_asset,
                    profile.provider,
                )
        else:
            if settings.app_log_flow_steps:
                logger.info(
                    "yfinance_provider.fetch.no_useful_data asset=%s",
                    normalized_asset,
                )

        return profile

    async def get_fundamentals(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyFundamentalsContext:
        if asset_profile is None:
            return self._empty_fundamentals("")

        asset = asset_profile.asset.upper()
        if (
            not asset
            or asset_profile.asset_type is not AssetType.STOCK
            or asset_profile.provider != "yfinance"
        ):
            return self._empty_fundamentals(asset)

        cache_key = self._fundamentals_cache_key(asset)
        cached = self._fundamentals_cache.get(cache_key)
        if isinstance(cached, CompanyFundamentalsContext):
            return cached

        try:
            info = await asyncio.to_thread(self._fetch_info, asset)
        except Exception:
            logger.exception("yfinance_provider.fundamentals.failed asset=%s", asset)
            return self._empty_fundamentals(asset)

        context = self._normalize_fundamentals(asset, info)
        self._fundamentals_cache.set(cache_key, context)
        return context

    async def get_asset_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        return await self.get_company_profile(asset=asset, asset_type=asset_type)

    def _fetch_info(self, asset: str) -> Mapping[str, Any]:
        info = self._ticker_factory(asset).info
        return info if isinstance(info, Mapping) else {}

    def _normalize_info(
        self,
        asset: str,
        asset_type: AssetType,
        info: Mapping[str, Any],
    ) -> AssetProfileContext | None:
        useful_fields = {
            "longName",
            "shortName",
            "sector",
            "industry",
            "longBusinessSummary",
            "country",
        }

        if not any(self._clean_string(info.get(field)) for field in useful_fields):
            return None

        return AssetProfileContext(
            asset=asset,
            asset_type=asset_type,
            name=self._first_string(info, "longName", "shortName"),
            sector=self._clean_string(info.get("sector")),
            industry=self._clean_string(info.get("industry")),
            business_summary=self._clean_string(info.get("longBusinessSummary")),
            exchange=self._first_string(info, "exchange", "fullExchangeName"),
            currency=self._clean_string(info.get("currency")),
            country=self._clean_string(info.get("country")),
            website=self._clean_string(info.get("website")),
            provider="yfinance",
            fetched_at=datetime.now(UTC),
        )

    def _normalize_fundamentals(
        self,
        asset: str,
        info: Mapping[str, Any],
    ) -> CompanyFundamentalsContext:
        return CompanyFundamentalsContext(
            asset=asset,
            provider="yfinance",
            revenue=self._number(info.get("totalRevenue")),
            revenue_growth=self._number(info.get("revenueGrowth")),
            operating_margin=self._number(info.get("operatingMargins")),
            debt_to_equity=self._number(info.get("debtToEquity")),
            financial_currency=self._clean_string(info.get("financialCurrency")),
            last_fiscal_year_end=self._unix_date(info.get("lastFiscalYearEnd")),
            most_recent_quarter=self._unix_date(info.get("mostRecentQuarter")),
            fetched_at=datetime.now(UTC),
        )

    @staticmethod
    def _empty_fundamentals(asset: str) -> CompanyFundamentalsContext:
        return CompanyFundamentalsContext(asset=asset, provider="yfinance_unavailable")

    @staticmethod
    def _fundamentals_cache_key(asset: str) -> str:
        return f"yfinance:fundamentals:{asset}"

    def _first_string(self, info: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = self._clean_string(info.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unix_date(value: Any) -> date | None:
        if isinstance(value, bool) or value is None:
            return None

        try:
            timestamp = float(value)
            if timestamp <= 0:
                return None
            return datetime.fromtimestamp(timestamp, tz=UTC).date()
        except (OSError, OverflowError, TypeError, ValueError):
            return None
