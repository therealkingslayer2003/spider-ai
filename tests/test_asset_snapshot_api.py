from fastapi.testclient import TestClient

from app.api.dependencies import get_asset_snapshot_service
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest
from app.main import create_app


class FailingAssetSnapshotService:
    async def get_snapshot(self, request: AssetSnapshotRequest) -> None:
        raise ServiceError("Asset snapshot generation failed. Please try again.")


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
