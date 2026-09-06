import logging

from app.agents.asset_snapshot.router.graph import AssetSnapshotRouterGraph
from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest, StockAssetSnapshot
from app.domain.schemas.snapshot_evidence import AssetSnapshotRunResult

logger = logging.getLogger(__name__)


class AssetSnapshotGraphRunner:
    def __init__(self, router_graph: AssetSnapshotRouterGraph) -> None:
        self._router_graph = router_graph

    async def run(
        self,
        request: AssetSnapshotRequest,
        with_evidence: bool = False
    ) -> StockAssetSnapshot:
        result = await self.run_with_evidence(request, to_persist_evidence=with_evidence)
        return result.snapshot

    async def run_with_evidence(
        self,
        request: AssetSnapshotRequest,
        with_evidence: bool = False
    ) -> AssetSnapshotRunResult:
        settings = get_settings()

        if settings.app_log_flow_steps:
            logger.info(
                "asset_snapshot.router.run.start asset=%s asset_type=%s",
                request.asset,
                request.asset_type.value,
            )

        final_state = await self._router_graph.ainvoke({"request": request}, with_evidence=with_evidence)

        validated_output = final_state.get("validated_output")
        snapshot_evidence = final_state.get("snapshot_evidence")
        error = final_state.get("error")

        if settings.app_log_flow_steps:
            logger.info(
                "asset_snapshot.router.run.end success=%s error=%s",
                validated_output is not None,
                error,
            )

        if validated_output is None or snapshot_evidence is None:
            logger.error("asset_snapshot.router.run.failed error=%s", error)
            raise ServiceError("Asset snapshot generation failed. Please try again.")

        return AssetSnapshotRunResult(
            snapshot=validated_output,
            evidence=snapshot_evidence,
        )
