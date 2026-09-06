from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.snapshot_evidence import SnapshotEvidence
from app.infrastructure.db.models import EvidenceModel


class EvidenceDao:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        asset_id: int,
        evidence: SnapshotEvidence,
    ) -> EvidenceModel:
        model = EvidenceModel(
            asset_id=asset_id,
            context_json=evidence.model_dump_json(),
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_id(self, evidence_id: int) -> SnapshotEvidence | None:
        model = await self._session.get(EvidenceModel, evidence_id)
        if model is None:
            return None
        return SnapshotEvidence.model_validate_json(model.context_json)
