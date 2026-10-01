from typing import NotRequired, TypedDict

from app.domain.schemas.asset_thesis import AssetThesisRequest, StockAssetThesis


class ThesisState(TypedDict):
    """Parent execution state; phase 2 will add the intermediate results."""

    request: AssetThesisRequest
    final_response: NotRequired[StockAssetThesis | None]
    error: NotRequired[str | None]
