import pytest

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType, CompetitivePeer
from app.domain.schemas.company_peer_context import CompanyPeerContext
from app.domain.schemas.sector_context import (
    SectorContext,
    SectorDriverContext,
    SectorRiskContext,
)
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT


@pytest.fixture
def builder() -> AssetSnapshotPromptBuilder:
    return AssetSnapshotPromptBuilder()


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
        provider="test",
    )


@pytest.fixture
def sector_context() -> SectorContext:
    return SectorContext(
        sector="Technology",
        industry="Semiconductors / AI Hardware",
        business_model_pattern="AI hardware platform economics.",
        market_context="AI chips depend on data center capex.",
        common_drivers=[
            SectorDriverContext(
                title="AI accelerator demand",
                explanation="AI workloads increase accelerator demand.",
                materiality="high",
            )
        ],
        common_risks=[
            SectorRiskContext(
                title="Export controls",
                explanation="Restrictions can limit advanced chip sales.",
                materiality="high",
            )
        ],
        competition_dimensions=["AI accelerators", "custom ASICs"],
        provider="test",
    )


@pytest.fixture
def peer_context() -> CompanyPeerContext:
    return CompanyPeerContext(
        asset="NVDA",
        peers=[
            CompetitivePeer(
                ticker="AMD",
                name="Advanced Micro Devices",
                competition_area="AI accelerators",
                why_competitor="AMD competes in GPUs.",
                why_it_matters="It pressures pricing and share.",
            )
        ],
        provider="test",
        confidence="high",
    )


# ── base prompt structure ─────────────────────────────────────────────────────


def test_prompt_contains_system_prompt(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert BASE_SYSTEM_PROMPT in prompt


def test_prompt_injects_asset(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert "NVDA" in prompt


def test_prompt_injects_asset_type(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert AssetType.STOCK.value in prompt


def test_prompt_does_not_contain_raw_placeholders(
    builder: AssetSnapshotPromptBuilder,
) -> None:
    prompt = builder.build_prompt("SPY", AssetType.ETF)
    assert "{asset}" not in prompt
    assert "{asset_type}" not in prompt


def test_prompt_does_not_raise_on_all_asset_types(
    builder: AssetSnapshotPromptBuilder,
) -> None:
    for asset_type in AssetType:
        builder.build_prompt("TEST", asset_type)


# ── asset_profile_context injection ──────────────────────────────────────────


def test_prompt_without_context_has_fallback_profile_section(
    builder: AssetSnapshotPromptBuilder,
) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)
    assert "1. Provider company profile" in prompt
    assert "Provider: none" in prompt
    assert "No provider profile was found" in prompt


def test_prompt_with_context_includes_profile_section(
    builder: AssetSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA", AssetType.STOCK, asset_profile_context=profile_context
    )
    assert "1. Provider company profile" in prompt


def test_prompt_with_context_includes_all_fields(
    builder: AssetSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA", AssetType.STOCK, asset_profile_context=profile_context
    )
    assert "NVIDIA Corporation" in prompt
    assert "Technology" in prompt
    assert "Semiconductors" in prompt
    assert "Provider: test" in prompt
    assert "Fetched at:" in prompt
    assert "NASDAQ" in prompt
    assert "USD" in prompt
    assert "USA" in prompt
    assert "NVIDIA designs GPUs" in prompt


def test_prompt_with_none_context_uses_fallback(
    builder: AssetSnapshotPromptBuilder,
) -> None:
    with_none = builder.build_prompt(
        "NVDA", AssetType.STOCK, asset_profile_context=None
    )
    assert "Provider: none" in with_none


def test_profile_section_appended_after_main_prompt(
    builder: AssetSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA", AssetType.STOCK, asset_profile_context=profile_context
    )
    main_prompt_end = prompt.index("data_scope")
    profile_start = prompt.index("1. Provider company profile")
    assert profile_start > main_prompt_end


def test_prompt_with_sector_context_includes_sector_section(
    builder: AssetSnapshotPromptBuilder,
    sector_context: SectorContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        sector_context=sector_context,
    )

    assert "2. Sector / industry context" in prompt
    assert "AI accelerator demand" in prompt
    assert "Export controls" in prompt
    assert "custom ASICs" in prompt


def test_prompt_with_peer_context_includes_competitor_names_and_tickers(
    builder: AssetSnapshotPromptBuilder,
    peer_context: CompanyPeerContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        company_peers_context=peer_context,
    )

    assert "3. Competitive landscape context" in prompt
    assert "Advanced Micro Devices" in prompt
    assert "AMD" in prompt
    assert "AI accelerators" in prompt


def test_prompt_includes_v15_json_schema(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)

    assert "competitive_landscape" in prompt
    assert "related_competitors" in prompt
    assert '"materiality": "low | medium | high"' in prompt


def test_prompt_instructs_model_to_avoid_vague_risks(
    builder: AssetSnapshotPromptBuilder,
) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK)

    assert "Avoid vague risks" in prompt
    assert "Every structural risk must explain" in prompt


def test_prompt_data_scope_reflects_available_contexts(
    builder: AssetSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
    sector_context: SectorContext,
    peer_context: CompanyPeerContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA",
        AssetType.STOCK,
        asset_profile_context=profile_context,
        sector_context=sector_context,
        company_peers_context=peer_context,
    )

    assert "provider_profile_with_static_sector_and_peer_context" in prompt
