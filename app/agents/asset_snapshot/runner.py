import logging

from app.agents.asset_snapshot.graph import build_asset_snapshot_graph
from app.agents.asset_snapshot.tools import (
    CompanyPeersTool,
    SectorContextTool,
    StableAssetProfileSearchTool,
)
from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetSnapshotRequest
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder

logger = logging.getLogger(__name__)


class AssetSnapshotGraphRunner:
    def __init__(
        self,
        profile_tool: StableAssetProfileSearchTool,
        sector_context_tool: SectorContextTool,
        company_peers_tool: CompanyPeersTool,
        prompt_builder: AssetSnapshotPromptBuilder,
        llm_client: OllamaChatClient,
    ) -> None:
        self.graph = build_asset_snapshot_graph(
            profile_tool=profile_tool,
            sector_context_tool=sector_context_tool,
            company_peers_tool=company_peers_tool,
            prompt_builder=prompt_builder,
            llm_client=llm_client,
        )

    async def run(
        self,
        request: AssetSnapshotRequest,
    ) -> AssetSnapshot:
        settings = get_settings()

        if settings.app_log_flow_steps:
            logger.info(
                "asset_snapshot.run.start asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )

        final_state = await self.graph.ainvoke(
            {
                "request": request,
                "errors": [],
            }
        )

        validated_output = final_state.get("validated_output")
        errors = final_state.get("errors", [])

        if settings.app_log_flow_steps:
            logger.info(
                "asset_snapshot.run.end success=%s errors=%s",
                validated_output is not None,
                len(errors),
            )

        if validated_output is None:
            logger.error("asset_snapshot.run.failed errors=%s", errors)
            raise ServiceError("Asset snapshot generation failed. Please try again.")

        return validated_output
