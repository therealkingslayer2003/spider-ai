import json

import pytest

from app.domain.schemas.asset_snapshot import CompetitivePeer, StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.graders import (
    CompetitiveEvidenceGrader,
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


@pytest.mark.parametrize(
    ("case_id", "tickers", "placeholder", "passed"),
    [
        ("amzn_peer_profiles_001", [], False, False),
        ("amzn_peer_profiles_001", ["ETSY"], False, False),
        ("amzn_peer_profiles_001", ["ETSY", "CASY"], True, False),
        ("amzn_peer_profiles_001", ["ETSY", "CASY"], False, True),
        ("ma_sparse_peers_001", [], False, False),
        ("ma_sparse_peers_001", ["V"], False, False),
        ("ma_sparse_peers_001", ["V", "AXP"], False, True),
        ("cloudx_unrelated_peer_001", [], False, False),
        ("cloudx_unrelated_peer_001", ["FARM"], False, True),
        ("profile_only_saas_001", [], False, True),
    ],
)
def test_competitive_evidence_requires_peer_acknowledgment_not_proven_competition(
    case_id, tickers, placeholder, passed
):
    case = next(c for c in load_dataset() if c.id == case_id)
    snapshot = make_snapshot()
    snapshot.competitive_landscape = [
        CompetitivePeer(
            ticker=ticker,
            name=ticker,
            competition_area="Provider-reported peer; specific overlap is unconfirmed.",
            why_competitor="Not available"
            if placeholder
            else "Provider-reported peer; direct competition is unconfirmed.",
            why_it_matters="Specific impact is not established by supplied evidence.",
        )
        for ticker in tickers
    ]

    result = CompetitiveEvidenceGrader().grade(case, snapshot)
    assert result.passed is passed
    assert bool(result.failure_labels) is not passed


@pytest.mark.parametrize(
    (
        "supplied_ticker",
        "supplied_name",
        "generated_ticker",
        "generated_name",
        "passed",
    ),
    [
        ("V", "Visa", "v", "Visa", True),
        ("V", "Visa", None, "VISA", True),
        (None, "Visa, Inc.", None, "Visa Inc", True),
        ("V", None, "V", "V", True),
        ("V", "Visa", "OTHER", "Visa", False),
        (None, "Visa", None, "Another Company", False),
    ],
)
def test_peer_coverage_matches_identity_without_inspecting_profiles(
    supplied_ticker,
    supplied_name,
    generated_ticker,
    generated_name,
    passed,
):
    from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext

    case = financial_case().model_copy(deep=True)
    case.peers_fixture = CompanyPeersContext(
        asset=case.request.asset,
        provider="frozen_eval",
        peers=[CompanyPeer(ticker=supplied_ticker, name=supplied_name)],
    )
    snapshot = make_snapshot()
    snapshot.competitive_landscape = [
        CompetitivePeer(
            ticker=generated_ticker,
            name=generated_name,
            competition_area="Provider-reported peer; direct overlap unconfirmed.",
            why_competitor="Included by the provider; no peer profile was supplied.",
            why_it_matters="Specific impact cannot be assessed from supplied facts.",
        )
    ]
    assert CompetitiveEvidenceGrader().grade(case, snapshot).passed is passed


def test_missing_provider_peer_is_reported_by_identity():
    case = next(c for c in load_dataset() if c.id == "ma_sparse_peers_001")
    result = CompetitiveEvidenceGrader().grade(case, make_snapshot())
    assert result.reason == "Missing provider-reported peers: ['AXP', 'V']"


def test_competitive_evidence_grader_rejects_invalid_schema():
    assert not CompetitiveEvidenceGrader().grade(financial_case(), {}).passed


def test_judge_distinguishes_peer_facts_from_generated_inferences():
    case = next(c for c in load_dataset() if c.id == "amzn_peer_profiles_001")
    from unittest.mock import AsyncMock

    grader = LLMJudgeGrader(
        "groundedness", "Grounded analysis", "grounding_failure", AsyncMock()
    )
    prompt = grader._build_prompt(case, make_snapshot())
    assert "Every distinct identifiable supplied peer should be acknowledged" in prompt
    assert "This is substantive" in prompt
    assert "not when enrichment fails" in prompt
    assert "unsupported claims of direct competition" in prompt
    assert "Do not require verbatim explanations in fixtures" in prompt
    assert "independent sellers" in prompt


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


def test_unsupported_numeric_claim_grader_accepts_scaled_revenue_metric() -> None:
    snapshot = make_snapshot(risk_text="Revenue is $900 million.")

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
    evidence_quote = "Subscription software supports recurring revenue."
    client = FakeJudgeClient(
        json.dumps(
            {
                "score": 2,
                "reason": "Grounded.",
                "evidence": [
                    {
                        "field_path": "business_or_asset_profile",
                        "quote": evidence_quote,
                    }
                ],
            }
        )
    )
    grader = LLMJudgeGrader(
        metric="groundedness",
        rubric="0 bad, 1 partial, 2 grounded",
        failure_label="grounding_failure",
        client=client,
    )

    result = await grader.grade(financial_case(), make_snapshot())

    assert result.score == 2
    assert result.evidence[0].field_path == "business_or_asset_profile"
    assert result.evidence[0].quote == evidence_quote
    assert "supplied request" in client.prompts[0]
    assert "literal,\ncontiguous excerpt" in client.prompts[0]


@pytest.mark.asyncio
async def test_semantic_judge_failure_label_has_exact_snapshot_evidence() -> None:
    evidence_quote = "Churn can reduce recurring revenue and pressure margins."
    grader = LLMJudgeGrader(
        metric="risk_mechanism_quality",
        rubric="0 bad, 1 partial, 2 clear mechanism",
        failure_label="weak_risk_mechanism",
        client=FakeJudgeClient(
            json.dumps(
                {
                    "score": 1,
                    "reason": "The mechanism is incomplete.",
                    "evidence": [
                        {
                            "field_path": "structural_risks[0].explanation",
                            "quote": evidence_quote,
                        }
                    ],
                }
            )
        ),
    )

    result = await grader.grade(financial_case(), make_snapshot())

    assert result.failure_labels == ["weak_risk_mechanism"]
    assert result.evidence[0].quote == evidence_quote


@pytest.mark.asyncio
async def test_semantic_judge_caps_excess_valid_evidence() -> None:
    grader = LLMJudgeGrader(
        metric="risk_mechanism_quality",
        rubric="0 bad, 1 partial, 2 clear mechanism",
        failure_label="weak_risk_mechanism",
        client=FakeJudgeClient(
            json.dumps(
                {
                    "score": 2,
                    "reason": "Multiple passages support the score.",
                    "evidence": [
                        {
                            "field_path": "summary",
                            "quote": "A structurally focused company overview.",
                        },
                        {
                            "field_path": "business_or_asset_profile",
                            "quote": (
                                "Subscription software supports recurring revenue."
                            ),
                        },
                        {
                            "field_path": "market_context",
                            "quote": "enterprise software",
                        },
                        {
                            "field_path": "structural_risks[0].explanation",
                            "quote": "Churn can reduce recurring revenue",
                        },
                    ],
                }
            )
        ),
    )

    result = await grader.grade(financial_case(), make_snapshot())

    assert len(result.evidence) == 3
    assert [evidence.field_path for evidence in result.evidence] == [
        "summary",
        "business_or_asset_profile",
        "market_context",
    ]


@pytest.mark.asyncio
async def test_semantic_judge_accepts_literal_evidence_from_list_field() -> None:
    snapshot = make_snapshot()
    snapshot.structural_risks[0].related_competitors = ["ALPHA", "BETA"]
    grader = LLMJudgeGrader(
        metric="groundedness",
        rubric="0 bad, 1 partial, 2 grounded",
        failure_label="grounding_failure",
        client=FakeJudgeClient(
            json.dumps(
                {
                    "score": 2,
                    "reason": "The named competitor is present in the snapshot.",
                    "evidence": [
                        {
                            "field_path": ("structural_risks[0].related_competitors"),
                            "quote": "ALPHA",
                        }
                    ],
                }
            )
        ),
    )

    result = await grader.grade(financial_case(), snapshot)

    assert result.evidence[0].field_path == ("structural_risks[0].related_competitors")
    assert result.evidence[0].quote == "ALPHA"


@pytest.mark.asyncio
async def test_semantic_judge_rejects_fabricated_evidence() -> None:
    grader = LLMJudgeGrader(
        metric="groundedness",
        rubric="0 bad, 1 partial, 2 grounded",
        failure_label="grounding_failure",
        client=FakeJudgeClient(
            json.dumps(
                {
                    "score": 0,
                    "reason": "Unsupported claim.",
                    "evidence": [
                        {
                            "field_path": "summary",
                            "quote": "This sentence is not in the snapshot.",
                        }
                    ],
                }
            )
        ),
    )

    with pytest.raises(JudgeEvaluationError, match="not present"):
        await grader.grade(financial_case(), make_snapshot())


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
