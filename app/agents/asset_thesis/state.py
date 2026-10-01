from datetime import datetime
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field, StringConstraints

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.domain.schemas.asset_thesis import (
    AssetThesisRequest,
    ShortThesisOverview,
    StockAssetThesis,
    ThesisAssetOverview,
    ThesisCatalyst,
    ThesisDataCoverage,
    ThesisRisksAndInvalidation,
    ThesisValuation,
)

ReferenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PreparedArtifactReference(BaseModel):
    artifact_id: ReferenceText
    version: ReferenceText


class PreparedThesisData(BaseModel):
    """Bounded parent-facing result of the data preparation subgraph."""

    filings_index: PreparedArtifactReference | None
    financials: PreparedArtifactReference | None
    quote: PreparedArtifactReference | None
    coverage: ThesisDataCoverage
    data_gaps: list[ReferenceText] = Field(default_factory=list)


class ThesisState(TypedDict, total=False):
    """Per-execution parent state; nodes update only their own fields."""

    request: AssetThesisRequest
    asset: str
    research_id: str
    as_of: datetime
    prepared_data: PreparedThesisData
    asset_overview: ThesisAssetOverview
    valuation: ThesisValuation
    current_catalysts: list[ThesisCatalyst]
    thesis_risks_and_invalidation: ThesisRisksAndInvalidation
    short_thesis_overview: ShortThesisOverview
    final_response: StockAssetThesis | None
    error: str | None


class ThesisDataPreparationState(TypedDict, total=False):
    asset: str
    research_id: str
    as_of: datetime
    prepared_data: PreparedThesisData


class ThesisAssetOverviewState(TypedDict, total=False):
    asset: str
    as_of: datetime
    prepared_data: PreparedThesisData
    snapshot_context: StockAssetSnapshot
    result: ThesisAssetOverview


class ThesisCatalystsState(TypedDict, total=False):
    asset: str
    as_of: datetime
    prepared_data: PreparedThesisData
    result: list[ThesisCatalyst]
