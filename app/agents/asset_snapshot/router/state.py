from typing import TypedDict

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)
from app.domain.schemas.snapshot_evidence import SnapshotEvidence


class AssetSnapshotRouterState(TypedDict, total=False):
    request: AssetSnapshotRequest
    selected_asset_type: AssetType
    validated_output: StockAssetSnapshot | None
    snapshot_evidence: SnapshotEvidence | None
    error: str | None
