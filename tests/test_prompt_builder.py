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
                competition_area="AI accelerators",
                why_competitor="AMD competes in GPUs.",
                why_it_matters="It pressures pricing and share.",
                provider="fmp",
            )
        ],
    )


@pytest.fixture
def fundamentals_context() -> CompanyFundamentalsContext:
    return CompanyFundamentalsContext(
        asset="NVDA",
        provider="fmp",
        market_cap=1_000_000.0,
        operating_margin=0.3,
        debt_to_equity=0.4,
        revenue=100.0,
        revenue_growth=0.1,
    )


def test_prompt_contains_system_prompt(builder: StockSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert BASE_SYSTEM_PROMPT in prompt


def test_prompt_injects_asset_and_type(builder: StockSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert "NVDA" in prompt
    assert AssetType.STOCK.value in prompt


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


def test_prompt_with_peers_context_includes_competitors(
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

    assert "2. COMPETITIVE CONTEXT" in prompt
    assert "Advanced Micro Devices" in prompt
    assert "AMD" in prompt
    assert "profile_with_peers" in prompt


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

    assert "3. OPTIONAL FINANCIAL SIGNALS" in prompt
    assert "market_cap" in prompt
    assert "operating_margin" in prompt
    assert "optional calibration signals" in prompt
    assert "profile_with_financial_signals" in prompt


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


def test_prompt_is_business_model_first(
    builder: StockSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
    )

    assert "company profile and business model are the primary basis" in prompt
    assert "Financial metrics are optional calibration signals" in prompt


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

    assert "operating_margin: 0.3" in prompt
    assert "market_cap:" not in prompt
    assert "debt_to_equity:" not in prompt
    assert "revenue:" not in prompt
    assert "revenue_growth:" not in prompt


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
                market_cap=1_000.0,
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

    assert "Avoid vague risks" in prompt
    assert "Every structural risk must explain" in prompt
    assert "No buy/sell/hold" not in prompt


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
