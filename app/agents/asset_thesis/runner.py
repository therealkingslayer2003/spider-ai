from app.agents.asset_thesis.graph import AssetThesisGraph
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_thesis import AssetThesisRequest, StockAssetThesis


class AssetThesisGraphRunner:
    def __init__(self, thesis_graph: AssetThesisGraph) -> None:
        self._thesis_graph = thesis_graph

    async def run(self, request: AssetThesisRequest) -> StockAssetThesis:
        final_state = await self._thesis_graph.ainvoke({"request": request})
        final_response = final_state.get("final_response")
        if final_response is None:
            raise ServiceError("Asset thesis generation failed. Please try again.")
        return final_response