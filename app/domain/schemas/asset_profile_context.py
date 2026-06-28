from datetime import UTC, datetime

from pydantic import BaseModel, Field

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
    website: str | None = None
    provider: str = "unknown"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
