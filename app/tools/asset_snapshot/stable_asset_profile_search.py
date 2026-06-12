from app.agents.asset_snapshot.state import AssetSnapshotState
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType


class StableAssetProfileSearchTool:
    async def run(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        return AssetProfileContext(
            asset=asset,
            asset_type=asset_type,
            name="Mastercard Incorporated",
            sector="Financials",
            industry="Financial Services",
            business_summary="Mastercard Incorporated is a global payment technology company that processes transactions across credit, debit, and prepaid cards.",
            exchange="NYSE",
            currency="USD",
            country="USA",
            provider="StableAssetProfileSearchTool",
        )