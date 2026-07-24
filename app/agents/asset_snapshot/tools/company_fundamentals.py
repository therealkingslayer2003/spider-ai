from datetime import UTC, datetime

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.market_data.providers import FundamentalsProvider


class CompanyFundamentalsTool:
    def __init__(
        self,
        provider: FundamentalsProvider,
    ) -> None:
        self._provider = provider

    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyFundamentalsContext:
        asset = asset_profile_context.asset.upper() if asset_profile_context else ""
        try:
            return await self._provider.get_fundamentals(
                asset_profile=asset_profile_context,
            )
        except Exception:
            return CompanyFundamentalsContext(
                asset=asset.upper(),
                provider="unavailable",
                fetched_at=datetime.now(UTC),
            )
