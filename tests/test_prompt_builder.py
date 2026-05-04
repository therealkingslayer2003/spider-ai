import pytest

from app.domain.schemas.asset_snapshot import AssetSnapshotMode, AssetType
from app.llm.prompts.feature_snapshot_prompt import LONG_ASSET_SNAPSHOT_PROMPT, SHORT_ASSET_SNAPSHOT_PROMPT
from app.llm.prompts.feature_snapshot_prompt_builder import AssetSnapshotPromptBuilder
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT


@pytest.fixture
def builder() -> AssetSnapshotPromptBuilder:
    return AssetSnapshotPromptBuilder()


def test_short_prompt_contains_system_prompt(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)
    assert BASE_SYSTEM_PROMPT in prompt


def test_long_prompt_contains_system_prompt(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("BTC", AssetType.CRYPTO, AssetSnapshotMode.LONG)
    assert BASE_SYSTEM_PROMPT in prompt


def test_short_prompt_injects_asset(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)
    assert "NVDA" in prompt


def test_long_prompt_injects_asset(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("EUR/USD", AssetType.FX, AssetSnapshotMode.LONG)
    assert "EUR/USD" in prompt


def test_short_prompt_injects_asset_type(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)
    assert AssetType.STOCK.value in prompt


def test_long_prompt_injects_asset_type(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("GOLD", AssetType.COMMODITY, AssetSnapshotMode.LONG)
    assert AssetType.COMMODITY.value in prompt


def test_short_mode_uses_short_template(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)
    # SHORT template contains "SHORT asset snapshot" and not the long-only field
    assert "SHORT" in prompt
    assert "business_or_asset_profile" not in prompt


def test_long_mode_uses_long_template(builder: AssetSnapshotPromptBuilder) -> None:
    prompt = builder.build_prompt("NVDA", AssetType.STOCK, AssetSnapshotMode.LONG)
    # LONG template includes the extra field not present in SHORT
    assert "business_or_asset_profile" in prompt


def test_prompt_does_not_contain_raw_placeholders(builder: AssetSnapshotPromptBuilder) -> None:
    """Ensure {asset} and {asset_type} placeholders were replaced, not left in the output."""
    prompt = builder.build_prompt("SPY", AssetType.ETF, AssetSnapshotMode.SHORT)
    assert "{asset}" not in prompt
    assert "{asset_type}" not in prompt


def test_prompt_does_not_raise_on_all_asset_types(builder: AssetSnapshotPromptBuilder) -> None:
    """Smoke-test every AssetType × AssetSnapshotMode combination."""
    for asset_type in AssetType:
        for mode in AssetSnapshotMode:
            # Should not raise KeyError or any other exception
            prompt = builder.build_prompt("TEST", asset_type, mode)
            assert len(prompt) > 0
