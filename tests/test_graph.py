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
    CompetitivePeer,
)
from app.domain.schemas.company_peer_context import CompanyPeerContext
from app.domain.schemas.sector_context import (
    SectorContext,
    SectorDriverContext,
    SectorRiskContext,
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
            "competitive_landscape": [
                {
                    "ticker": "AMD",
                    "name": "Advanced Micro Devices",
                    "competition_area": "AI accelerators",
                    "why_competitor": "AMD competes in GPUs.",
                    "why_it_matters": "It pressures pricing and share.",
                }
            ],
            "structural_drivers": [
                {
                    "title": "AI demand",
                    "explanation": "AI workloads support data center GPU demand.",
                    "materiality": "high",
                }
            ],
            "structural_risks": [
                {
                    "title": "Supply chain concentration",
                    "explanation": "Foundry constraints can limit availability.",
                    "materiality": "high",
                    "related_competitors": ["AMD"],
                }
            ],
            "data_scope": "provider_profile_with_static_sector_and_peer_context",
        }
    )


def make_sector_context() -> SectorContext:
    return SectorContext(
        sector="Technology",
        industry="Semiconductors / AI Hardware",
        business_model_pattern="AI hardware platform economics.",
        market_context="Semiconductor sector.",
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
        competition_dimensions=["AI accelerators"],
        provider="test",
    )


def make_peer_context(asset: str = "NVDA") -> CompanyPeerContext:
    return CompanyPeerContext(
        asset=asset,
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


@pytest.fixture
def mock_profile_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_profile()
    return tool


@pytest.fixture
def mock_sector_context_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_sector_context()
    return tool


@pytest.fixture
def mock_company_peers_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_peer_context()
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
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)


@pytest.mark.asyncio
async def test_graph_snapshot_has_all_fields(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})
    output = final_state["validated_output"]

    assert output.competitive_landscape[0].ticker == "AMD"
    assert output.structural_drivers[0].title == "AI demand"
    assert output.structural_risks[0].title == "Supply chain concentration"
    assert output.business_or_asset_profile == "Designs GPUs for gaming and AI."


@pytest.mark.asyncio
async def test_graph_passes_profile_context_to_prompt_builder(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    profile = make_profile()
    mock_profile_tool.run.return_value = profile
    sector_context = make_sector_context()
    peer_context = make_peer_context()
    mock_sector_context_tool.run.return_value = sector_context
    mock_company_peers_tool.run.return_value = peer_context
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    await graph.ainvoke({"request": make_request(), "errors": []})

    call_kwargs = mock_prompt_builder.build_prompt.call_args.kwargs
    assert call_kwargs["asset_profile_context"] == profile
    assert call_kwargs["sector_context"] == sector_context
    assert call_kwargs["company_peers_context"] == peer_context


@pytest.mark.asyncio
async def test_graph_has_no_errors_on_happy_path(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["errors"] == []


# ── error propagation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_records_error_when_llm_fails(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.side_effect = RuntimeError("ollama unreachable")
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["validated_output"] is None
    assert any("ollama unreachable" in e for e in final_state["errors"])


@pytest.mark.asyncio
async def test_graph_records_error_when_llm_returns_invalid_json(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.return_value = "not valid json"
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["validated_output"] is None
    assert final_state["errors"]


@pytest.mark.asyncio
async def test_graph_continues_when_profile_tool_fails(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_profile_tool.run.side_effect = RuntimeError("provider unavailable")
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)
    assert any("provider unavailable" in e for e in final_state["errors"])


@pytest.mark.asyncio
async def test_graph_continues_when_peer_tool_returns_empty_peers(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_company_peers_tool.run.return_value = CompanyPeerContext(
        asset="NVDA",
        peers=[],
        provider="test",
        confidence="low",
    )
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)


@pytest.mark.asyncio
async def test_graph_continues_when_sector_tool_fails(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_sector_context_tool.run.side_effect = RuntimeError("sector unavailable")
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)
    assert any("sector unavailable" in e for e in final_state["errors"])


@pytest.mark.asyncio
async def test_graph_continues_when_profile_tool_returns_none(
    mock_profile_tool: AsyncMock,
    mock_sector_context_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_profile_tool.run.return_value = None
    graph = build_asset_snapshot_graph(
        mock_profile_tool,
        mock_sector_context_tool,
        mock_company_peers_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await graph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], AssetSnapshot)
