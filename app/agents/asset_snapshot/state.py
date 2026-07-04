from typing import TypedDict

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetSnapshotRequest
from app.domain.schemas.company_peer_context import CompanyPeerContext
from app.domain.schemas.sector_context import SectorContext


class AssetSnapshotState(TypedDict, total=False):
    request: AssetSnapshotRequest
    resolved_asset: str | None
    asset_profile_context: AssetProfileContext | None
    company_peers_context: CompanyPeerContext | None
    sector_context: SectorContext | None
    selected_tool_name: str | None
    generation_prompt: str | None
    raw_llm_output: str | None
    validated_output: AssetSnapshot | None
    errors: list[str]
