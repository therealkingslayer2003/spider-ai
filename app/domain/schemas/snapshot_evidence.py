from pydantic import BaseModel

from app.domain.schemas.asset_snapshot import StockAssetSnapshot


class SnapshotEvidence(BaseModel):
    snapshot : StockAssetSnapshot
    rationale: str | None = None


class AssetSnapshotRunResult(BaseModel):
    snapshot: StockAssetSnapshot
    evidence: SnapshotEvidence
