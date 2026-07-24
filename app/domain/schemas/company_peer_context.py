from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CompanyPeer(BaseModel):
    ticker: str | None = None
    name: str | None = None
    competition_area: str | None = None
    why_competitor: str | None = None
    why_it_matters: str | None = None
    provider: str | None = None


class CompanyPeersContext(BaseModel):
    asset: str
    provider: str
    peers: list[CompanyPeer]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
