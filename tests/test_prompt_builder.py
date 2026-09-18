from datetime import date

import pytest

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT


@pytest.fixture
def builder() -> StockSnapshotPromptBuilder:
    return StockSnapshotPromptBuilder()


@pytest.fixture
def profile_context() -> AssetProfileContext:
    return AssetProfileContext(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        name="NVIDIA Corporation",
        sector="Technology",
        industry="Semiconductors",
        business_summary="NVIDIA designs GPUs and system-on-chip units.",
        exchange="NASDAQ",
        currency="USD",
        country="USA",
        provider="yfinance",
    )


@pytest.fixture
def peer_context() -> CompanyPeersContext:
    return CompanyPeersContext(
        asset="NVDA",
        provider="fmp",
        peers=[
            CompanyPeer(
                ticker="AMD",
                name="Advanced Micro Devices",
                profile=AssetProfileContext(
                    asset="AMD",
                    asset_type=AssetType.STOCK,
                    name="Advanced Micro Devices",
                    sector="Technology",
                    industry="Semiconductors",
                    business_summary="Designs GPUs and processors.",
                    exchange=None,
                    currency=None,
                    country=None,
                    provider="yfinance",
                ),
                provider="fmp",
            )
        ],
    )


@pytest.fixture
def fundamentals_context() -> CompanyFundamentalsContext:
    return CompanyFundamentalsContext(
        asset="NVDA",
        provider="fmp",
        revenue=100.0,
        revenue_growth=0.1,
        operating_margin=0.3,
        debt_to_equity_ratio=2.09,
        financial_currency="USD",
        last_fiscal_year_end=date(2024, 12, 31),
        most_recent_quarter=date(2025, 6, 30),
    )


def test_prompt_contains_system_prompt(builder: StockSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert BASE_SYSTEM_PROMPT in prompt


def test_prompt_injects_asset_and_type(builder: StockSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert "NVDA" in prompt
    assert AssetType.STOCK.value in prompt
    assert '"asset": "NVDA"' in prompt
    assert '"asset_type": "stock"' in prompt
    assert '"asset_type": "string"' not in prompt
    assert 'Do not replace asset_type with "Company"' in prompt


def test_prompt_without_context_has_fallback_profile_section(
    builder: StockSnapshotPromptBuilder,
) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert "1. COMPANY PROFILE" in prompt
    assert "Provider: none" in prompt
    assert "No provider profile was found" in prompt
    assert "model_static_knowledge_fallback" in prompt


def test_prompt_with_profile_context_includes_provider_fields(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
    )

    assert "NVIDIA Corporation" in prompt
    assert "Technology" in prompt
    assert "Semiconductors" in prompt
    assert "Provider: yfinance" in prompt
    assert "profile_only" in prompt


def test_prompt_with_peers_context_includes_peer_relationship_instructions(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    peer_context: CompanyPeersContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_peers_context=peer_context,
    )

    assert "2. PEER CONTEXT" in prompt
    assert "Advanced Micro Devices" in prompt
    assert "AMD" in prompt
    assert "profile_with_peers" in prompt
    assert "Designs GPUs and processors." in prompt
    assert "Provider: yfinance" in prompt
    assert "Fetched at:" in prompt
    assert "relationship_area=Not available" not in prompt
    assert "analytical OUTPUT" in " ".join(prompt.split())
    assert 'bare "Not available" is not' in prompt
    assert "Enrichment qualifies explanations, not eligibility" in prompt
    assert "EVERY distinct identifiable supplied peer" in prompt


def test_prompt_with_fundamentals_context_includes_metrics(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    fundamentals_context: CompanyFundamentalsContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_fundamentals_context=fundamentals_context,
    )

    assert "3. SUPPORTING FINANCIAL FUNDAMENTALS" in prompt
    assert "Revenue: 100" in prompt
    assert "Revenue growth: 10.00%" in prompt
    assert "Operating margin: 30.00%" in prompt
    assert "Debt-to-equity ratio: 2.09x" in prompt
    assert "Debt-to-equity ratio: 209x" not in prompt
    assert "Debt-to-equity ratio: 209%" not in prompt
    assert "Financial currency: USD" in prompt
    assert "Latest fiscal year end: 2024-12-31" in prompt
    assert "Most recent quarter: 2025-06-30" in prompt
    assert "market_cap" not in prompt
    assert "quantitative supporting evidence" in prompt
    assert "profile_with_financial_signals" in prompt


@pytest.mark.parametrize("with_profile", [False, True])
def test_prompt_retains_sparse_or_nonoverlapping_provider_peer(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    with_profile: bool,
) -> None:
    peer_profile = (
        profile_context.model_copy(
            update={
                "asset": "FARM",
                "name": "Field Farm",
                "industry": "Agriculture",
                "business_summary": "Grows wheat and sells grain to food processors.",
            }
        )
        if with_profile
        else None
    )
    peers = CompanyPeersContext(
        asset="NVDA",
        provider="fmp",
        peers=[CompanyPeer(ticker="FARM", name="Field Farm", profile=peer_profile)],
    )
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, profile_context, peers)
    assert "FARM | Field Farm" in prompt
    assert "Provider-reported peers are a research universe" in prompt
    assert "not eligibility" in prompt
    assert "explain why impact cannot be assessed" in prompt
    assert 'qualify absent overlap, not a "missing profile"' in prompt
    if with_profile:
        assert "Grows wheat" in prompt
    else:
        assert "Retain peers without profiles" in prompt


def test_prompt_data_scope_reflects_profile_peers_and_fundamentals(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    peer_context: CompanyPeersContext,
    fundamentals_context: CompanyFundamentalsContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_peers_context=peer_context,
        company_fundamentals_context=fundamentals_context,
    )

    assert "profile_with_peers_and_financial_signals" in prompt
    assert "NVIDIA Corporation" in prompt
    assert "Advanced Micro Devices" in prompt


def test_prompt_is_business_model_first(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
    )

    assert "company profile and business model are primary" in prompt
    assert "Financial fundamentals are quantitative supporting evidence" in prompt


def test_prompt_includes_only_available_financial_signals(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    fundamentals = CompanyFundamentalsContext(
        asset="NVDA",
        provider="yfinance",
        operating_margin=0.3,
    )

    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_fundamentals_context=fundamentals,
    )

    assert "Operating margin: 30.00%" in prompt
    assert "Market cap:" not in prompt
    assert "Debt-to-equity ratio:" not in prompt
    assert "Revenue:" not in prompt
    assert "Revenue growth:" not in prompt
    assert "Financial currency:" not in prompt


def test_removed_financial_metrics_are_absent_from_prompt(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    fundamentals_context: CompanyFundamentalsContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_fundamentals_context=fundamentals_context,
    )

    assert "gross_margin" not in prompt
    assert "net_margin" not in prompt
    assert "return_on_equity" not in prompt


@pytest.mark.parametrize(
    ("peers", "fundamentals", "expected_scope"),
    [
        (None, None, "profile_only"),
        (
            CompanyPeersContext(
                asset="NVDA",
                provider="fmp",
                peers=[CompanyPeer(ticker="AMD")],
            ),
            None,
            "profile_with_peers",
        ),
        (
            None,
            CompanyFundamentalsContext(
                asset="NVDA",
                provider="yfinance",
                revenue=1_000.0,
            ),
            "profile_with_financial_signals",
        ),
        (
            CompanyPeersContext(
                asset="NVDA",
                provider="fmp",
                peers=[CompanyPeer(ticker="AMD")],
            ),
            CompanyFundamentalsContext(
                asset="NVDA",
                provider="yfinance",
                operating_margin=0.3,
            ),
            "profile_with_peers_and_financial_signals",
        ),
    ],
)
def test_data_scope_reflects_meaningful_provider_coverage(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    peers: CompanyPeersContext | None,
    fundamentals: CompanyFundamentalsContext | None,
    expected_scope: str,
) -> None:
    assert (
        builder.data_scope(
            asset_profile_context=profile_context,
            company_peers_context=peers,
            company_fundamentals_context=fundamentals,
        )
        == expected_scope
    )


def test_empty_financial_context_does_not_change_profile_scope(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    fundamentals = CompanyFundamentalsContext(
        asset="NVDA",
        provider="yfinance",
    )

    assert (
        builder.data_scope(
            asset_profile_context=profile_context,
            company_peers_context=None,
            company_fundamentals_context=fundamentals,
        )
        == "profile_only"
    )


def test_financial_metadata_without_numeric_signals_does_not_change_scope(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    fundamentals = CompanyFundamentalsContext(
        asset="NVDA",
        provider="yfinance",
        financial_currency="USD",
        last_fiscal_year_end=date(2024, 12, 31),
    )

    assert (
        builder.data_scope(
            asset_profile_context=profile_context,
            company_peers_context=None,
            company_fundamentals_context=fundamentals,
        )
        == "profile_only"
    )

    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_fundamentals_context=fundamentals,
    )
    assert "Financial currency: USD" in prompt
    assert "Latest fiscal year end: 2024-12-31" in prompt


def test_prompt_formats_large_revenue_without_scientific_notation(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_fundamentals_context=CompanyFundamentalsContext(
            asset="NVDA",
            provider="yfinance",
            revenue=39_331_000_000,
        ),
    )

    assert "Revenue: 39,331,000,000" in prompt
    assert "e+" not in prompt


def test_prompt_uses_fmp_profile_fallback_scope(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    profile_context.provider = "fmp"

    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
    )

    assert "fmp_profile_fallback" in prompt


def test_prompt_includes_risk_mechanism_guardrails(
    builder: StockSnapshotPromptBuilder,
) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)

    normalized = " ".join(prompt.split())
    assert (
        "STRUCTURAL PRESSURE -> COMPANY EXPOSURE -> TRANSMISSION MECHANISM"
        in normalized
    )
    assert "exposed company business area" in normalized
    assert "High debt is not automatically bad" in prompt
    assert "P/E, P/S, EV/EBITDA" in prompt and "DCF" in prompt
    assert "No buy/sell/hold recommendations" in prompt


def test_prompt_does_not_contain_raw_vendor_json(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    peer_context: CompanyPeersContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        company_peers_context=peer_context,
    )

    assert "regularMarketPrice" not in prompt
    assert "raw" not in prompt.lower()
