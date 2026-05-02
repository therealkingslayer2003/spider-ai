from enum import Enum

from pydantic import BaseModel


class Mode(str, Enum):
    """Position mode for asset snapshot."""

    SHORT = "short"
    LONG = "long"


class AssetType(str, Enum):
    """Supported asset types."""

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    COMMODITY = "commodity"
    INDEX = "index"
    FX = "fx"


class ShortAssetSnapshot(BaseModel):
    mode: Mode
    asset: str
    asset_type: AssetType
    summary: str
    market_context: str
    data_scope: str


class LongAssetSnapshot(ShortAssetSnapshot):
    business_or_asset_profile: str
    structural_drivers: list[str]
    structural_risks: list[str]