import logging

from app.agents.asset_snapshot.asset_resolver import (
    normalize_resolved_asset,
    resolve_ambiguous_asset,
    resolve_deterministic_asset,
    should_resolve_ambiguous_asset,
)
from app.agents.asset_snapshot.stock.state import StockSnapshotState
from app.agents.asset_snapshot.tools import (
    CompanyFundamentalsTool,
    CompanyPeersTool,
    CompanyProfileTool,
)
from app.core.config import get_settings
from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from app.llm.json_parser import parse_llm_json
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder

_RESOLUTION_CONFIDENCE_THRESHOLD = 0.7
logger = logging.getLogger(__name__)


async def ambiguous_asset_resolution_node(
    state: StockSnapshotState,
    llm: BaseChatModelClient,
) -> StockSnapshotState:
    request = state["request"]
    settings = get_settings()
    deterministic_asset = resolve_deterministic_asset(
        request.asset,
        request.asset_type,
    )

    if deterministic_asset and deterministic_asset != request.asset:
        if settings.app_log_flow_steps:
            logger.info(
                "stock.asset_resolution.deterministic original=%s resolved=%s",
                request.asset,
                deterministic_asset,
            )
        return {"resolved_asset": deterministic_asset}

    if not should_resolve_ambiguous_asset(request.asset, request.asset_type):
        if settings.app_log_flow_steps:
            logger.info(
                "stock.asset_resolution.skipped asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )
        return {"resolved_asset": None}

    try:
        if settings.app_log_flow_steps:
            logger.info(
                "stock.asset_resolution.start asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )
        resolution = await resolve_ambiguous_asset(
            asset=request.asset,
            asset_type=request.asset_type,
            llm=llm,
        )
    except Exception as exc:
        logger.exception("stock.asset_resolution.failed asset=%s", request.asset)
        return {
            "resolved_asset": None,
            "errors": state.get("errors", [])
            + [f"ambiguous_asset_resolution_failed: {exc}"],
        }

    resolved_asset = normalize_resolved_asset(resolution.resolved_asset)

    if resolved_asset and resolution.confidence >= _RESOLUTION_CONFIDENCE_THRESHOLD:
        if settings.app_log_flow_steps:
            logger.info(
                "stock.asset_resolution.resolved original=%s resolved=%s "
                "confidence=%.2f",
                request.asset,
                resolved_asset,
                resolution.confidence,
            )
        return {"resolved_asset": resolved_asset.strip().upper()}

    if settings.app_log_flow_steps:
        logger.info(
            "stock.asset_resolution.rejected asset=%s proposed=%s confidence=%.2f",
            request.asset,
            resolution.resolved_asset,
            resolution.confidence,
        )

    return {"resolved_asset": None}


async def company_profile_node(
    state: StockSnapshotState,
    tool: CompanyProfileTool,
) -> StockSnapshotState:
    request = state["request"]
    asset = state.get("resolved_asset") or request.asset
    settings = get_settings()

    try:
        if settings.app_log_flow_steps:
            logger.info(
                "stock.company_profile.start asset=%s asset_type=%s",
                asset,
                request.asset_type.value,
            )
        asset_profile_context = await tool.run(
            asset=asset,
            asset_type=request.asset_type,
        )
        if settings.app_log_flow_steps:
            logger.info(
                "stock.company_profile.end found=%s provider=%s",
                asset_profile_context is not None,
                asset_profile_context.provider if asset_profile_context else None,
            )
        return {"asset_profile_context": asset_profile_context}

    except Exception as exc:
        logger.exception("stock.company_profile.failed asset=%s", asset)
        return {
            "asset_profile_context": None,
            "errors": state.get("errors", []) + [f"company_profile_failed: {exc}"],
        }


async def company_peers_node(
    state: StockSnapshotState,
    tool: CompanyPeersTool,
) -> StockSnapshotState:
    request = state["request"]
    asset = state.get("resolved_asset") or request.asset
    settings = get_settings()

    try:
        if settings.app_log_flow_steps:
            logger.info("stock.company_peers.start asset=%s", asset)

        company_peers_context = await tool.run(
            asset_profile_context=state.get("asset_profile_context"),
        )

        if settings.app_log_flow_steps:
            logger.info(
                "stock.company_peers.end provider=%s peers=%s",
                company_peers_context.provider,
                len(company_peers_context.peers),
            )

        return {"company_peers_context": company_peers_context}
    except Exception as exc:
        logger.exception("stock.company_peers.failed asset=%s", asset)
        return {
            "company_peers_context": None,
            "errors": state.get("errors", []) + [f"company_peers_failed: {exc}"],
        }


async def company_fundamentals_node(
    state: StockSnapshotState,
    tool: CompanyFundamentalsTool,
) -> StockSnapshotState:
    request = state["request"]
    asset = state.get("resolved_asset") or request.asset
    settings = get_settings()

    try:
        if settings.app_log_flow_steps:
            logger.info("stock.company_fundamentals.start asset=%s", asset)

        company_fundamentals_context = await tool.run(
            asset_profile_context=state.get("asset_profile_context"),
        )

        if settings.app_log_flow_steps:
            logger.info(
                "stock.company_fundamentals.end provider=%s",
                company_fundamentals_context.provider,
            )

        return {"company_fundamentals_context": company_fundamentals_context}
    except Exception as exc:
        logger.exception("stock.company_fundamentals.failed asset=%s", asset)
        return {
            "company_fundamentals_context": None,
            "errors": state.get("errors", []) + [f"company_fundamentals_failed: {exc}"],
        }


async def generate_stock_snapshot_node(
    state: StockSnapshotState,
    llm: BaseChatModelClient,
    prompt_builder: StockSnapshotPromptBuilder,
) -> StockSnapshotState:
    request = state["request"]
    asset = state.get("resolved_asset") or request.asset
    settings = get_settings()

    prompt = prompt_builder.build_prompt(
        asset=asset,
        asset_type=request.asset_type,
        asset_profile_context=state.get("asset_profile_context"),
        company_peers_context=state.get("company_peers_context"),
        company_fundamentals_context=state.get("company_fundamentals_context"),
    )

    data_scope = prompt_builder.data_scope(
        asset_profile_context=state.get("asset_profile_context"),
        company_peers_context=state.get("company_peers_context"),
        company_fundamentals_context=state.get("company_fundamentals_context"),
    )

    if settings.app_log_flow_steps:
        logger.info(
            "stock.generate_snapshot.prompt_built asset=%s asset_type=%s chars=%s "
            "data_scope=%s",
            asset,
            request.asset_type.value,
            len(prompt),
            data_scope,
        )

    try:
        raw_llm_output = await llm.generate(prompt)
        if settings.app_log_flow_steps:
            logger.info(
                "stock.generate_snapshot.llm_output_received chars=%s",
                len(raw_llm_output),
            )
        return {
            "data_scope": data_scope,
            "generation_prompt": prompt,
            "raw_llm_output": raw_llm_output,
        }
    except Exception as exc:
        logger.exception("stock.generate_snapshot.failed asset=%s", asset)
        return {
            "data_scope": data_scope,
            "raw_llm_output": None,
            "errors": state.get("errors", []) + [f"LLM generation error: {exc}"],
        }


async def validate_stock_snapshot_node(
    state: StockSnapshotState,
) -> StockSnapshotState:
    raw_llm_output = state.get("raw_llm_output")
    settings = get_settings()

    if not raw_llm_output:
        if settings.app_log_flow_steps:
            logger.info("stock.validate_snapshot.skipped reason=no_llm_output")
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + ["No LLM output to validate"],
        }

    try:
        data = parse_llm_json(raw_llm_output)
        request = state.get("request")
        if request is not None and isinstance(data, dict):
            canonical_asset = state.get("resolved_asset") or request.asset
            canonical_data_scope = state.get("data_scope")
            generated_metadata = (
                data.get("asset"),
                data.get("asset_type"),
                data.get("data_scope"),
            )
            canonical_metadata = (
                canonical_asset,
                request.asset_type.value,
                canonical_data_scope,
            )
            if generated_metadata != canonical_metadata:
                logger.warning(
                    "stock.validate_snapshot.metadata_normalized "
                    "generated_asset=%s generated_asset_type=%s "
                    "generated_data_scope=%s",
                    *generated_metadata,
                )
            data = {
                **data,
                "asset": canonical_asset,
                "asset_type": request.asset_type.value,
            }
            if canonical_data_scope is not None:
                data["data_scope"] = canonical_data_scope

        validated_output = StockAssetSnapshot.model_validate(data)
        peers = state.get("company_peers_context")
        if peers and peers.peers and not validated_output.competitive_landscape:
            logger.warning(
                "stock.validate_snapshot.empty_landscape candidates=%s profiles=%s "
                "reason=provider_reported_peers_not_acknowledged",
                len(peers.peers),
                sum(peer.profile is not None for peer in peers.peers),
            )
        if settings.app_log_flow_steps:
            logger.info(
                "stock.validate_snapshot.success asset=%s asset_type=%s",
                validated_output.asset,
                validated_output.asset_type.value,
            )
        return {"validated_output": validated_output}
    except Exception as exc:
        logger.exception("stock.validate_snapshot.failed")
        return {
            "validated_output": None,
            "errors": state.get("errors", []) + [f"LLM output parse error: {exc}"],
        }
