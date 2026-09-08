import logging
from datetime import datetime

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.domain.schemas.asset_snapshot_evidence import AssetSnapshotEvidence
from app.infrastructure.db.dao import (
    AssetDao,
    AssetTypeDao,
    EvidenceDao,
    ResearchArtifactDao,
    SnapshotResearchArtifactDao,
)
from app.infrastructure.db.database import Database

logger = logging.getLogger(__name__)


class SnapshotArtifactPersistenceService:
    def __init__(
        self,
        database: Database,
        *,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        self._database = database
        self._model = model
        self._prompt_version = prompt_version

    async def persist(
        self,
        snapshot: StockAssetSnapshot,
        evidence: AssetSnapshotEvidence,
        *,
        data_as_of: datetime | None = None,
    ) -> int:
        await self._database.initialize()

        async with self._database.session_factory() as session:
            async with session.begin():
                asset_type = await AssetTypeDao(session).get_or_create(
                    snapshot.asset_type.value
                )
                asset = await AssetDao(session).get_or_create(
                    asset_type.id,
                    snapshot.asset,
                )
                evidence_model = await EvidenceDao(session).create(
                    asset.id,
                    evidence,
                )
                research_artifact = await ResearchArtifactDao(session).create(
                    asset.id,
                    data_as_of=data_as_of,
                    model=self._model,
                    prompt_version=self._prompt_version,
                )
                await SnapshotResearchArtifactDao(session).create(
                    research_artifact.id,
                    evidence_model.id,
                    snapshot,
                )

        logger.info(
            "snapshot_artifact.persisted research_artifact_id=%s asset=%s",
            research_artifact.id,
            snapshot.asset,
        )
        return research_artifact.id
