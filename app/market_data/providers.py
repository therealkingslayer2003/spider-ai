from typing import Protocol

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType


class MarketDataProvider(Protocol):
    async def get_asset_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None: ...


class MarketDataProviderError(Exception):
    """Raised when a market data provider fails in a controlled way."""
