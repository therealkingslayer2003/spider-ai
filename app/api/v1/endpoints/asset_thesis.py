from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter

from app.api.dependencies import get_asset_thesis_service
from app.core.exceptions import AssetThesisNotImplementedError, ServiceError
from app.domain.schemas.asset_thesis import AssetThesisRequest, StockAssetThesis
from app.services.asset_thesis_service import AssetThesisService

router = APIRouter()


@router.post(
    "/thesis",
    responses={
        501: {"description": "Thesis research execution is not implemented."},
        502: {"description": "Thesis research execution failed."},
    },
)
async def get_asset_thesis(
    request: AssetThesisRequest,
    service: AssetThesisService = Depends(get_asset_thesis_service),
) -> StockAssetThesis:
    try:
        return await service.get_thesis(request)
    except AssetThesisNotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
