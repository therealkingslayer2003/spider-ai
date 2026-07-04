from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter

from app.api.dependencies import get_asset_snapshot_service
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetSnapshotRequest
from app.services.asset_snapshot_service import AssetSnapshotService

router = APIRouter()


@router.post("/snapshot")
async def get_asset_snapshot(
    request: AssetSnapshotRequest,
    service: AssetSnapshotService = Depends(get_asset_snapshot_service),
) -> AssetSnapshot:
    try:
        return await service.get_snapshot(request)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
