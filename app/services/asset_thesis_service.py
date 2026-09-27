from app.core.exceptions import AssetThesisNotImplementedError
from app.domain.schemas.asset_thesis import AssetThesisRequest, StockAssetThesis


class AssetThesisService:
    """Application boundary for future Thesis orchestration.

    Prepare/index shared research data, then independently produce Asset Overview,
    Catalysts, and deterministic DCF results. Combine those results with targeted
    retrieval for Thesis Risks & Invalidation. Finally generate Short Thesis
    Overview, assemble sources, and validate the response. There is no separate
    Risk Discovery stage or mandatory reconciliation/recalculation loop.

    Add the runner dependency here when execution is implemented; the skeleton
    needs no graph, external clients, persistence, or Snapshot execution.
    """

    async def get_thesis(self, request: AssetThesisRequest) -> StockAssetThesis:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )
