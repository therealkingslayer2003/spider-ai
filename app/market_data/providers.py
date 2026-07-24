from typing import Protocol

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext


class CompanyProfileProvider(Protocol):
    async def get_company_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None: ...


class CompanyPeersProvider(Protocol):
    async def get_company_peers(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyPeersContext: ...


class FundamentalsProvider(Protocol):
    async def get_fundamentals(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyFundamentalsContext: ...


class MarketDataProviderError(Exception):
    """Raised when a market data provider fails in a controlled way."""
