from typing import Protocol

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType


class AssetSnapshotTool(Protocol):
    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        ...