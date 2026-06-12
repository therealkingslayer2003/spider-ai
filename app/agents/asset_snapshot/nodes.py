import json

from app.agents.asset_snapshot.state import AssetSnapshotState
from app.agents.asset_snapshot.tools import AssetSnapshotTool
from app.domain.schemas.asset_snapshot import AssetSnapshotMode, AssetType, LongAssetSnapshot, ShortAssetSnapshot
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder


async def planner_node(state: AssetSnapshotState) -> AssetSnapshotState:
    request = state["request"]

    if request.asset_type == AssetType.STOCK:
        return {"selected_tool_name": "stable_asset_profile_search"}

    return {
        "selected_tool_name": None,
        "errors": state.get("errors", []) + [
            f"No asset snapshot tool configured for asset_type={request.asset_type}"
        ],
    }


async def asset_profile_tool_node(
    state: AssetSnapshotState,
    tools: dict[str, AssetSnapshotTool],
) -> AssetSnapshotState:
    request = state["request"]
    selected_tool_name = state.get("selected_tool_name")

    if not selected_tool_name:
        return {"asset_profile_context": None}

    tool = tools.get(selected_tool_name)

    if tool is None:
        return {
            "asset_profile_context": None,
            "errors": state.get("errors", []) + [
                f"Selected tool not found: {selected_tool_name}"
            ],
        }

    try:
        asset_profile_context = await tool.run(
            asset=request.asset,
            asset_type=request.asset_type,
        )
        return {"asset_profile_context": asset_profile_context}

    except Exception as exc:
        return {
            "asset_profile_context": None,
            "errors": state.get("errors", []) + [f"asset_profile_tool_failed: {exc}"],
        }


async def generate_snapshot_node(
    state: AssetSnapshotState,
    llm: OllamaChatClient,
    prompt_builder: AssetSnapshotPromptBuilder,
) -> AssetSnapshotState:
    request = state["request"]

    prompt = prompt_builder.build_prompt(
        asset=request.asset,
        asset_type=request.asset_type,
        mode=request.mode,
        asset_profile_context=state.get("asset_profile_context"),
    )

    try:
        raw_llm_output = await llm.generate(prompt)
        return {"raw_llm_output": raw_llm_output}
    except Exception as e:
        return {
            "raw_llm_output": None,
            "errors": state.get("errors", []) + [f"LLM generation error: {e}"],
        }


async def validate_snapshot_node(state: AssetSnapshotState) -> AssetSnapshotState:
    raw_llm_output = state.get("raw_llm_output")

    if not raw_llm_output:
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + ["No LLM output to validate"],
        }

    try:
        data = json.loads(raw_llm_output)
        mode = data.get("mode")
        if mode == AssetSnapshotMode.SHORT:
            validated_output = ShortAssetSnapshot.model_validate(data)
        else:
            validated_output = LongAssetSnapshot.model_validate(data)
        return {"validated_output": validated_output}
    except Exception as e:
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + [f"LLM output parse error: {e}"],
        }
