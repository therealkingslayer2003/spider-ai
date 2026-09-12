import asyncio
import logging
from datetime import UTC, datetime

from app.agents.asset_snapshot.tools.cache import InMemoryTTLCache
from app.agents.asset_snapshot.tools.company_profile import CompanyProfileTool
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.market_data.providers import CompanyPeersProvider

logger = logging.getLogger(__name__)


class CompanyPeersTool:
    def __init__(
        self,
        provider: CompanyPeersProvider | None,
        profile_tool: CompanyProfileTool,
        *,
        max_profiles: int = 10,
        concurrency: int = 3,
        profile_timeout_seconds: float = 15.0,
        cache: InMemoryTTLCache | None = None,
    ) -> None:
        if max_profiles < 1 or concurrency < 1 or profile_timeout_seconds <= 0:
            raise ValueError("Peer enrichment limits must be positive")
        self._provider = provider
        self._profile_tool = profile_tool
        self._max_profiles = max_profiles
        self._concurrency = concurrency
        self._profile_timeout_seconds = profile_timeout_seconds
        self._cache = cache if cache is not None else InMemoryTTLCache()

    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyPeersContext:
        asset = (
            asset_profile_context.asset.strip().upper() if asset_profile_context else ""
        )

        if self._provider is None or asset_profile_context is None:
            return self._empty_context(asset)

        cache_key = f"company_peers:{asset_profile_context.asset_type.value}:{asset}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, CompanyPeersContext):
            logger.info("company_peers.cache_hit asset=%s", asset)
            return cached.model_copy(deep=True)

        try:
            context = await self._provider.get_company_peers(
                asset_profile=asset_profile_context,
            )
        except Exception:
            logger.warning("company_peers.fetch.failed asset=%s", asset, exc_info=True)
            return self._empty_context(asset)

        context = context.model_copy(deep=True)
        symbols = list(
            dict.fromkeys(
                peer.ticker.strip().upper()
                for peer in context.peers
                if peer.ticker
                and peer.ticker.strip()
                and peer.ticker.strip().upper() != asset
            )
        )[: self._max_profiles]
        semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch_profile(symbol: str) -> AssetProfileContext | None:
            async with semaphore:
                try:
                    profile = await asyncio.wait_for(
                        self._profile_tool.run(
                            asset=symbol, asset_type=AssetType.STOCK
                        ),
                        timeout=self._profile_timeout_seconds,
                    )
                    if profile is not None and (
                        profile.asset.upper() != symbol
                        or profile.asset_type is not AssetType.STOCK
                    ):
                        logger.warning(
                            "company_peers.profile.mismatch asset=%s peer=%s",
                            asset,
                            symbol,
                        )
                        return None
                    logger.info(
                        "company_peers.profile.result asset=%s peer=%s "
                        "found=%s provider=%s",
                        asset,
                        symbol,
                        profile is not None,
                        profile.provider if profile else None,
                    )
                    return profile
                except Exception:
                    logger.warning(
                        "company_peers.profile.failed asset=%s peer=%s",
                        asset,
                        symbol,
                        exc_info=True,
                    )
                    return None

        profiles = dict(
            zip(
                symbols,
                await asyncio.gather(*(fetch_profile(s) for s in symbols)),
                strict=True,
            )
        )
        for peer in context.peers:
            symbol = peer.ticker.strip().upper() if peer.ticker else ""
            profile = profiles.get(symbol)
            peer.profile = profile.model_copy(deep=True) if profile else None
            if peer.name is None and peer.profile is not None:
                peer.name = peer.profile.name
        logger.info(
            "company_peers.enrichment.end asset=%s candidates=%s "
            "attempted=%s enriched=%s",
            asset,
            len(context.peers),
            len(symbols),
            sum(profile is not None for profile in profiles.values()),
        )
        if context.peers:
            self._cache.set(cache_key, context.model_copy(deep=True))
        return context

    @staticmethod
    def _empty_context(asset: str) -> CompanyPeersContext:
        return CompanyPeersContext(
            asset=asset,
            provider="unavailable",
            peers=[],
            fetched_at=datetime.now(UTC),
        )
