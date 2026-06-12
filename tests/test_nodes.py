import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.nodes import (
    asset_profile_tool_node,
    generate_snapshot_node,
    planner_node,
    validate_snapshot_node,
)
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotMode,
    AssetSnapshotRequest,
    AssetType,
    LongAssetSnapshot,
    ShortAssetSnapshot,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def make_request(
    asset: str = "NVDA",
    asset_type: AssetType = AssetType.STOCK,
    mode: AssetSnapshotMode = AssetSnapshotMode.SHORT,
) -> AssetSnapshotRequest:
    return AssetSnapshotRequest(asset=asset, asset_type=asset_type, mode=mode)


def make_profile(asset: str = "NVDA") -> AssetProfileContext:
    return AssetProfileContext(
        asset=asset,
        asset_type=AssetType.STOCK,
        name="NVIDIA Corporation",
        sector="Technology",
        industry="Semiconductors",
        business_summary="Designs GPUs.",
        exchange="NASDAQ",
        currency="USD",
        country="USA",
        provider="test",
    )


def short_json(asset: str = "NVDA") -> str:
    return json.dumps({
        "mode": "short",
        "asset": asset,
        "asset_type": "stock",
        "summary": "GPU manufacturer.",
        "market_context": "Semiconductor sector.",
        "data_scope": "static_asset_profile",
    })


def long_json(asset: str = "NVDA") -> str:
    return json.dumps({
        "mode": "long",
        "asset": asset,
        "asset_type": "stock",
        "summary": "GPU manufacturer.",
        "business_or_asset_profile": "Designs GPUs for gaming and AI.",
        "market_context": "Semiconductor sector.",
        "structural_drivers": ["AI demand"],
        "structural_risks": ["supply chain"],
        "data_scope": "static_asset_profile",
    })


# ── planner_node ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_routes_stock_to_stable_profile_tool() -> None:
    state = {"request": make_request(asset_type=AssetType.STOCK), "errors": []}
    result = await planner_node(state)
    assert result["selected_tool_name"] == "stable_asset_profile_search"


@pytest.mark.asyncio
async def test_planner_returns_none_tool_for_unsupported_type() -> None:
    state = {"request": make_request(asset_type=AssetType.CRYPTO), "errors": []}
    result = await planner_node(state)
    assert result["selected_tool_name"] is None


@pytest.mark.asyncio
async def test_planner_adds_error_for_unsupported_type() -> None:
    state = {"request": make_request(asset_type=AssetType.CRYPTO), "errors": []}
    result = await planner_node(state)
    assert any("CRYPTO" in e for e in result["errors"])


# ── asset_profile_tool_node ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_asset_profile_tool_returns_context_on_success() -> None:
    profile = make_profile()
    mock_tool = AsyncMock()
    mock_tool.run.return_value = profile
    tools = {"stable_asset_profile_search": mock_tool}

    state = {
        "request": make_request(),
        "selected_tool_name": "stable_asset_profile_search",
        "errors": [],
    }
    result = await asset_profile_tool_node(state, tools)

    assert result["asset_profile_context"] == profile


@pytest.mark.asyncio
async def test_asset_profile_tool_calls_run_with_correct_args() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.return_value = make_profile()
    tools = {"stable_asset_profile_search": mock_tool}

    state = {
        "request": make_request(asset="NVDA", asset_type=AssetType.STOCK),
        "selected_tool_name": "stable_asset_profile_search",
        "errors": [],
    }
    await asset_profile_tool_node(state, tools)

    mock_tool.run.assert_awaited_once_with(asset="NVDA", asset_type=AssetType.STOCK)


@pytest.mark.asyncio
async def test_asset_profile_tool_returns_none_when_no_tool_selected() -> None:
    state = {"request": make_request(), "selected_tool_name": None, "errors": []}
    result = await asset_profile_tool_node(state, {})
    assert result["asset_profile_context"] is None


@pytest.mark.asyncio
async def test_asset_profile_tool_returns_none_when_tool_not_found() -> None:
    state = {
        "request": make_request(),
        "selected_tool_name": "unknown_tool",
        "errors": [],
    }
    result = await asset_profile_tool_node(state, {})
    assert result["asset_profile_context"] is None
    assert any("unknown_tool" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_asset_profile_tool_handles_tool_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("network error")
    tools = {"stable_asset_profile_search": mock_tool}

    state = {
        "request": make_request(),
        "selected_tool_name": "stable_asset_profile_search",
        "errors": [],
    }
    result = await asset_profile_tool_node(state, tools)

    assert result["asset_profile_context"] is None
    assert any("network error" in e for e in result["errors"])


# ── generate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_snapshot_sets_raw_llm_output() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = short_json()
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"

    state = {
        "request": make_request(),
        "asset_profile_context": None,
        "errors": [],
    }
    result = await generate_snapshot_node(state, mock_llm, mock_builder)

    assert result["raw_llm_output"] == short_json()


@pytest.mark.asyncio
async def test_generate_snapshot_passes_profile_context_to_builder() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = short_json()
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"
    profile = make_profile()

    state = {
        "request": make_request(),
        "asset_profile_context": profile,
        "errors": [],
    }
    await generate_snapshot_node(state, mock_llm, mock_builder)

    mock_builder.build_prompt.assert_called_once_with(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        mode=AssetSnapshotMode.SHORT,
        asset_profile_context=profile,
    )


@pytest.mark.asyncio
async def test_generate_snapshot_records_error_on_llm_failure() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.side_effect = RuntimeError("timeout")
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"

    state = {"request": make_request(), "asset_profile_context": None, "errors": []}
    result = await generate_snapshot_node(state, mock_llm, mock_builder)

    assert result["raw_llm_output"] is None
    assert any("timeout" in e for e in result["errors"])


# ── validate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_snapshot_parses_short_json() -> None:
    state = {"raw_llm_output": short_json(), "errors": []}
    result = await validate_snapshot_node(state)
    assert isinstance(result["validated_output"], ShortAssetSnapshot)


@pytest.mark.asyncio
async def test_validate_snapshot_parses_long_json() -> None:
    state = {"raw_llm_output": long_json(), "errors": []}
    result = await validate_snapshot_node(state)
    assert isinstance(result["validated_output"], LongAssetSnapshot)


@pytest.mark.asyncio
async def test_validate_snapshot_short_fields_are_correct() -> None:
    state = {"raw_llm_output": short_json("MA"), "errors": []}
    result = await validate_snapshot_node(state)
    output = result["validated_output"]
    assert output.asset == "MA"
    assert output.mode == AssetSnapshotMode.SHORT


@pytest.mark.asyncio
async def test_validate_snapshot_long_fields_are_correct() -> None:
    state = {"raw_llm_output": long_json("MA"), "errors": []}
    result = await validate_snapshot_node(state)
    output = result["validated_output"]
    assert isinstance(output, LongAssetSnapshot)
    assert output.structural_drivers == ["AI demand"]
    assert output.structural_risks == ["supply chain"]


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_on_invalid_json() -> None:
    state = {"raw_llm_output": "not json at all", "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert any("parse error" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_on_missing_fields() -> None:
    state = {"raw_llm_output": json.dumps({"mode": "short"}), "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"]


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_when_no_output() -> None:
    state = {"raw_llm_output": None, "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"]
