from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.domain.schemas.snapshot_evidence import SnapshotEvidence
from app.infrastructure.db.models import (
    AssetModel,
    AssetTypeModel,
    EvidenceModel,
    ResearchArtifactModel,
    SnapshotResearchArtifactModel,
)


@dataclass(frozen=True)
class SnapshotArtifactAggregate:
    research_artifact_id: int
    evidence_id: int
    asset_id: int
    asset_name: str
    asset_type: str
    created_at: datetime
    data_as_of: datetime | None
    model: str | None
    prompt_version: str | None
    snapshot: StockAssetSnapshot
    evidence: SnapshotEvidence
    rationale: str | None


class SnapshotResearchArtifactDao:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        research_artifact_id: int,
        evidence_id: int,
        snapshot: StockAssetSnapshot,
        rationale: str | None = None,
    ) -> SnapshotResearchArtifactModel:
        model = SnapshotResearchArtifactModel(
            research_artifact_id=research_artifact_id,
            evidence_id=evidence_id,
            output_json=snapshot.model_dump_json(),
            rationale=rationale,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_research_artifact_id(
        self,
        research_artifact_id: int,
    ) -> SnapshotArtifactAggregate | None:
        statement = self._aggregate_statement().where(
            SnapshotResearchArtifactModel.research_artifact_id == research_artifact_id
        )
        result = await self._session.execute(statement)
        row = result.one_or_none()
        return self._to_aggregate(row) if row is not None else None

    async def get_latest_for_asset(
        self,
        asset_name: str,
        asset_type: str,
    ) -> SnapshotArtifactAggregate | None:
        statement = (
            self._aggregate_statement()
            .where(
                AssetModel.name == asset_name.strip().upper(),
                AssetTypeModel.name == asset_type.strip().lower(),
            )
            .order_by(
                ResearchArtifactModel.created_at.desc(),
                ResearchArtifactModel.id.desc(),
            )
            .limit(1)
        )
        result = await self._session.execute(statement)
        row = result.one_or_none()
        return self._to_aggregate(row) if row is not None else None

    @staticmethod
    def _aggregate_statement():
        return (
            select(
                SnapshotResearchArtifactModel,
                ResearchArtifactModel,
                EvidenceModel,
                AssetModel,
                AssetTypeModel,
            )
            .join(
                ResearchArtifactModel,
                ResearchArtifactModel.id
                == SnapshotResearchArtifactModel.research_artifact_id,
            )
            .join(
                EvidenceModel,
                EvidenceModel.id == SnapshotResearchArtifactModel.evidence_id,
            )
            .join(AssetModel, AssetModel.id == ResearchArtifactModel.asset_id)
            .join(AssetTypeModel, AssetTypeModel.id == AssetModel.asset_type_id)
        )

    @staticmethod
    def _to_aggregate(row) -> SnapshotArtifactAggregate:
        snapshot_model, artifact, evidence, asset, asset_type = row
        return SnapshotArtifactAggregate(
            research_artifact_id=artifact.id,
            evidence_id=evidence.id,
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset_type.name,
            created_at=artifact.created_at,
            data_as_of=artifact.data_as_of,
            model=artifact.model,
            prompt_version=artifact.prompt_version,
            snapshot=StockAssetSnapshot.model_validate_json(snapshot_model.output_json),
            evidence=SnapshotEvidence.model_validate_json(evidence.context_json),
            rationale=snapshot_model.rationale,
        )
