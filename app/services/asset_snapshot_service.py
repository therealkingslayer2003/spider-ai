import logging

from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest, StockAssetSnapshot
from app.services.snapshot_artifact_persistence_service import (
    SnapshotArtifactPersistenceService,
)

logger = logging.getLogger(__name__)


class AssetSnapshotService:
    def __init__(
        self,
        graph_runner: AssetSnapshotGraphRunner,
        persistence_service: SnapshotArtifactPersistenceService | None = None,
    ) -> None:
        self.graph_runner = graph_runner
        self._persistence_service = persistence_service

    async def get_snapshot(self, request: AssetSnapshotRequest) -> StockAssetSnapshot:
        if self._persistence_service is None:
            logger.warning(
                "asset_snapshot.persistence_service_unavailable asset=%s",
                request.asset,
            )
            return await self.graph_runner.run(request)

        result = await self.graph_runner.run_result(request)
        try:
            await self._persistence_service.persist(
                snapshot=result.snapshot,
                evidence=result.evidence,
            )
        except Exception as exc:
            logger.exception(
                "asset_snapshot.persistence_failed asset=%s",
                result.snapshot.asset,
            )
            raise ServiceError(
                "Asset snapshot persistence failed. Please try again."
            ) from exc

        return result.snapshot
