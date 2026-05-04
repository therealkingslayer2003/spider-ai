from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.domain.schemas.health import HealthResponse


router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
    )
