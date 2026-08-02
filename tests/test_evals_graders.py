import json

import pytest

from app.domain.schemas.asset_snapshot import CompetitivePeer, StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.graders import (
    DataScopeGrader,
    ForbiddenClaimGrader,
    RequiredFieldGrader,
    SafetyGrader,
    SchemaValidityGrader,
    UnsupportedCompetitorGrader,
    UnsupportedNumericClaimGrader,
)
from evals.asset_snapshot.judge import JudgeEvaluationError, LLMJudgeGrader


def make_snapshot(
    *,
    asset: str = "SGRD",
    data_scope: str = "profile_with_financial_signals",
    profile_text: str = "Subscription software supports recurring revenue.",
    risk_text: str = "Churn can reduce recurring revenue and pressure margins.",
) -> StockAssetSnapshot:
    return StockAssetSnapshot.model_validate(
        {
            "asset": asset,
            "asset_type": "stock",
            "summary": "A structurally focused company overview.",
            "business_or_asset_profile": profile_text,
            "market_context": "The company operates in enterprise software.",
            "competitive_landscape": [],
            "structural_drivers": [
                {
                    "title": "Retention",
                    "explanation": "Retention supports recurring revenue.",
                    "materiality": "high",
                }
            ],
            "structural_risks": [
                {
                    "title": "Churn",
                    "explanation": risk_text,
                    "materiality": "high",
                    "related_competitors": [],
                }
            ],
            "data_scope": data_scope,
        }
    )


def financial_case():
    return next(
        case for case in load_dataset() if case.id == "profile_financials_no_peers_001"
    )


def test_schema_validity_grader_accepts_production_snapshot() -> None:
    result = SchemaValidityGrader().grade(financial_case(), make_snapshot())

    assert result.passed is True


def test_schema_validity_grader_rejects_invalid_output() -> None:
    result = SchemaValidityGrader().grade(financial_case(), {"asset": "SGRD"})

    assert result.passed is False
    assert "schema_failure" in result.failure_labels


def test_safety_grader_rejects_recommendation_language() -> None:
    snapshot = make_snapshot(profile_text="Investors should buy this stock.")

    result = SafetyGrader().grade(financial_case(), snapshot)

    assert result.passed is False
    assert "safety_violation" in result.failure_labels


def test_required_field_grader_rejects_empty_risks() -> None:
    snapshot = make_snapshot()
    snapshot.structural_risks = []

    result = RequiredFieldGrader().grade(financial_case(), snapshot)

    assert result.passed is False


def test_data_scope_grader_rejects_wrong_scope() -> None:
    snapshot = make_snapshot(data_scope="profile_only")

    result = DataScopeGrader().grade(financial_case(), snapshot)

    assert result.passed is False
    assert "profile_with_financial_signals" in (result.reason or "")


def test_unsupported_numeric_claim_grader_rejects_wrong_metric() -> None:
    snapshot = make_snapshot(risk_text="Operating margin is 18%.")

    result = UnsupportedNumericClaimGrader().grade(financial_case(), snapshot)

    assert result.passed is False
    assert "hallucinated_metric" in result.failure_labels


def test_unsupported_numeric_claim_grader_accepts_scaled_currency_metric() -> None:
    snapshot = make_snapshot(risk_text="Market cap is $4 billion.")

    result = UnsupportedNumericClaimGrader().grade(financial_case(), snapshot)

    assert result.passed is True


def test_forbidden_claim_grader_normalizes_phrase() -> None:
    snapshot = make_snapshot(risk_text="The operating-margin is 30 percent.")

    result = ForbiddenClaimGrader().grade(financial_case(), snapshot)

    assert result.passed is False


def test_unsupported_competitor_grader_rejects_invented_peer() -> None:
    case = next(
        case for case in load_dataset() if case.id == "novapay_peers_missing_001"
    )
    snapshot = make_snapshot(asset=case.request.asset, data_scope="profile_only")
    snapshot.competitive_landscape = [
        CompetitivePeer(
            ticker="FAKE",
            name="Fake Peer",
            competition_area="payments",
            why_competitor="Competes",
            why_it_matters="Pressures pricing",
        )
    ]

    result = UnsupportedCompetitorGrader().grade(case, snapshot)

    assert result.passed is False
    assert "unsupported_competitor" in result.failure_labels


class FakeJudgeClient(BaseChatModelClient):
    def __init__(self, output: str) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def generate(self, message: str) -> str:
        self.prompts.append(message)
        return self.output


@pytest.mark.asyncio
async def test_semantic_judge_parses_structured_result() -> None:
    client = FakeJudgeClient(json.dumps({"score": 2, "reason": "Grounded."}))
    grader = LLMJudgeGrader(
        metric="groundedness",
        rubric="0 bad, 1 partial, 2 grounded",
        failure_label="grounding_failure",
        client=client,
    )

    result = await grader.grade(financial_case(), make_snapshot())

    assert result.score == 2
    assert "supplied request" in client.prompts[0]


@pytest.mark.asyncio
async def test_semantic_judge_invalid_output_is_controlled() -> None:
    grader = LLMJudgeGrader(
        metric="groundedness",
        rubric="0 bad, 1 partial, 2 grounded",
        failure_label="grounding_failure",
        client=FakeJudgeClient("not-json"),
    )

    with pytest.raises(JudgeEvaluationError, match="groundedness"):
        await grader.grade(financial_case(), make_snapshot())
