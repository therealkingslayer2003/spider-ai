from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.llm.prompts.company_peer_projection import PeerContextMode

ReviewStatus = Literal["pending_manual_review", "approved", "rejected"]
Provenance = Literal[
    "synthetic_ai_generated",
    "human",
    "production_regression",
]
CaseKind = Literal["normal", "fallback", "contrast", "adversarial"]
EntityKind = Literal["real", "fictional"]
FixtureDataType = Literal["stable_qualitative", "synthetic", "mixed", "none"]


class EvalCaseMetadata(BaseModel):
    category: str
    archetype: str
    case_kind: CaseKind
    entity_kind: EntityKind
    provenance: Provenance
    review_status: ReviewStatus
    fixture_data_type: FixtureDataType
    flags: list[str] = Field(default_factory=list)
    notes: str | None = None


class EvalExpectations(BaseModel):
    business_model_concepts: list[str] = Field(default_factory=list)
    structural_driver_themes: list[str] = Field(default_factory=list)
    structural_risk_themes: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    require_company_specificity: bool = True
    require_structural_risks: bool = True
    require_mechanism_explanation: bool = True
    enforce_supplied_peers_only: bool = False
    peer_relationship_guidance: list[str] = Field(default_factory=list)


class StockSnapshotEvalCase(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]+$")
    metadata: EvalCaseMetadata
    request: AssetSnapshotRequest
    profile_fixture: AssetProfileContext | None = None
    peers_fixture: CompanyPeersContext | None = None
    fundamentals_fixture: CompanyFundamentalsContext | None = None
    expectations: EvalExpectations

    @model_validator(mode="after")
    def validate_fixture_alignment(self) -> "StockSnapshotEvalCase":
        if self.request.asset_type is not AssetType.STOCK:
            raise ValueError("Stock Snapshot eval cases must use asset_type=stock")

        expected_asset = self.request.asset.upper()
        fixtures = (
            self.profile_fixture,
            self.peers_fixture,
            self.fundamentals_fixture,
        )
        for fixture in fixtures:
            if fixture is not None and fixture.asset.upper() != expected_asset:
                raise ValueError(
                    f"Fixture asset {fixture.asset!r} does not match "
                    f"request asset {expected_asset!r}"
                )

        if self.profile_fixture is None:
            if self.peers_fixture is not None and self.peers_fixture.peers:
                raise ValueError("Peer fixtures require a profile fixture")
            if self.fundamentals_fixture is not None and any(
                value is not None
                for value in (
                    self.fundamentals_fixture.revenue,
                    self.fundamentals_fixture.revenue_growth,
                    self.fundamentals_fixture.operating_margin,
                    self.fundamentals_fixture.debt_to_equity_ratio,
                )
            ):
                raise ValueError("Financial fixtures require a profile fixture")

        peers = self.peers_fixture.peers if self.peers_fixture else []
        for peer in peers:
            if peer.profile is not None and (
                not peer.ticker
                or peer.profile.asset.upper() != peer.ticker.upper()
                or peer.profile.asset_type is not AssetType.STOCK
            ):
                raise ValueError(
                    "Peer profile must match its candidate ticker and stock type"
                )

        return self


class EvalMetricResult(BaseModel):
    metric: str
    score: float
    passed: bool
    reason: str | None = None
    failure_labels: list[str] = Field(default_factory=list)


class JudgeEvidence(BaseModel):
    field_path: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=600)


class JudgeResult(BaseModel):
    score: Literal[0, 1, 2]
    reason: str
    evidence: list[JudgeEvidence] = Field(min_length=1)


class SemanticMetricResult(BaseModel):
    metric: str
    score: Literal[0, 1, 2]
    reason: str
    evidence: list[JudgeEvidence] = Field(min_length=1, max_length=3)
    failure_labels: list[str] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    case_id: str
    category: str
    review_status: ReviewStatus
    output: StockAssetSnapshot | None = None
    deterministic_metrics: list[EvalMetricResult] = Field(default_factory=list)
    semantic_metrics: list[SemanticMetricResult] = Field(default_factory=list)
    semantic_metrics_expected: int = Field(default=0, ge=0)
    failure_labels: list[str] = Field(default_factory=list)
    latency_seconds: float
    generation_latency_seconds: float | None = None
    prompt_measurements: "PromptMeasurements | None" = None
    error: str | None = None


class PromptMeasurements(BaseModel):
    feature_prompt_chars: int
    static_prompt_chars: int
    dynamic_context_chars: int
    total_prompt_chars: int
    dynamic_context_sha256: str
    prompt_sha256: str


class EvalAggregate(BaseModel):
    deterministic_pass_rates: dict[str, float] = Field(default_factory=dict)
    semantic_averages: dict[str, float] = Field(default_factory=dict)
    weakest_cases: list[str] = Field(default_factory=list)


class StockSnapshotEvalReport(BaseModel):
    dataset_version: str
    git_commit_sha: str | None
    generation_model: str
    judge_model: str | None
    peer_context_mode: PeerContextMode | None = None
    feature_prompt_sha256: str | None = None
    feature_prompt_chars: int | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    case_count: int
    approved_case_count: int
    pending_case_count: int
    unreviewed_dataset_run: bool
    deterministic_only: bool
    total_runtime_seconds: float
    average_latency_seconds: float
    aggregate: EvalAggregate
    cases: list[EvalCaseResult]
