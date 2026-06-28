"""
Integration tests for the compiled LangGraph.

Graph tests test the *wiring*: node order, state flow, and final output.
We mock all external I/O (LLM, tools) — no real network calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.graph import build_asset_snapshot_graph
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetSnapshot,
    AssetSnapshotRequest,
    AssetType,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def make_request(
    asset: str = "NVDA",
    asset_type: AssetType = AssetType.STOCK,
) -> AssetSnapshotRequest:
    return AssetSnapshotRequest(asset=asset, asset_type=asset_type)


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


def llm_response(asset: str = "NVDA") -> str:
    return json.dumps(
        {
            "asset": asset,
            "asset_type": "stock",
            "summary": "GPU manufacturer.",
            "market_context": "Semiconductor sector.",
            "business_or_asset_profile": "Designs GPUs for gaming and AI.",
            "structural_drivers": ["AI demand"],
            "structural_risks": ["supply chain"],
            "data_scope": "static_asset_profile",
        }
    )


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
    llm.generate.return_value = llm_response()
    return llm


# ── happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_produces_asset_snapshot(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)


@pytest.mark.asyncio
async def test_graph_snapshot_has_all_fields(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})
    output = final_state["validated_output"]

    assert output.structural_drivers == ["AI demand"]
    assert output.structural_risks == ["supply chain"]
    assert output.business_or_asset_profile == "Designs GPUs for gaming and AI."


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


@pytest.mark.asyncio
async def test_graph_continues_when_profile_tool_fails(
    mock_profile_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_profile_tool.run.side_effect = RuntimeError("provider unavailable")
    graph = build_asset_snapshot_graph(mock_profile_tool, mock_prompt_builder, mock_llm)

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)
    assert any("provider unavailable" in e for e in final_state["errors"])
