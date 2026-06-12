from pydantic import BaseModel

from app.domain.schemas.asset_snapshot import AssetType


class AssetProfileContext(BaseModel):
    asset: str
    asset_type: AssetType
    name: str | None
    sector: str | None
    industry: str | None
    business_summary: str | None
    exchange: str | None
    currency: str | None
    country: str | None
    provider: str | None