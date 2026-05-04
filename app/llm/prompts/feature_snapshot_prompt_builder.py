from app.domain.schemas.asset_snapshot import AssetSnapshotMode, AssetType
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT
from app.llm.prompts.feature_snapshot_prompt import (
    LONG_ASSET_SNAPSHOT_PROMPT,
    SHORT_ASSET_SNAPSHOT_PROMPT,
)


class AssetSnapshotPromptBuilder:
    def build_prompt(
        self, asset: str, asset_type: AssetType, mode: AssetSnapshotMode
    ) -> str:
        if mode == AssetSnapshotMode.SHORT:
            mode_prompt = SHORT_ASSET_SNAPSHOT_PROMPT
        else:
            mode_prompt = LONG_ASSET_SNAPSHOT_PROMPT
        return (
            BASE_SYSTEM_PROMPT
            + "\n\n"
            + mode_prompt.format(asset=asset, asset_type=asset_type.value)
        )
