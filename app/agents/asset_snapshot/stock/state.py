from typing import TypedDict

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest, StockAssetSnapshot
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext


class StockSnapshotState(TypedDict, total=False):
    request: AssetSnapshotRequest
    resolved_asset: str | None
    asset_profile_context: AssetProfileContext | None
    company_peers_context: CompanyPeersContext | None
    company_fundamentals_context: CompanyFundamentalsContext | None
    generation_prompt: str | None
    validated_output: StockAssetSnapshot | None
    data_scope: str | None
    errors: list[str]
