from unittest.mock import AsyncMock

import pytest

from app.domain.schemas.asset_snapshot import (
    AssetSnapshot,
    AssetSnapshotRequest,
    AssetType,
)
from app.services.asset_snapshot_service import AssetSnapshotService


@pytest.fixture
def mock_graph_runner() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def snapshot_request() -> AssetSnapshotRequest:
    return AssetSnapshotRequest(asset="NVDA", asset_type=AssetType.STOCK)


@pytest.fixture
def snapshot() -> AssetSnapshot:
    return AssetSnapshot(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        summary="NVDA is a GPU manufacturer.",
        market_context="Semiconductor sector.",
        business_or_asset_profile="Designs GPUs for gaming and AI.",
        structural_drivers=["AI demand"],
        structural_risks=["supply chain"],
        data_scope="static_asset_profile",
    )


@pytest.mark.asyncio
async def test_get_snapshot_delegates_to_graph_runner(
    mock_graph_runner: AsyncMock,
    snapshot_request: AssetSnapshotRequest,
    snapshot: AssetSnapshot,
) -> None:
    mock_graph_runner.run.return_value = snapshot
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    result = await service.get_snapshot(snapshot_request)

    mock_graph_runner.run.assert_awaited_once_with(snapshot_request)
    assert result is snapshot


@pytest.mark.asyncio
async def test_get_snapshot_returns_graph_runner_result(
    mock_graph_runner: AsyncMock,
    snapshot_request: AssetSnapshotRequest,
    snapshot: AssetSnapshot,
) -> None:
    mock_graph_runner.run.return_value = snapshot
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    result = await service.get_snapshot(snapshot_request)

    assert result == snapshot


@pytest.mark.asyncio
async def test_get_snapshot_propagates_runner_exception(
    mock_graph_runner: AsyncMock,
    snapshot_request: AssetSnapshotRequest,
) -> None:
    mock_graph_runner.run.side_effect = RuntimeError("graph failed")
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    with pytest.raises(RuntimeError, match="graph failed"):
        await service.get_snapshot(snapshot_request)
