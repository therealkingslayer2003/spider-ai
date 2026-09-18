from fastapi.testclient import TestClient

from app.api.dependencies import get_asset_snapshot_service
from app.core.exceptions import ServiceError, UnsupportedAssetTypeError
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)
from app.main import create_app


class FailingAssetSnapshotService:
    async def get_snapshot(self, request: AssetSnapshotRequest) -> None:
        raise ServiceError("Asset snapshot generation failed. Please try again.")


class UnsupportedAssetSnapshotService:
    async def get_snapshot(self, request: AssetSnapshotRequest) -> None:
        raise UnsupportedAssetTypeError(AssetType.ETF)


class SuccessfulAssetSnapshotService:
    def __init__(self, snapshot: StockAssetSnapshot) -> None:
        self._snapshot = snapshot

    async def get_snapshot(self, request: AssetSnapshotRequest) -> StockAssetSnapshot:
        return self._snapshot


def test_asset_snapshot_endpoint_returns_controlled_error_on_generation_failure() -> (
    None
):
    app = create_app()
    app.dependency_overrides[get_asset_snapshot_service] = lambda: (
        FailingAssetSnapshotService()
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/asset/snapshot",
            json={"asset": "GOOGL", "asset_type": "stock"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Asset snapshot generation failed. Please try again."
    }


def test_asset_snapshot_endpoint_returns_controlled_error_for_unsupported_type() -> (
    None
):
    app = create_app()
    app.dependency_overrides[get_asset_snapshot_service] = lambda: (
        UnsupportedAssetSnapshotService()
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/asset/snapshot",
            json={"asset": "SPY", "asset_type": "etf"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "asset_type=etf" in response.json()["detail"]


def test_asset_snapshot_endpoint_response_does_not_expose_persistence_metadata() -> (
    None
):
    snapshot = StockAssetSnapshot.model_validate(
        {
            "asset": "NVDA",
            "asset_type": "stock",
            "summary": "GPU platform company.",
            "business_or_asset_profile": "Designs accelerated computing products.",
            "market_context": "Semiconductor industry.",
            "peer_landscape": [],
            "structural_drivers": [],
            "structural_risks": [],
            "data_scope": "profile_only",
        }
    )
    app = create_app()
    app.dependency_overrides[get_asset_snapshot_service] = lambda: (
        SuccessfulAssetSnapshotService(snapshot)
    )

    try:
        response = TestClient(app).post(
            "/api/v1/asset/snapshot",
            json={"asset": "NVDA", "asset_type": "stock"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == snapshot.model_dump(mode="json")
    assert "research_artifact_id" not in response.json()
    assert "evidence" not in response.json()
    assert "rationale" not in response.json()
