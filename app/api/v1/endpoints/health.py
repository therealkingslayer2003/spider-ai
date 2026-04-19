from fastapi import APIRouter

from app.core.config import get_settings
from app.domain.schemas.health import HealthResponse


router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
    )
