
from pydantic import ValidationError

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotMode,
    AssetType,
    LongAssetSnapshot,
    ShortAssetSnapshot,
)
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder


class AssetSnapshotService:
    def __init__(
        self,
        llm_client: OllamaChatClient,
        prompt_builder: AssetSnapshotPromptBuilder,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder

    async def get_snapshot(
        self, asset: str, asset_type: AssetType, mode: AssetSnapshotMode
    ) -> ShortAssetSnapshot | LongAssetSnapshot:
        prompt = self.prompt_builder.build_prompt(asset, asset_type, mode)

        response = await self.llm_client.generate(prompt)

        try:
            if mode == AssetSnapshotMode.SHORT:
                return ShortAssetSnapshot.model_validate_json(response)
            return LongAssetSnapshot.model_validate_json(response)
        except ValidationError as e:
            raise ValueError(
                f"Failed to parse LLM response into AssetSnapshot: {e}\nResponse content: {response}"
            ) from e
   