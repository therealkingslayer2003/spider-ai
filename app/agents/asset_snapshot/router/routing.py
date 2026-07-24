from app.agents.asset_snapshot.router.state import AssetSnapshotRouterState
from app.core.exceptions import UnsupportedAssetTypeError
from app.domain.schemas.asset_snapshot import AssetType


def route_asset_type(
    state: AssetSnapshotRouterState,
) -> AssetSnapshotRouterState:
    return {"selected_asset_type": state["request"].asset_type}


def selected_asset_type_route(state: AssetSnapshotRouterState) -> str:
    if state.get("selected_asset_type") is AssetType.STOCK:
        return "stock"
    return "unsupported"


async def unsupported_asset_type_node(
    state: AssetSnapshotRouterState,
) -> AssetSnapshotRouterState:
    raise UnsupportedAssetTypeError(state["request"].asset_type)


async def finalize_router_result(
    state: AssetSnapshotRouterState,
) -> AssetSnapshotRouterState:
    return {
        "validated_output": state.get("validated_output"),
        "error": state.get("error"),
    }
