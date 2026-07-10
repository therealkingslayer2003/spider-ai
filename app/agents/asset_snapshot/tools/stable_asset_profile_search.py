from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.providers import MarketDataProvider
from app.market_data.yfinance_provider import YFinanceMarketDataProvider


class StableAssetProfileSearchTool:
    def __init__(
        self,
        market_data_provider: MarketDataProvider | None = None,
    ) -> None:
        self._market_data_provider = (
            market_data_provider or YFinanceMarketDataProvider()
        )

    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        return await self._market_data_provider.get_asset_profile(
            asset=asset,
            asset_type=asset_type,
        )
