from typing import TypedDict

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)


class AssetSnapshotRouterState(TypedDict, total=False):
    request: AssetSnapshotRequest
    selected_asset_type: AssetType
    validated_output: StockAssetSnapshot | None
    error: str | None
