import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import yfinance

from app.core.config import get_settings
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.cache import AssetProfileCache, InMemoryTTLAssetProfileCache
from app.market_data.providers import MarketDataProviderError

logger = logging.getLogger(__name__)


class YFinanceMarketDataProvider:
    _SUPPORTED_TYPES = {AssetType.STOCK, AssetType.ETF}

    def __init__(
        self,
        cache: AssetProfileCache | None = None,
        ticker_factory: Callable[[str], Any] = yfinance.Ticker,
    ) -> None:
        self._cache = cache or InMemoryTTLAssetProfileCache()
        self._ticker_factory = ticker_factory

    async def get_asset_profile(
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
            "exchange",
            "fullExchangeName",
            "currency",
            "country",
            "website",
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
