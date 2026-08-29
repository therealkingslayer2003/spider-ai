from datetime import UTC, date, datetime

from pydantic import BaseModel, Field


class CompanyFundamentalsContext(BaseModel):
    asset: str
    provider: str
    revenue: float | None = Field(
        default=None,
        description=(
            "Provider-reported company revenue used as business scale context."
        ),
    )
    revenue_growth: float | None = Field(
        default=None,
        description=(
            "Provider-reported revenue growth used as evidence about growth or "
            "maturity, not as an investment signal."
        ),
    )
    operating_margin: float | None = Field(
        default=None,
        description=(
            "Operating profitability evidence interpreted with the business model."
        ),
    )
    debt_to_equity: float | None = Field(
        default=None,
        description=(
            "Capital-structure evidence requiring company- and sector-aware "
            "interpretation."
        ),
    )
    financial_currency: str | None = Field(
        default=None,
        description="Provider-reported currency for the financial figures.",
    )
    last_fiscal_year_end: date | None = Field(
        default=None,
        description="Provider-reported latest fiscal-year-end date.",
    )
    most_recent_quarter: date | None = Field(
        default=None,
        description="Provider-reported most-recent-quarter date.",
    )
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
