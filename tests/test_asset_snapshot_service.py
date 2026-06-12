from unittest.mock import AsyncMock

import pytest

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotMode,
    AssetSnapshotRequest,
    AssetType,
    ShortAssetSnapshot,
)
from app.services.asset_snapshot_service import AssetSnapshotService


@pytest.fixture
def mock_graph_runner() -> AsyncMock:
    runner = AsyncMock()
    return runner


@pytest.fixture
def short_request() -> AssetSnapshotRequest:
    return AssetSnapshotRequest(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        mode=AssetSnapshotMode.SHORT,
    )


@pytest.fixture
def short_snapshot() -> ShortAssetSnapshot:
    return ShortAssetSnapshot(
        mode=AssetSnapshotMode.SHORT,
        asset="NVDA",
        asset_type=AssetType.STOCK,
        summary="NVDA is a GPU manufacturer.",
        market_context="Semiconductor sector.",
        data_scope="static_asset_profile",
    )


# ── delegation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_snapshot_delegates_to_graph_runner(
    mock_graph_runner: AsyncMock,
    short_request: AssetSnapshotRequest,
    short_snapshot: ShortAssetSnapshot,
) -> None:
    mock_graph_runner.run.return_value = short_snapshot
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    result = await service.get_snapshot(short_request)

    mock_graph_runner.run.assert_awaited_once_with(short_request)
    assert result is short_snapshot


@pytest.mark.asyncio
async def test_get_snapshot_returns_graph_runner_result(
    mock_graph_runner: AsyncMock,
    short_request: AssetSnapshotRequest,
    short_snapshot: ShortAssetSnapshot,
) -> None:
    mock_graph_runner.run.return_value = short_snapshot
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    result = await service.get_snapshot(short_request)

    assert result == short_snapshot


@pytest.mark.asyncio
async def test_get_snapshot_propagates_runner_exception(
    mock_graph_runner: AsyncMock,
    short_request: AssetSnapshotRequest,
) -> None:
    mock_graph_runner.run.side_effect = RuntimeError("graph failed")
    service = AssetSnapshotService(graph_runner=mock_graph_runner)

    with pytest.raises(RuntimeError, match="graph failed"):
        await service.get_snapshot(short_request)
