from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.domain.schemas.asset_snapshot import AssetSnapshot, AssetSnapshotRequest


class AssetSnapshotService:
    def __init__(self, graph_runner: AssetSnapshotGraphRunner) -> None:
        self.graph_runner = graph_runner

    async def get_snapshot(self, request: AssetSnapshotRequest) -> AssetSnapshot:
        return await self.graph_runner.run(request)
