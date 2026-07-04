from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AssetType(str, Enum):  # noqa: UP042
    """Supported asset types."""

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    COMMODITY = "commodity"
    INDEX = "index"
    FX = "fx"


class AssetSnapshot(BaseModel):
    asset: str
    asset_type: AssetType
    summary: str
    market_context: str
    business_or_asset_profile: str
    competitive_landscape: list["CompetitivePeer"]
    structural_drivers: list["StructuralDriver"]
    structural_risks: list["StructuralRisk"]
    data_scope: str


class CompetitivePeer(BaseModel):
    ticker: str | None = None
    name: str
    competition_area: str
    why_competitor: str
    why_it_matters: str


class StructuralDriver(BaseModel):
    title: str
    explanation: str
    materiality: Literal["low", "medium", "high"]

    @field_validator("materiality", mode="before")
    @classmethod
    def normalize_materiality(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class StructuralRisk(BaseModel):
    title: str
    explanation: str
    materiality: Literal["low", "medium", "high"]
    related_competitors: list[str] = Field(default_factory=list)

    @field_validator("materiality", mode="before")
    @classmethod
    def normalize_materiality(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


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
