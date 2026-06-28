import logging

from app.agents.asset_snapshot.asset_resolver import (
    normalize_resolved_asset,
    resolve_ambiguous_asset,
    resolve_deterministic_asset,
    should_resolve_ambiguous_asset,
)
from app.agents.asset_snapshot.state import AssetSnapshotState
from app.agents.asset_snapshot.tools import AssetSnapshotTool
from app.core.config import get_settings
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetType
from app.llm.base import BaseChatModelClient
from app.llm.json_parser import parse_llm_json
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder

_RESOLUTION_CONFIDENCE_THRESHOLD = 0.7
logger = logging.getLogger(__name__)


async def ambiguous_asset_resolution_node(
    state: AssetSnapshotState,
    llm: BaseChatModelClient,
) -> AssetSnapshotState:
    request = state["request"]
    settings = get_settings()
    deterministic_asset = resolve_deterministic_asset(
        request.asset,
        request.asset_type,
    )

    if deterministic_asset and deterministic_asset != request.asset:
        if settings.app_log_flow_steps:
            logger.info(
                "ambiguous_asset_resolution.deterministic original=%s resolved=%s",
                request.asset,
                deterministic_asset,
            )
        return {"resolved_asset": deterministic_asset}

    if not should_resolve_ambiguous_asset(request.asset, request.asset_type):
        if settings.app_log_flow_steps:
            logger.info(
                "ambiguous_asset_resolution.skipped asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )
        return {"resolved_asset": None}

    try:
        if settings.app_log_flow_steps:
            logger.info(
                "ambiguous_asset_resolution.start asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )
        resolution = await resolve_ambiguous_asset(
            asset=request.asset,
            asset_type=request.asset_type,
            llm=llm,
        )
    except Exception as exc:
        logger.exception("ambiguous_asset_resolution.failed asset=%s", request.asset)
        return {
            "resolved_asset": None,
            "errors": state.get("errors", [])
            + [f"ambiguous_asset_resolution_failed: {exc}"],
        }

    resolved_asset = normalize_resolved_asset(resolution.resolved_asset)

    if resolved_asset and resolution.confidence >= _RESOLUTION_CONFIDENCE_THRESHOLD:
        if settings.app_log_flow_steps:
            logger.info(
                "ambiguous_asset_resolution.resolved original=%s resolved=%s "
                "confidence=%.2f",
                request.asset,
                resolved_asset,
                resolution.confidence,
            )
        return {"resolved_asset": resolved_asset.strip().upper()}

    if settings.app_log_flow_steps:
        logger.info(
            "ambiguous_asset_resolution.rejected asset=%s proposed=%s confidence=%.2f",
            request.asset,
            resolution.resolved_asset,
            resolution.confidence,
        )

    return {"resolved_asset": None}


async def planner_node(state: AssetSnapshotState) -> AssetSnapshotState:
    request = state["request"]
    settings = get_settings()

    if request.asset_type in {AssetType.STOCK, AssetType.ETF}:
        if settings.app_log_flow_steps:
            logger.info(
                "planner.selected_tool asset=%s asset_type=%s tool=%s",
                state.get("resolved_asset") or request.asset,
                request.asset_type.value,
                "stable_asset_profile_search",
            )
        return {"selected_tool_name": "stable_asset_profile_search"}

    if settings.app_log_flow_steps:
        logger.info(
            "planner.no_tool asset=%s asset_type=%s",
            request.asset,
            request.asset_type.value,
        )

    return {
        "selected_tool_name": None,
        "errors": state.get("errors", [])
        + [
            "No asset snapshot tool configured for "
            f"asset_type={request.asset_type.name}"
        ],
    }


async def asset_profile_tool_node(
    state: AssetSnapshotState,
    tools: dict[str, AssetSnapshotTool],
) -> AssetSnapshotState:
    request = state["request"]
    selected_tool_name = state.get("selected_tool_name")
    settings = get_settings()

    if not selected_tool_name:
        if settings.app_log_flow_steps:
            logger.info("asset_profile_tool.skipped reason=no_tool_selected")
        return {"asset_profile_context": None}

    tool = tools.get(selected_tool_name)

    if tool is None:
        logger.error("asset_profile_tool.missing tool=%s", selected_tool_name)
        return {
            "asset_profile_context": None,
            "errors": state.get("errors", [])
            + [f"Selected tool not found: {selected_tool_name}"],
        }

    try:
        asset = state.get("resolved_asset") or request.asset
        if settings.app_log_flow_steps:
            logger.info(
                "asset_profile_tool.start tool=%s asset=%s asset_type=%s",
                selected_tool_name,
                asset,
                request.asset_type.value,
            )
        asset_profile_context = await tool.run(
            asset=asset,
            asset_type=request.asset_type,
        )
        if settings.app_log_flow_steps:
            logger.info(
                "asset_profile_tool.end found=%s provider=%s",
                asset_profile_context is not None,
                asset_profile_context.provider if asset_profile_context else None,
            )
        return {"asset_profile_context": asset_profile_context}

    except Exception as exc:
        logger.exception(
            "asset_profile_tool.failed tool=%s asset=%s",
            selected_tool_name,
            state.get("resolved_asset") or request.asset,
        )
        return {
            "asset_profile_context": None,
            "errors": state.get("errors", []) + [f"asset_profile_tool_failed: {exc}"],
        }


async def generate_snapshot_node(
    state: AssetSnapshotState,
    llm: BaseChatModelClient,
    prompt_builder: AssetSnapshotPromptBuilder,
) -> AssetSnapshotState:
    request = state["request"]
    asset = state.get("resolved_asset") or request.asset
    settings = get_settings()

    prompt = prompt_builder.build_prompt(
        asset=asset,
        asset_type=request.asset_type,
        asset_profile_context=state.get("asset_profile_context"),
    )

    if settings.app_log_flow_steps:
        logger.info(
            "generate_snapshot.prompt_built asset=%s asset_type=%s chars=%s "
            "has_profile_context=%s",
            asset,
            request.asset_type.value,
            len(prompt),
            state.get("asset_profile_context") is not None,
        )

    try:
        raw_llm_output = await llm.generate(prompt)
        if settings.app_log_flow_steps:
            logger.info(
                "generate_snapshot.llm_output_received chars=%s",
                len(raw_llm_output),
            )
        return {"generation_prompt": prompt, "raw_llm_output": raw_llm_output}
    except Exception as e:
        logger.exception("generate_snapshot.failed asset=%s", asset)
        return {
            "raw_llm_output": None,
            "errors": state.get("errors", []) + [f"LLM generation error: {e}"],
        }


async def validate_snapshot_node(state: AssetSnapshotState) -> AssetSnapshotState:
    raw_llm_output = state.get("raw_llm_output")
    settings = get_settings()

    if not raw_llm_output:
        if settings.app_log_flow_steps:
            logger.info("validate_snapshot.skipped reason=no_llm_output")
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + ["No LLM output to validate"],
        }

    try:
        data = parse_llm_json(raw_llm_output)
        validated_output = AssetSnapshot.model_validate(data)
        if settings.app_log_flow_steps:
            logger.info(
                "validate_snapshot.success asset=%s asset_type=%s",
                validated_output.asset,
                validated_output.asset_type.value,
            )
        return {"validated_output": validated_output}
    except Exception as e:
        logger.exception("validate_snapshot.failed")
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + [f"LLM output parse error: {e}"],
        }
