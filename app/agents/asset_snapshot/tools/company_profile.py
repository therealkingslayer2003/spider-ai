from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.fmp_provider import FmpProvider
from app.market_data.providers import CompanyProfileProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider


class CompanyProfileTool:
    def __init__(
        self,
        primary_provider: CompanyProfileProvider | None = None,
        fallback_provider: CompanyProfileProvider | None = None,
        market_data_provider: CompanyProfileProvider | None = None,
    ) -> None:
        self._primary_provider = (
            primary_provider or market_data_provider or YFinanceCompanyProfileProvider()
        )
        self._fallback_provider = fallback_provider or FmpProvider()

    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        try:
            profile = await self._get_profile(self._primary_provider, asset, asset_type)
            if profile is not None:
                return profile
        except Exception:
            profile = None

        try:
            return await self._get_profile(self._fallback_provider, asset, asset_type)
        except Exception:
            return None

    @staticmethod
    async def _get_profile(
        provider: CompanyProfileProvider,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        if hasattr(provider, "get_company_profile"):
            return await provider.get_company_profile(
                asset=asset,
                asset_type=asset_type,
            )

        return await provider.get_asset_profile(  # type: ignore[attr-defined]
            asset=asset,
            asset_type=asset_type,
        )
