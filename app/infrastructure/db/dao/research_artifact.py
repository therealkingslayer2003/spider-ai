from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ResearchArtifactModel


class ResearchArtifactDao:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        asset_id: int,
        *,
        data_as_of: datetime | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> ResearchArtifactModel:
        artifact = ResearchArtifactModel(
            asset_id=asset_id,
            data_as_of=data_as_of,
            model=model,
            prompt_version=prompt_version,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

    async def get_by_id(self, artifact_id: int) -> ResearchArtifactModel | None:
        return await self._session.get(ResearchArtifactModel, artifact_id)

    async def get_latest_for_asset(
        self,
        asset_id: int,
    ) -> ResearchArtifactModel | None:
        result = await self._session.execute(
            select(ResearchArtifactModel)
            .where(ResearchArtifactModel.asset_id == asset_id)
            .order_by(
                ResearchArtifactModel.created_at.desc(),
                ResearchArtifactModel.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
