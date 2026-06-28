from langgraph.graph import END, START, StateGraph

from app.agents.asset_snapshot.nodes import (
    ambiguous_asset_resolution_node,
    asset_profile_tool_node,
    generate_snapshot_node,
    planner_node,
    validate_snapshot_node,
)
from app.agents.asset_snapshot.state import AssetSnapshotState
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.tools.asset_snapshot.stable_asset_profile_search import (
    StableAssetProfileSearchTool,
)


def build_asset_snapshot_graph(
    profile_tool: StableAssetProfileSearchTool,
    prompt_builder: AssetSnapshotPromptBuilder,
    llm_client: OllamaChatClient,
):
    tools = {"stable_asset_profile_search": profile_tool}

    async def ambiguous_asset_resolution_node_wrapper(state: AssetSnapshotState):
        return await ambiguous_asset_resolution_node(state, llm_client)

    async def asset_profile_tool_node_wrapper(state: AssetSnapshotState):
        return await asset_profile_tool_node(state, tools)

    async def generate_snapshot_node_wrapper(state: AssetSnapshotState):
        return await generate_snapshot_node(state, llm_client, prompt_builder)

    graph = StateGraph(AssetSnapshotState)

    graph.add_node(
        "ambiguous_asset_resolution", ambiguous_asset_resolution_node_wrapper
    )
    graph.add_node("planner", planner_node)
    graph.add_node("asset_profile_tool", asset_profile_tool_node_wrapper)
    graph.add_node("generate_snapshot", generate_snapshot_node_wrapper)
    graph.add_node("validate_snapshot", validate_snapshot_node)

    graph.add_edge(START, "ambiguous_asset_resolution")
    graph.add_edge("ambiguous_asset_resolution", "planner")
    graph.add_edge("planner", "asset_profile_tool")
    graph.add_edge("asset_profile_tool", "generate_snapshot")
    graph.add_edge("generate_snapshot", "validate_snapshot")
    graph.add_edge("validate_snapshot", END)

    return graph.compile()
