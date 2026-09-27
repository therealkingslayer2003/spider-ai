from fastapi import APIRouter

from app.api.v1.endpoints import asset_snapshot, asset_thesis, chat, health

api_v1_router = APIRouter()

api_v1_router.include_router(health.router, prefix="/health", tags=["health"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_v1_router.include_router(
    asset_snapshot.router, prefix="/asset", tags=["asset_snapshot"]
)
api_v1_router.include_router(
    asset_thesis.router, prefix="/asset", tags=["asset_thesis"]
)
