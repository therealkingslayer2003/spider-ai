from datetime import UTC, datetime

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.market_data.providers import CompanyPeersProvider


class CompanyPeersTool:
    def __init__(
        self,
        provider: CompanyPeersProvider | None,
    ) -> None:
        self._provider = provider

    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyPeersContext:
        asset = asset_profile_context.asset.upper() if asset_profile_context else ""

        if self._provider is None:
            return self._empty_context(asset)

        try:
            return await self._provider.get_company_peers(
                asset_profile=asset_profile_context,
            )
        except Exception:
            return self._empty_context(asset)

    @staticmethod
    def _empty_context(asset: str) -> CompanyPeersContext:
        return CompanyPeersContext(
            asset=asset,
            provider="unavailable",
            peers=[],
            fetched_at=datetime.now(UTC),
        )
