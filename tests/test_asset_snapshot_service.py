import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.schemas.asset_snapshot import (
    AssetSnapshotMode,
    AssetType,
    LongAssetSnapshot,
    ShortAssetSnapshot,
)
from app.services.asset_snapshot_service import AssetSnapshotService


# ── helpers ─────────────────────────────────────────────────────────────────


def make_short_json(asset: str = "NVDA", asset_type: str = "stock") -> str:
    return json.dumps(
        {
            "mode": "short",
            "asset": asset,
            "asset_type": asset_type,
            "summary": "NVDA is a GPU manufacturer.",
            "market_context": "Semiconductor sector.",
            "data_scope": "static_asset_profile",
        }
    )


def make_long_json(asset: str = "NVDA", asset_type: str = "stock") -> str:
    return json.dumps(
        {
            "mode": "long",
            "asset": asset,
            "asset_type": asset_type,
            "summary": "NVDA is a GPU manufacturer.",
            "business_or_asset_profile": "Designs GPUs for gaming and AI.",
            "market_context": "Semiconductor sector.",
            "structural_drivers": ["AI demand", "data centre growth"],
            "structural_risks": ["supply chain", "regulation"],
            "data_scope": "static_asset_profile",
        }
    )


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm() -> AsyncMock:
    client = AsyncMock()
    return client


@pytest.fixture
def mock_builder() -> MagicMock:
    builder = MagicMock()
    builder.build_prompt.return_value = "mocked prompt"
    return builder


# ── short-mode tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_snapshot_short_returns_short_model(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = make_short_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    result = await service.get_snapshot(
        "NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT
    )

    assert isinstance(result, ShortAssetSnapshot)


@pytest.mark.asyncio
async def test_get_snapshot_short_fields(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = make_short_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    result = await service.get_snapshot(
        "NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT
    )

    assert result.asset == "NVDA"
    assert result.asset_type == AssetType.STOCK
    assert result.mode == AssetSnapshotMode.SHORT
    assert result.summary == "NVDA is a GPU manufacturer."


# ── long-mode tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_snapshot_long_returns_long_model(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = make_long_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    result = await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.LONG)

    assert isinstance(result, LongAssetSnapshot)


@pytest.mark.asyncio
async def test_get_snapshot_long_fields(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = make_long_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    result = await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.LONG)

    assert isinstance(result, LongAssetSnapshot)
    assert result.business_or_asset_profile == "Designs GPUs for gaming and AI."
    assert "AI demand" in result.structural_drivers
    assert "supply chain" in result.structural_risks


# ── prompt builder delegation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_snapshot_calls_prompt_builder(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = make_short_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)

    mock_builder.build_prompt.assert_called_once_with(
        "NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT
    )


@pytest.mark.asyncio
async def test_get_snapshot_passes_prompt_to_llm(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_builder.build_prompt.return_value = "expected prompt"
    mock_llm.generate.return_value = make_short_json()
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)

    mock_llm.generate.assert_awaited_once_with("expected prompt")


# ── error handling ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_snapshot_raises_value_error_on_invalid_json(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    mock_llm.generate.return_value = "this is not valid json"
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    with pytest.raises(ValueError, match="Failed to parse LLM response"):
        await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)


@pytest.mark.asyncio
async def test_get_snapshot_raises_value_error_on_missing_fields(
    mock_llm: AsyncMock, mock_builder: MagicMock
) -> None:
    # Valid JSON but missing required schema fields
    mock_llm.generate.return_value = json.dumps({"mode": "short"})
    service = AssetSnapshotService(llm_client=mock_llm, prompt_builder=mock_builder)

    with pytest.raises(ValueError, match="Failed to parse LLM response"):
        await service.get_snapshot("NVDA", AssetType.STOCK, AssetSnapshotMode.SHORT)
