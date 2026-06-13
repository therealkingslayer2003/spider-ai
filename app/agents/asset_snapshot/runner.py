from app.agents.asset_snapshot.graph import build_asset_snapshot_graph
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetSnapshotRequest
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.llm.ollama_client import OllamaChatClient
from app.tools.asset_snapshot.stable_asset_profile_search import StableAssetProfileSearchTool


class AssetSnapshotGraphRunner:
    def __init__(
        self,
        profile_tool: StableAssetProfileSearchTool,
        prompt_builder: AssetSnapshotPromptBuilder,
        llm_client: OllamaChatClient,
    ) -> None:
        self.graph = build_asset_snapshot_graph(
            profile_tool=profile_tool,
            prompt_builder=prompt_builder,
            llm_client=llm_client,
        )

    async def run(
        self,
        request: AssetSnapshotRequest,
    ) -> AssetSnapshot:
        final_state = await self.graph.ainvoke(
            {
                "request": request,
                "errors": [],
            }
        )

        return final_state["validated_output"]
