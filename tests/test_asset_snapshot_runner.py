from unittest.mock import AsyncMock

import pytest

from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest, AssetType


@pytest.mark.asyncio
async def test_runner_raises_service_error_when_graph_has_no_valid_snapshot() -> None:
    router_graph = AsyncMock()
    router_graph.ainvoke.return_value = {
        "validated_output": None,
        "error": "LLM output parse error",
    }
    runner = AssetSnapshotGraphRunner(router_graph=router_graph)

    request = AssetSnapshotRequest(asset="GOOGL", asset_type=AssetType.STOCK)

    with pytest.raises(ServiceError, match="Asset snapshot generation failed"):
        await runner.run(request)
