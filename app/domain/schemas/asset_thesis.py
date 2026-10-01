"""Thesis v1 contracts; no research execution or valuation calculations."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.domain.schemas.asset_snapshot import AssetType, StockAssetSnapshot

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Rate = Annotated[
    FiniteFloat, Field(description="Decimal rate or ratio: 0.10 means 10%.")
]
EvidenceIds = Annotated[
    list[Text],
    Field(description="Stable IDs resolving to sources_and_evidence in this response."),
]


class ThesisClaim(BaseModel):
    text: Text
    evidence_ids: EvidenceIds = Field(
        description="May be empty for analytical uncertainty; cite sourced facts."
    )


class ThesisEvidenceSource(BaseModel):
    evidence_id: Text = Field(
        description="Stable source/locator identity, not a list index or random run ID."
    )
    url: Text
    retrieved_at: AwareDatetime


class FilingEvidence(ThesisEvidenceSource):
    kind: Literal["filing"] = "filing"
    form: Literal["10-K", "10-Q", "8-K"]
    accession_number: Text
    filed_on: date
    passage_locator: Text = Field(
        description="Section, HTML anchor, or indexed chunk ID."
    )
    excerpt: Text | None = None
    exhibit: Text | None = Field(
        default=None,
        description="HTML exhibit identifier if applicable; url points to the exhibit.",
    )


class CompanyFactEvidence(ThesisEvidenceSource):
    kind: Literal["company_fact"] = "company_fact"
    accession_number: Text
    filed_on: date
    taxonomy: Text
    concept: Text
    unit: Text = Field(
        description="SEC fact unit, e.g. USD or shares; never scaled millions."
    )
    period_start: date | None = Field(
        default=None, description="Null for instant facts."
    )
    period_end: date
    value: FiniteFloat


class MarketPriceEvidence(ThesisEvidenceSource):
    kind: Literal["market_price"] = "market_price"
    provider: Text
    price_as_of: AwareDatetime = Field(
        description="Quote timestamp, not retrieval time."
    )


ThesisEvidence = Annotated[
    FilingEvidence | CompanyFactEvidence | MarketPriceEvidence,
    Field(discriminator="kind"),
]


class CorpusCoverage(BaseModel):
    status: Literal["complete", "partial", "unavailable", "not_applicable"]
    explanation: Text = Field(
        description="What was covered and why anything is missing or not applicable."
    )
    evidence_ids: EvidenceIds


class ThesisDataCoverage(BaseModel):
    latest_10k: CorpusCoverage
    subsequent_10q: CorpusCoverage = Field(
        description="Latest 10-Q only if filed after the latest 10-K."
    )
    recent_8k_and_html_exhibits: CorpusCoverage
    company_facts: CorpusCoverage
    market_price: CorpusCoverage
    filing_lookback_days: Literal[90] = 90
    complete_financial_years: list[int] = Field(
        max_length=3,
        description="Complete fiscal years covered by Company Facts; target three.",
    )
    limitations: list[Text]


class ShortThesisOverview(BaseModel):
    investment_thesis: ThesisClaim
    valuation_conclusion: Literal[
        "undervalued", "fairly_valued", "overvalued", "uncertain"
    ] = Field(description="Research judgment; uncertain is never an execution status.")
    valuation_rationale: ThesisClaim
    principal_limitations: list[ThesisClaim]


class ThesisAssetOverview(BaseModel):
    business_description: ThesisClaim
    main_economic_drivers: list[ThesisClaim]
    historical_financial_context: list[ThesisClaim]


class FinancialValue(BaseModel):
    value: FiniteFloat | None = Field(
        description="Unscaled value in this field's units; null if unavailable."
    )
    unavailable_reason: Text | None = None

    @model_validator(mode="after")
    def explain_missing_value(self) -> Self:
        if (self.value is None) != (self.unavailable_reason is not None):
            raise ValueError("Provide unavailable_reason exactly when value is null.")
        return self


class ThesisFinancialInput(FinancialValue):
    metric: Literal[
        "revenue",
        "operating_income",
        "income_tax_expense",
        "income_before_tax",
        "depreciation_and_amortization",
        "capital_expenditures",
        "current_assets",
        "current_liabilities",
        "cash_and_cash_equivalents",
        "total_debt",
        "shares_outstanding",
    ]
    period_start: date | None = Field(
        default=None, description="Null for instant facts."
    )
    period_end: date
    unit: Literal["USD", "shares"]
    evidence_ids: EvidenceIds

    @model_validator(mode="after")
    def validate_sourced_input(self) -> Self:
        if self.value is not None and not self.evidence_ids:
            raise ValueError("Available financial inputs require evidence.")
        expected_unit = "shares" if self.metric == "shares_outstanding" else "USD"
        if self.unit != expected_unit:
            raise ValueError(f"{self.metric} must use {expected_unit}.")
        return self


class DcfForecastAssumptions(BaseModel):
    """Explicit yearly assumptions; all rates/ratios use decimals (0.10 = 10%)."""

    year: int = Field(
        ge=1, le=5, description="Forecast year offset from the historical base."
    )
    revenue_growth: Rate = Field(gt=-1)
    operating_margin: Rate
    tax_rate: Rate = Field(ge=0, le=1)
    depreciation_and_amortization_to_revenue: Rate = Field(ge=0)
    capital_expenditures_to_revenue: Rate = Field(ge=0)
    change_in_working_capital_to_revenue: Rate = Field(
        description="Change in operating working capital / revenue; positive uses cash."
    )


class DcfAssumptions(BaseModel):
    """Five forecast years plus terminal growth; annual rates are decimals."""

    discount_rate: Rate = Field(
        gt=0, description="Explicit annual WACC; never auto-estimated."
    )
    terminal_growth_rate: Rate = Field(gt=-1)
    forecast_years: list[DcfForecastAssumptions] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_fixed_dcf(self) -> Self:
        if [year.year for year in self.forecast_years] != [1, 2, 3, 4, 5]:
            raise ValueError("Forecast assumptions must be ordered years 1 through 5.")
        if self.terminal_growth_rate >= self.discount_rate:
            raise ValueError("Terminal growth must be below the discount rate.")
        return self


class DcfAssumptionBasis(BaseModel):
    config_version: Text = Field(
        description="Policy version used to derive forecasts and select DCF parameters."
    )
    values: DcfAssumptions


class ThesisReferencePrice(FinancialValue):
    as_of: AwareDatetime | None = Field(
        description="Quote time; null if no quote is available."
    )
    currency: Literal["USD"] = "USD"
    evidence_ids: EvidenceIds

    @model_validator(mode="after")
    def validate_quote(self) -> Self:
        if self.value is not None:
            if self.value <= 0 or self.as_of is None or not self.evidence_ids:
                raise ValueError(
                    "An available price must be positive, dated, and sourced."
                )
        return self


class DcfResults(BaseModel):
    forecast_fcff: list[FinancialValue] = Field(
        min_length=5,
        max_length=5,
        description="Calculated FCFF in USD, ordered forecast years 1 through 5.",
    )
    terminal_value: FinancialValue = Field(
        description="Terminal enterprise value in USD at the end of forecast year 5."
    )
    enterprise_value: FinancialValue = Field(
        description="Calculated enterprise value, USD."
    )
    equity_value: FinancialValue = Field(description="Calculated equity value, USD.")
    intrinsic_value_per_share: FinancialValue = Field(
        description="Calculated USD per share."
    )
    upside_downside: FinancialValue = Field(
        description="Intrinsic value / reference price - 1; 0.10 means 10% upside."
    )


class DcfSensitivityPoint(BaseModel):
    discount_rate: Rate = Field(gt=0)
    terminal_growth_rate: Rate = Field(gt=-1)
    intrinsic_value_per_share: FinancialValue = Field(
        description="Calculated USD per share; explain null for invalid scenarios."
    )

    @model_validator(mode="after")
    def reject_undefined_terminal_value(self) -> Self:
        if (
            self.terminal_growth_rate >= self.discount_rate
            and self.intrinsic_value_per_share.value is not None
        ):
            raise ValueError("Sensitivity requires null when growth is not below WACC.")
        return self


class ThesisValuation(BaseModel):
    method: Literal["two_stage_fcff_dcf"] = "two_stage_fcff_dcf"
    currency: Literal["USD"] = "USD"
    forecast_years: Literal[5] = 5
    historical_base: list[ThesisFinancialInput] = Field(
        description="Sourced inputs: three fiscal years and balance-sheet bridge."
    )
    assumptions: DcfAssumptionBasis | None
    assumptions_unavailable_reason: Text | None = None
    reference_price: ThesisReferencePrice
    calculated_results: DcfResults
    sensitivity: list[DcfSensitivityPoint]
    limitations: list[ThesisClaim] = Field(
        description="Explain incomplete history, omitted sensitivity, and model limits."
    )

    @model_validator(mode="after")
    def explain_missing_assumptions(self) -> Self:
        if (self.assumptions is None) != (
            self.assumptions_unavailable_reason is not None
        ):
            raise ValueError(
                "Explain missing assumptions exactly when assumptions is null."
            )
        return self


class ThesisCatalyst(BaseModel):
    title: Text
    disclosed_event: Text
    disclosed_on: date
    event_date: date | None = Field(
        default=None, description="Null when not disclosed."
    )
    potential_business_impact: Text
    evidence_ids: EvidenceIds = Field(min_length=1)


class ThesisRisk(BaseModel):
    observable_risk: Text
    uncertainty: Text
    affected_assumptions: list[Text] = Field(min_length=1)
    reassessment_signals: list[Text] = Field(
        min_length=1,
        description="Observable signals; numeric thresholds only when justified.",
    )
    evidence_ids: EvidenceIds


class ThesisRisksAndInvalidation(BaseModel):
    risks: list[ThesisRisk]
    uncertainties: list[ThesisClaim]


class StockAssetThesis(BaseModel):
    asset: Text
    asset_type: Literal[AssetType.STOCK] = AssetType.STOCK
    company_name: Text
    cik: str | None = Field(default=None, pattern=r"^\d{10}$")
    researched_at: AwareDatetime
    data_coverage: ThesisDataCoverage
    short_thesis_overview: ShortThesisOverview
    asset_overview: ThesisAssetOverview
    valuation: ThesisValuation
    current_catalysts: list[ThesisCatalyst]
    thesis_risks_and_invalidation: ThesisRisksAndInvalidation
    sources_and_evidence: list[ThesisEvidence]

    @model_validator(mode="after")
    def validate_evidence_references(self) -> Self:
        ids = [source.evidence_id for source in self.sources_and_evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique.")

        def referenced_ids(value: object) -> set[str]:
            if isinstance(value, BaseModel):
                refs = set(getattr(value, "evidence_ids", []))
                for name in type(value).model_fields:
                    refs.update(referenced_ids(getattr(value, name)))
                return refs
            if isinstance(value, list):
                return {ref for item in value for ref in referenced_ids(item)}
            return set()

        unknown = referenced_ids(self) - set(ids)
        if unknown:
            raise ValueError(f"Unknown evidence IDs: {', '.join(sorted(unknown))}")
        return self


class AssetThesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Stock ticker, symbol, or identifier.",
        examples=["NVDA"],
    )
    asset_type: Literal[AssetType.STOCK] = Field(..., examples=[AssetType.STOCK])
    snapshot_context: StockAssetSnapshot | None = Field(
        default=None,
        description="Optional same-asset background; not required or primary evidence.",
    )

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Asset must not be empty.")
        return cleaned.upper()

    @model_validator(mode="after")
    def validate_snapshot_context(self) -> Self:
        if self.snapshot_context is not None and (
            self.snapshot_context.asset.strip().upper() != self.asset
            or self.snapshot_context.asset_type != AssetType.STOCK
        ):
            raise ValueError(
                "Snapshot context must describe the requested stock asset."
            )
        return self
