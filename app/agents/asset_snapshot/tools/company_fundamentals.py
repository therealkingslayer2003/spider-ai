import logging
from datetime import UTC, datetime

from app.agents.asset_snapshot.tools.cache import InMemoryTTLCache
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.market_data.providers import FundamentalsProvider

logger = logging.getLogger(__name__)


class CompanyFundamentalsTool:
    def __init__(
        self,
        provider: FundamentalsProvider,
        *,
        cache: InMemoryTTLCache | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache if cache is not None else InMemoryTTLCache()

    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyFundamentalsContext:
        asset = (
            asset_profile_context.asset.strip().upper() if asset_profile_context else ""
        )
        # The provider may vary its behavior based on the source of the profile.
        cache_key = (
            f"company_fundamentals:{asset_profile_context.asset_type.value}:"
            f"{asset}:{asset_profile_context.provider}"
            if asset_profile_context is not None
            else None
        )
        cached = self._cache.get(cache_key) if cache_key else None
        if isinstance(cached, CompanyFundamentalsContext):
            logger.info("company_fundamentals.cache_hit asset=%s", asset)
            return cached.model_copy(deep=True)
        try:
            context = await self._provider.get_fundamentals(
                asset_profile=asset_profile_context,
            )
        except Exception:
            return CompanyFundamentalsContext(
                asset=asset.upper(),
                provider="unavailable",
                fetched_at=datetime.now(UTC),
            )
        if cache_key and any(
            value is not None
            for value in (
                context.revenue,
                context.revenue_growth,
                context.operating_margin,
                context.debt_to_equity_ratio,
            )
        ):
            self._cache.set(cache_key, context.model_copy(deep=True))
        return context.model_copy(deep=True)
