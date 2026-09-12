from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.domain.schemas.asset_profile_context import AssetProfileContext


class CompanyPeer(BaseModel):
    ticker: str | None = None
    name: str | None = None
    profile: AssetProfileContext | None = Field(
        default=None,
        description=(
            "Retrieved candidate company facts, "
            "not a confirmed competitive relationship."
        ),
    )
    provider: str | None = None


class CompanyPeersContext(BaseModel):
    asset: str
    provider: str
    peers: list[CompanyPeer]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
