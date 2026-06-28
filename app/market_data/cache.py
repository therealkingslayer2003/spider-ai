import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType

logger = logging.getLogger(__name__)


class AssetProfileCache(Protocol):
    def get(self, asset: str, asset_type: AssetType) -> AssetProfileContext | None: ...

    def set(self, profile: AssetProfileContext) -> None: ...


class InMemoryTTLAssetProfileCache:
    def __init__(
        self,
        ttl: timedelta = timedelta(hours=24),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl
        self._now = now or (lambda: datetime.now(UTC))
        self._values: dict[
            tuple[str, AssetType], tuple[AssetProfileContext, datetime]
        ] = {}

    def get(self, asset: str, asset_type: AssetType) -> AssetProfileContext | None:
        key = self._key(asset, asset_type)
        cached = self._values.get(key)

        if cached is None:
            logger.debug(
                "asset_profile_cache.miss asset=%s asset_type=%s",
                key[0],
                asset_type.value,
            )
            return None

        profile, expires_at = cached

        if self._now() >= expires_at:
            del self._values[key]
            logger.debug(
                "asset_profile_cache.expired asset=%s asset_type=%s",
                key[0],
                asset_type.value,
            )
            return None

        logger.debug(
            "asset_profile_cache.hit asset=%s asset_type=%s provider=%s",
            key[0],
            asset_type.value,
            profile.provider,
        )
        return profile

    def set(self, profile: AssetProfileContext) -> None:
        self._values[self._key(profile.asset, profile.asset_type)] = (
            profile,
            self._now() + self._ttl,
        )
        logger.debug(
            "asset_profile_cache.set asset=%s asset_type=%s provider=%s",
            profile.asset,
            profile.asset_type.value,
            profile.provider,
        )

    @staticmethod
    def _key(asset: str, asset_type: AssetType) -> tuple[str, AssetType]:
        return (asset.upper(), asset_type)
