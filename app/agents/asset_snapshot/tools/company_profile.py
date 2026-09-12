import logging

from app.agents.asset_snapshot.tools.cache import InMemoryTTLCache
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.market_data.providers import CompanyProfileProvider

logger = logging.getLogger(__name__)


class CompanyProfileTool:
    def __init__(
        self,
        primary_provider: CompanyProfileProvider,
        fallback_provider: CompanyProfileProvider | None,
        *,
        cache: InMemoryTTLCache | None = None,
    ) -> None:
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._cache = cache if cache is not None else InMemoryTTLCache()

    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        asset = asset.strip().upper()
        cache_key = f"company_profile:{asset_type.value}:{asset}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, AssetProfileContext):
            logger.info("company_profile.cache_hit asset=%s", asset)
            return cached.model_copy(deep=True)

        profile = await self._try_provider(
            provider=self._primary_provider,
            asset=asset,
            asset_type=asset_type,
        )
        if profile is None and self._fallback_provider is not None:
            profile = await self._try_provider(
                provider=self._fallback_provider,
                asset=asset,
                asset_type=asset_type,
            )
        if profile is not None:
            self._cache.set(cache_key, profile.model_copy(deep=True))
            return profile.model_copy(deep=True)
        return None

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
