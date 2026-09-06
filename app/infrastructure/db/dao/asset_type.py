from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import AssetTypeModel


class AssetTypeDao:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: str) -> AssetTypeModel | None:
        normalized_name = name.strip().lower()
        result = await self._session.execute(
            select(AssetTypeModel).where(AssetTypeModel.name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        name: str,
        description: str | None = None,
    ) -> AssetTypeModel:
        existing = await self.get_by_name(name)
        if existing is not None:
            return existing

        asset_type = AssetTypeModel(
            name=name.strip().lower(),
            description=description,
        )
        self._session.add(asset_type)
        await self._session.flush()
        return asset_type
