import json
from string import Formatter

import pytest

from app.domain.schemas.asset_snapshot import PeerRelationship, StockAssetSnapshot
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.original_feature_prompt import (
    ASSET_SNAPSHOT_PROMPT as ORIGINAL_FEATURE_PROMPT,
)
from evals.asset_snapshot.prompt_measurements import (
    MeasuredSnapshotPromptBuilder,
)


def test_verbose_reference_and_compressed_prompt_use_same_current_contract():
    assert "## PRODUCT PURPOSE" in ORIGINAL_FEATURE_PROMPT
    assert len(ASSET_SNAPSHOT_PROMPT) < len(ORIGINAL_FEATURE_PROMPT)
    for template in (ORIGINAL_FEATURE_PROMPT, ASSET_SNAPSHOT_PROMPT):
        assert "peer_type must be exactly one of" in template
        assert "Stable model knowledge MAY" in template
        assert "never override" in template


def test_output_contract_and_placeholders_are_unchanged():
    examples = []
    schema_templates = []
    for template in (ORIGINAL_FEATURE_PROMPT, ASSET_SNAPSHOT_PROMPT):
        assert {field for _, field, _, _ in Formatter().parse(template) if field} == {
            "asset",
            "asset_type",
            "data_scope",
        }
        schema = template.split("## REQUIRED JSON SCHEMA\n\n")[1].split("\n\n")[0]
        schema_templates.append(schema)
        examples.append(
            json.loads(
                schema.format(
                    asset="AAPL", asset_type="stock", data_scope="profile_only"
                )
            )
        )
    assert examples[0] == examples[1]
    assert schema_templates[0] == schema_templates[1]
    assert set(examples[0]) == set(StockAssetSnapshot.model_fields)
    assert set(examples[0]["peer_landscape"][0]) == set(PeerRelationship.model_fields)


@pytest.mark.parametrize("template", [ASSET_SNAPSHOT_PROMPT, ORIGINAL_FEATURE_PROMPT])
def test_merged_explanation_preserves_both_requirements_and_reference_boundary(
    template,
):
    prompt = " ".join(template.split())
    assert "WHY the relationship exists AND HOW it could structurally matter" in prompt
    assert "one coherent explanation" in prompt
    assert "never only a high/medium/low rating" in prompt
    assert (
        "mentioned in prose is not eligible unless it is also a supplied peer" in prompt
    )
    assert '"why_related"' not in template
    assert '"economic_relevance"' not in template


@pytest.mark.parametrize(
    "requirements",
    [
        (
            "persistent characteristics",
            "not temporary events",
            "current investment theses",
            "price forecasts",
        ),
        (
            "business model -> economic engines and dependencies "
            "-> financial characterization",
            "competitive pressures -> structural drivers/risks "
            "-> causal economic consequences",
        ),
        (
            "target company profile > supplied peer profile/context "
            "> supplied financial fundamentals > stable model knowledge",
            "Provider evidence takes precedence over memory",
        ),
        (
            "Provider evidence is the primary source of truth",
            "Stable model knowledge MAY supplement it",
            "never guess missing values",
            "not positive/negative evidence",
            "Use partial evidence",
        ),
        (
            "No margin -> no financial profitability claim",
            "no debt-to-equity ratio -> no leverage claim",
            "no revenue growth -> no fast/declining growth",
        ),
        (
            "When the company profile is unavailable, data_scope remains",
            '"model_static_knowledge_fallback"',
            "Model memory must not introduce unsupplied numerical claims",
            "never authorizes inventing peer identities",
        ),
        (
            "name identifies the company only",
            "sector is broad context",
            "insufficient for company-specific risks",
            "industry refines",
            "not identical firm economics",
        ),
        (
            "exchange is identification/listing context only",
            "currency is trading/listing context, "
            "not revenue exposure or reporting currency",
            "country needs a defensible business link",
            "it alone proves no risk",
        ),
        (
            "business_summary is the primary source",
            "customers/users/ merchants",
            "supported monetization",
            "Translate facts into economics",
        ),
        (
            "EVERY distinct identifiable supplied peer",
            "failed/partial enrichment and different businesses",
            "Preserve supplied tickers/names",
            "ticker-only -> use ticker as name",
            "not eligibility",
        ),
        (
            "Provider-reported peer != proven direct competitor",
            "peer_type must be exactly one of",
            "analytical OUTPUT fields",
            "not expected provider fields",
        ),
        (
            "relationship_area: specific supported",
            "why_relevant: one coherent explanation",
            "WHY the relationship exists AND HOW it could structurally matter",
            "Preserve both the relationship reasoning and economic significance",
            "Never invent measured impacts, market shares, dominance, or facts",
        ),
        (
            "none follows from peer membership",
            "limits explanation, not inclusion",
            'qualify absent overlap, not a "missing profile"',
            "ONLY without identifiable supplied peers",
            'bare "Not available" is not',
        ),
        (
            "quantitative supporting evidence, not standalone drivers/risks",
            "business model and an actual economic mechanism",
            "revenue: scale context only",
            "Large does not automatically mean safe",
        ),
        (
            "revenue_growth: observed expansion/maturity and growth dependence",
            "high growth is not automatically bullish",
            "operating_margin: operating profitability, scalability, cost sensitivity",
            "high margin alone proves no moat",
        ),
        (
            "debt_to_equity_ratio",
            "2.0 = approximately 2x equity",
            "interpreted by business and sector",
            "High debt is not automatically bad",
            "low debt not automatically safe",
            "Do not assert this chain without evidence or force debt into risks",
        ),
        (
            "financial_currency: monetary interpretation metadata only",
            "not currency exposure",
            "last_fiscal_year_end and most_recent_quarter",
            "never economic signals",
            "Do not assume all metrics share a common reporting period",
        ),
        (
            "DRIVER -> COMPANY-SPECIFIC ECONOMIC ENGINE OR DEPENDENCY "
            "-> TRANSMISSION MECHANISM -> ECONOMIC CONSEQUENCE",
            "larger two-sided payment network",
        ),
        (
            "STRUCTURAL PRESSURE -> COMPANY EXPOSURE "
            "-> TRANSMISSION MECHANISM -> ECONOMIC CONSEQUENCE",
            "exposed company business area",
            "how it propagates",
            "alternative payment rails",
        ),
        (
            "not severity-sounding language",
            "high: directly affects a major revenue engine",
            "medium: meaningful but secondary, indirect",
            "low: limited connection",
        ),
        (
            "market_context is STRUCTURAL",
            "No current price action, sentiment, latest earnings, "
            "or recent-news commentary",
        ),
        (
            "No intrinsic/fair value, DCF, cheap/expensive conclusions, price targets",
            "P/E, P/S, EV/EBITDA-based valuation analysis",
            "No buy/sell/hold recommendations or guaranteed predictions",
        ),
        (
            "Return ONLY valid JSON",
            "no markdown, code fences, external commentary, or internal reasoning",
            "Copy asset, asset_type, and data_scope exactly",
            'Materiality must be "low", "medium", or "high"',
        ),
        (
            "summary: 4-6 concise sentences",
            "structural_drivers and structural_risks: 3-6 each if supported",
            "never manufactured to meet a count",
            "related_entities: supplied peer tickers/names materially participating",
        ),
    ],
)
def test_compressed_prompt_keeps_semantic_guardrails(requirements):
    normalized = " ".join(ASSET_SNAPSHOT_PROMPT.split())
    for requirement in requirements:
        assert requirement in normalized


@pytest.mark.parametrize("case", load_dataset(), ids=lambda case: case.id)
def test_feature_ablation_changes_no_dynamic_fixture_context(case):
    original_case = case.model_dump_json()
    measurements = []
    prompts = []
    for template in (ORIGINAL_FEATURE_PROMPT, ASSET_SNAPSHOT_PROMPT):
        builder = MeasuredSnapshotPromptBuilder(feature_prompt=template)
        prompts.append(
            builder.build_prompt(
                case.request.asset,
                case.request.asset_type,
                case.profile_fixture,
                case.peers_fixture,
                case.fundamentals_fixture,
            )
        )
        measurements.append(builder.measurements)
    left, right = measurements
    assert left is not None and right is not None
    assert left.dynamic_context_sha256 == right.dynamic_context_sha256
    assert left.dynamic_context_chars == right.dynamic_context_chars
    assert (
        prompts[0][left.static_prompt_chars :]
        == prompts[1][right.static_prompt_chars :]
    )
    assert left.total_prompt_chars - right.total_prompt_chars == (
        left.static_prompt_chars - right.static_prompt_chars
    )
    assert case.model_dump_json() == original_case
