from pydantic import BaseModel

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext


class AssetSnapshotEvidence(BaseModel):
    asset_profile_context: AssetProfileContext | None = None
    company_peers_context: CompanyPeersContext | None = None
    company_fundamentals_context: CompanyFundamentalsContext | None = None
    data_scope: str


class AssetSnapshotRunResult(BaseModel):
    snapshot: StockAssetSnapshot
    evidence: AssetSnapshotEvidence
