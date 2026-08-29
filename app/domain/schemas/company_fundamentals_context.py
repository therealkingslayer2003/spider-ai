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
    debt_to_equity_ratio: float | None = Field(
        default=None,
        description=(
            "Normalized debt-to-equity ratio expressed as a multiple, where 2.0 "
            "means debt is approximately 2x shareholders' equity. Used as "
            "supporting evidence about capital structure and financing dependence; "
            "interpretation must remain business- and sector-aware."
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
