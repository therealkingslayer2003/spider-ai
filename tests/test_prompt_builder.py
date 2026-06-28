import pytest

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
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
    assert "Asset profile context" in prompt
    assert "Provider: none" in prompt
    assert "No provider profile was found" in prompt


def test_prompt_with_context_includes_profile_section(
    builder: AssetSnapshotPromptBuilder,
    profile_context: AssetProfileContext,
) -> None:
    prompt = builder.build_prompt(
        "NVDA", AssetType.STOCK, asset_profile_context=profile_context
    )
    assert "Asset profile context" in prompt


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
    profile_start = prompt.index("Asset profile context")
    assert profile_start > main_prompt_end
