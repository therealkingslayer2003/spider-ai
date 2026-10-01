from app.agents.asset_thesis.runner import AssetThesisGraphRunner
from app.domain.schemas.asset_thesis import AssetThesisRequest, StockAssetThesis


class AssetThesisService:
    """Application boundary for future Thesis orchestration.

    Prepare/index shared research data, then independently produce Asset Overview,
    Catalysts, and deterministic DCF results. Combine those results with targeted
    retrieval for Thesis Risks & Invalidation. Finally generate Short Thesis
    Overview, assemble sources, and validate the response. There is no separate
    Risk Discovery stage or mandatory reconciliation/recalculation loop.

    The runner provides the parent graph boundary. Research execution remains
    unimplemented until its nodes are added.
    """

    def __init__(self, graph_runner: AssetThesisGraphRunner) -> None:
        self.graph_runner = graph_runner

    async def get_thesis(self, request: AssetThesisRequest) -> StockAssetThesis:
        return await self.graph_runner.run(request)
