from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.providers import CompanyProfileProvider


class CompanyProfileTool:
    def __init__(
        self,
        primary_provider: CompanyProfileProvider,
        fallback_provider: CompanyProfileProvider | None,
    ) -> None:
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider

    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        profile = await self._try_provider(
            provider=self._primary_provider,
            asset=asset,
            asset_type=asset_type,
        )
        if profile is not None:
            return profile

        if self._fallback_provider is None:
            return None

        return await self._try_provider(
            provider=self._fallback_provider,
            asset=asset,
            asset_type=asset_type,
        )

    @staticmethod
    async def _try_provider(
        provider: CompanyProfileProvider,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        try:
            return await provider.get_company_profile(
                asset=asset,
                asset_type=asset_type,
            )
        except Exception:
            return None
