from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CompanyFundamentalsContext(BaseModel):
    asset: str
    provider: str
    market_cap: float | None = None
    operating_margin: float | None = None
    debt_to_equity: float | None = None
    revenue: float | None = None
    revenue_growth: float | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
