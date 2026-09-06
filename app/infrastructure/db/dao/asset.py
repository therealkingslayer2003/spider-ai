from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import AssetModel


class AssetDao:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, asset_id: int) -> AssetModel | None:
        return await self._session.get(AssetModel, asset_id)

    async def find(
        self,
        asset_type_id: int,
        name: str,
    ) -> AssetModel | None:
        normalized_name = name.strip().upper()
        result = await self._session.execute(
            select(AssetModel).where(
                AssetModel.asset_type_id == asset_type_id,
                AssetModel.name == normalized_name,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, asset_type_id: int, name: str) -> AssetModel:
        asset = AssetModel(
            asset_type_id=asset_type_id,
            name=name.strip().upper(),
        )
        self._session.add(asset)
        await self._session.flush()
        return asset

    async def get_or_create(self, asset_type_id: int, name: str) -> AssetModel:
        existing = await self.find(asset_type_id, name)
        if existing is not None:
            return existing
        return await self.create(asset_type_id, name)
