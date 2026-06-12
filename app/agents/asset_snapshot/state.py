from typing import Any, TypedDict

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest, LongAssetSnapshot, ShortAssetSnapshot


class AssetSnapshotState(TypedDict):
    request: AssetSnapshotRequest
    asset_profile_context: AssetProfileContext | None
    selected_tool_name: str | None
    raw_llm_output: str | None
    validated_output: ShortAssetSnapshot | LongAssetSnapshot | None
    errors: list[str]