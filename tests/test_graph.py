"""
Integration tests for the compiled LangGraph.

Mental model
------------
Graph tests sit one layer above node tests. They test the *wiring*:
- Do nodes execute in the right order?
- Does state flow correctly between nodes?
- Does the final state contain the expected output?

We still mock ALL external I/O (LLM, tools) — we are not testing Ollama
or network calls here. The graph itself (edges, state passing) is what
we are validating.

Use graph.ainvoke() directly. This exercises the full compiled graph
the same way the runner does in production.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.graph import build_asset_snapshot_graph
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


def short_llm_response(asset: str = "NVDA") -> str:
    return json.dumps({
        "mode": "short",
        "asset": asset,
        "asset_type": "stock",
        "summary": "GPU manufacturer.",
        "market_context": "Semiconductor sector.",
        "data_scope": "static_asset_profile",
    })


def long_llm_response(asset: str = "NVDA") -> str:
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


@pytest.fixture
def mock_profile_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_profile()
    return tool


@pytest.fixture
def mock_prompt_builder() -> MagicMock:
    builder = MagicMock()
    builder.build_prompt.return_value = "mocked prompt"
    return builder


@pytest.fixture
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.generate.return_value = short_llm_response()
    return llm


# ── happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_produces_short_snapshot(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({
        "request": make_request(mode=AssetSnapshotMode.SHORT),
        "errors": [],
    })

    assert isinstance(final_state["validated_output"], ShortAssetSnapshot)


@pytest.mark.asyncio
async def test_graph_produces_long_snapshot(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.return_value = long_llm_response()
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({
        "request": make_request(mode=AssetSnapshotMode.LONG),
        "errors": [],
    })

    assert isinstance(final_state["validated_output"], LongAssetSnapshot)


@pytest.mark.asyncio
async def test_graph_passes_profile_context_to_prompt_builder(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    profile = make_profile()
    mock_profile_tool.run.return_value = profile
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    await graph.ainvoke({"request": make_request(), "errors": []})

    call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
    assert call_kwargs["asset_profile_context"] == profile


@pytest.mark.asyncio
async def test_graph_has_no_errors_on_happy_path(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["errors"] == []


# ── error propagation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_records_error_when_llm_fails(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.side_effect = RuntimeError("ollama unreachable")
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["validated_output"] is None
    assert any("ollama unreachable" in e for e in final_state["errors"])


@pytest.mark.asyncio
async def test_graph_records_error_when_llm_returns_invalid_json(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.return_value = "not valid json"
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["validated_output"] is None
    assert final_state["errors"]
