from typing import Protocol

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_peer_context import CompanyPeerContext
from app.domain.schemas.sector_context import SectorContext


class AssetSnapshotTool(Protocol):
    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None: ...


class CompanyPeersToolProtocol(Protocol):
    async def run(
        self,
        asset: str,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyPeerContext: ...


class SectorContextToolProtocol(Protocol):
    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> SectorContext: ...
