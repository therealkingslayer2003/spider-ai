from typing import TypedDict

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)
from app.domain.schemas.asset_snapshot_evidence import AssetSnapshotEvidence


class AssetSnapshotRouterState(TypedDict, total=False):
    request: AssetSnapshotRequest
    selected_asset_type: AssetType
    validated_output: StockAssetSnapshot | None
    evidence: AssetSnapshotEvidence | None
    error: str | None
