from enum import Enum

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
    structural_drivers: list[str]
    structural_risks: list[str]
    data_scope: str


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
