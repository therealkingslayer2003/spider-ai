from fastapi import Depends
from fastapi.routing import APIRouter

from app.api.dependencies import get_asset_snapshot_service
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    LongAssetSnapshot,
    ShortAssetSnapshot,
)
from app.services.asset_snapshot_service import AssetSnapshotService

router = APIRouter()


@router.post("/snapshot")
async def get_asset_snapshot(
    request: AssetSnapshotRequest,
    service: AssetSnapshotService = Depends(get_asset_snapshot_service),
) -> ShortAssetSnapshot | LongAssetSnapshot:
    return await service.get_snapshot(
        asset=request.asset,
        asset_type=request.asset_type,
        mode=request.mode,
    )
