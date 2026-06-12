from fastapi import Depends

from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.chat_service import ChatService
from app.tools.asset_snapshot.stable_asset_profile_search import StableAssetProfileSearchTool


def get_ollama_client() -> OllamaChatClient:
    return OllamaChatClient()


def get_prompt_builder() -> AssetSnapshotPromptBuilder:
    return AssetSnapshotPromptBuilder()


def get_profile_tool() -> StableAssetProfileSearchTool:
    return StableAssetProfileSearchTool()


def get_graph_runner(
    profile_tool: StableAssetProfileSearchTool = Depends(get_profile_tool),
    prompt_builder: AssetSnapshotPromptBuilder = Depends(get_prompt_builder),
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> AssetSnapshotGraphRunner:
    return AssetSnapshotGraphRunner(
        profile_tool=profile_tool,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )


def get_chat_service(
    llm_client: OllamaChatClient = Depends(get_ollama_client),
) -> ChatService:
    return ChatService(llm_client=llm_client)


def get_asset_snapshot_service(
    graph_runner: AssetSnapshotGraphRunner = Depends(get_graph_runner),
) -> AssetSnapshotService:
    return AssetSnapshotService(graph_runner=graph_runner)
