from unittest.mock import AsyncMock

import pytest

from app.domain.schemas.asset_snapshot import (
    AssetSnapshot,
    AssetSnapshotRequest,
    AssetType,
    CompetitivePeer,
    StructuralDriver,
    StructuralRisk,
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
        competitive_landscape=[
            CompetitivePeer(
                ticker="AMD",
                name="Advanced Micro Devices",
                competition_area="AI accelerators",
                why_competitor="AMD competes in GPUs.",
                why_it_matters="It pressures pricing and share.",
            )
        ],
        structural_drivers=[
            StructuralDriver(
                title="AI demand",
                explanation="AI workloads support GPU demand.",
                materiality="high",
            )
        ],
        structural_risks=[
            StructuralRisk(
                title="Supply chain concentration",
                explanation="Foundry constraints can affect availability.",
                materiality="high",
                related_competitors=["AMD"],
            )
        ],
        data_scope="provider_profile_with_static_sector_and_peer_context",
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
