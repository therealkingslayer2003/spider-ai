from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator


class AssetType(str, Enum):
    """Supported asset types."""

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    COMMODITY = "commodity"
    INDEX = "index"
    FX = "fx"


class BaseAssetSnapshot(BaseModel):
    asset: str
    asset_type: AssetType
    summary: str
    structural_drivers: list["StructuralDriver"]
    structural_risks: list["StructuralRisk"]
    data_scope: str


class StockAssetSnapshot(BaseAssetSnapshot):
    business_or_asset_profile: str
    market_context: str
    peer_landscape: list["PeerRelationship"] = Field(
        description=(
            "Every identifiable provider-reported peer, with an analytical "
            "relationship classification and qualified economic relevance."
        )
    )


class PeerRelationship(BaseModel):
    ticker: str | None = Field(
        default=None,
        description="Preserve the supplied peer ticker; null only when unavailable.",
    )
    name: str
    peer_type: Literal[
        "direct_competitor", "indirect_competitor", "comparable", "unclear"
    ] = Field(
        description=(
            "Analytical classification, not a provider assertion: direct for "
            "substantial offering/demand overlap, indirect for substitution of "
            "the same economic need, comparable for broad economic similarity "
            "without proven competition, unclear when support is insufficient."
        )
    )
    relationship_area: str = Field(
        description="Specific economic overlap, broader comparability, or uncertainty."
    )
    why_relevant: str = Field(
        description=(
            "One explanation of the supported relationship AND its structural "
            "economic significance for the target company. Use provider evidence "
            "first and reliable stable knowledge second; distinguish competition "
            "from comparability and explain the causal effect or evidence "
            "limitation. Return explanatory prose, not a high/medium/low rating."
        )
    )

def normalize_materiality(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value

Materiality = Annotated[
    Literal["low", "medium", "high"],
    BeforeValidator(normalize_materiality),
]

class StructuralDriver(BaseModel):
    title: str
    explanation: str
    materiality: Materiality


class StructuralRisk(BaseModel):
    title: str
    explanation: str
    materiality: Materiality
    related_entities: list[str] = Field(
        default_factory=list,
        description=(
            "Peer tickers or supplied names materially connected to this specific "
            "risk mechanism, not every peer and not necessarily competitors."
        ),
    )


class AssetSnapshotRequest(BaseModel):
    asset: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description=(
            "Asset ticker, symbol, or identifier. Examples: NVDA, EUR/USD, GOLD, SPY."
        ),
        examples=["NVDA"],
    )
    asset_type: AssetType = Field(
        ...,
        description="Asset class/type.",
        examples=[AssetType.STOCK],
    )

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("Asset must not be empty.")

        return cleaned.upper()
