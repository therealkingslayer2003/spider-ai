"""
Unit tests for LangGraph nodes.

A LangGraph node is just an async function: (state: dict) -> dict.
LangGraph is NOT involved here — we call each node function directly.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.nodes import (
    ambiguous_asset_resolution_node,
    asset_profile_tool_node,
    company_peers_tool_node,
    generate_snapshot_node,
    planner_node,
    sector_context_tool_node,
    validate_snapshot_node,
)
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


def snapshot_json(asset: str = "NVDA") -> str:
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
                    "why_competitor": "AMD competes in GPUs and accelerators.",
                    "why_it_matters": "It can pressure Nvidia pricing and share.",
                }
            ],
            "structural_drivers": [
                {
                    "title": "AI demand",
                    "explanation": "Data center AI demand supports GPU revenue.",
                    "materiality": "high",
                }
            ],
            "structural_risks": [
                {
                    "title": "Supply chain concentration",
                    "explanation": "Foundry constraints can affect availability.",
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
                why_competitor="AMD competes with GPUs and accelerators.",
                why_it_matters="It pressures pricing and customer choice.",
            )
        ],
        provider="test",
        confidence="high",
    )


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
async def test_asset_profile_tool_uses_resolved_asset_when_available() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.return_value = make_profile("AAPL")
    tools = {"stable_asset_profile_search": mock_tool}

    state = {
        "request": make_request(asset="Apple", asset_type=AssetType.STOCK),
        "resolved_asset": "AAPL",
        "selected_tool_name": "stable_asset_profile_search",
        "errors": [],
    }
    await asset_profile_tool_node(state, tools)
    mock_tool.run.assert_awaited_once_with(asset="AAPL", asset_type=AssetType.STOCK)


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


# ── sector_context_tool_node ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sector_context_tool_returns_context_on_success() -> None:
    mock_tool = AsyncMock()
    sector_context = make_sector_context()
    mock_tool.run.return_value = sector_context
    profile = make_profile()

    state = {"asset_profile_context": profile, "errors": []}
    result = await sector_context_tool_node(state, mock_tool)

    assert result["sector_context"] == sector_context
    mock_tool.run.assert_awaited_once_with(asset_profile_context=profile)


@pytest.mark.asyncio
async def test_sector_context_tool_handles_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("sector mapping failed")

    state = {"asset_profile_context": make_profile(), "errors": []}
    result = await sector_context_tool_node(state, mock_tool)

    assert result["sector_context"] is None
    assert any("sector mapping failed" in e for e in result["errors"])


# ── company_peers_tool_node ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_company_peers_tool_returns_context_on_success() -> None:
    mock_tool = AsyncMock()
    peer_context = make_peer_context()
    mock_tool.run.return_value = peer_context
    profile = make_profile()

    state = {
        "request": make_request(),
        "asset_profile_context": profile,
        "errors": [],
    }
    result = await company_peers_tool_node(state, mock_tool)

    assert result["company_peers_context"] == peer_context
    mock_tool.run.assert_awaited_once_with(
        asset="NVDA",
        asset_profile_context=profile,
    )


@pytest.mark.asyncio
async def test_company_peers_tool_uses_resolved_asset() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.return_value = make_peer_context("AAPL")
    profile = make_profile("AAPL")

    state = {
        "request": make_request(asset="Apple"),
        "resolved_asset": "AAPL",
        "asset_profile_context": profile,
        "errors": [],
    }
    await company_peers_tool_node(state, mock_tool)

    mock_tool.run.assert_awaited_once_with(
        asset="AAPL",
        asset_profile_context=profile,
    )


@pytest.mark.asyncio
async def test_company_peers_tool_handles_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("peer mapping failed")

    state = {"request": make_request(), "asset_profile_context": None, "errors": []}
    result = await company_peers_tool_node(state, mock_tool)

    assert result["company_peers_context"] is None
    assert any("peer mapping failed" in e for e in result["errors"])


# ── generate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_snapshot_sets_raw_llm_output() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = snapshot_json()
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"

    state = {
        "request": make_request(),
        "asset_profile_context": None,
        "company_peers_context": None,
        "sector_context": None,
        "errors": [],
    }
    result = await generate_snapshot_node(state, mock_llm, mock_builder)
    assert result["raw_llm_output"] == snapshot_json()


@pytest.mark.asyncio
async def test_generate_snapshot_passes_profile_context_to_builder() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = snapshot_json()
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"
    profile = make_profile()
    sector_context = make_sector_context()
    peer_context = make_peer_context()

    state = {
        "request": make_request(),
        "asset_profile_context": profile,
        "sector_context": sector_context,
        "company_peers_context": peer_context,
        "errors": [],
    }
    await generate_snapshot_node(state, mock_llm, mock_builder)

    mock_builder.build_prompt.assert_called_once_with(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        asset_profile_context=profile,
        company_peers_context=peer_context,
        sector_context=sector_context,
    )


@pytest.mark.asyncio
async def test_ambiguous_resolver_skips_ticker_like_input() -> None:
    mock_llm = AsyncMock()
    state = {"request": make_request(asset="NVDA"), "errors": []}

    result = await ambiguous_asset_resolution_node(state, mock_llm)

    assert result["resolved_asset"] is None
    mock_llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_resolver_resolves_common_name() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = json.dumps(
        {
            "original_asset": "APPLE",
            "resolved_asset": "AAPL",
            "confidence": 0.92,
            "reasoning": "Apple commonly refers to Apple Inc.",
        }
    )
    state = {"request": make_request(asset="Apple"), "errors": []}

    result = await ambiguous_asset_resolution_node(state, mock_llm)

    assert result["resolved_asset"] == "AAPL"


@pytest.mark.asyncio
async def test_ambiguous_resolver_extracts_ticker_prefix_without_llm() -> None:
    mock_llm = AsyncMock()
    state = {"request": make_request(asset="MA(MASTERCARD)"), "errors": []}

    result = await ambiguous_asset_resolution_node(state, mock_llm)

    assert result["resolved_asset"] == "MA"
    mock_llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_resolver_parses_markdown_fenced_json() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = """```json
{
  "original_asset": "MA(MASTERCARD)",
  "resolved_asset": "MA",
  "confidence": 1.0,
  "reasoning": "Resolved to MA, likely Mastercard."
}
```"""
    state = {"request": make_request(asset="MA(MASTERCARD)"), "errors": []}

    result = await ambiguous_asset_resolution_node(state, mock_llm)

    assert result["resolved_asset"] == "MA"


@pytest.mark.asyncio
async def test_ambiguous_resolver_rejects_non_ticker_like_llm_resolution() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = json.dumps(
        {
            "original_asset": "MASTERCARD",
            "resolved_asset": "MASTECO",
            "confidence": 0.8,
            "reasoning": "Incorrectly invented ticker.",
        }
    )
    state = {"request": make_request(asset="Mastercard"), "errors": []}

    result = await ambiguous_asset_resolution_node(state, mock_llm)

    assert result["resolved_asset"] is None


@pytest.mark.asyncio
async def test_generate_snapshot_records_error_on_llm_failure() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.side_effect = RuntimeError("timeout")
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"

    state = {
        "request": make_request(),
        "asset_profile_context": None,
        "company_peers_context": None,
        "sector_context": None,
        "errors": [],
    }
    result = await generate_snapshot_node(state, mock_llm, mock_builder)
    assert result["raw_llm_output"] is None
    assert any("timeout" in e for e in result["errors"])


# ── validate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_snapshot_parses_json() -> None:
    state = {"raw_llm_output": snapshot_json(), "errors": []}
    result = await validate_snapshot_node(state)
    assert isinstance(result["validated_output"], AssetSnapshot)


@pytest.mark.asyncio
async def test_validate_snapshot_parses_markdown_fenced_json() -> None:
    state = {"raw_llm_output": f"```json\n{snapshot_json('MA')}\n```", "errors": []}
    result = await validate_snapshot_node(state)
    output = result["validated_output"]

    assert isinstance(output, AssetSnapshot)
    assert output.asset == "MA"


@pytest.mark.asyncio
async def test_validate_snapshot_fields_are_correct() -> None:
    state = {"raw_llm_output": snapshot_json("MA"), "errors": []}
    result = await validate_snapshot_node(state)
    output = result["validated_output"]
    assert output.asset == "MA"
    assert output.structural_drivers[0].title == "AI demand"
    assert output.structural_risks[0].title == "Supply chain concentration"
    assert output.structural_risks[0].materiality == "high"
    assert output.business_or_asset_profile == "Designs GPUs for gaming and AI."


@pytest.mark.asyncio
async def test_validate_snapshot_accepts_uppercase_materiality() -> None:
    payload = json.loads(snapshot_json("GOOGL"))
    payload["structural_drivers"][0]["materiality"] = "High"
    payload["structural_risks"][0]["materiality"] = "Medium"
    state = {"raw_llm_output": json.dumps(payload), "errors": []}

    result = await validate_snapshot_node(state)
    output = result["validated_output"]

    assert isinstance(output, AssetSnapshot)
    assert output.structural_drivers[0].materiality == "high"
    assert output.structural_risks[0].materiality == "medium"


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_on_invalid_json() -> None:
    state = {"raw_llm_output": "not json at all", "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert any("parse error" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_on_missing_fields() -> None:
    state = {"raw_llm_output": json.dumps({"asset": "NVDA"}), "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"]


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_when_no_output() -> None:
    state = {"raw_llm_output": None, "errors": []}
    result = await validate_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"]
