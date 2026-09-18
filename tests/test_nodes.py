"""
Unit tests for LangGraph nodes.

A LangGraph node is just an async function: (state: dict) -> dict.
LangGraph is NOT involved here — we call each node function directly.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.stock.nodes import (
    ambiguous_asset_resolution_node,
    company_fundamentals_node,
    company_peers_node,
    company_profile_node,
    generate_stock_snapshot_node,
    validate_stock_snapshot_node,
)
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
    StockAssetSnapshot,
)
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext

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


def make_snapshot(asset: str = "NVDA") -> StockAssetSnapshot:
    return StockAssetSnapshot.model_validate(
        {
            "asset": asset,
            "asset_type": "stock",
            "summary": "GPU manufacturer.",
            "market_context": "Semiconductor sector.",
            "business_or_asset_profile": "Designs GPUs for gaming and AI.",
            "peer_landscape": [
                {
                    "ticker": "AMD",
                    "name": "Advanced Micro Devices",
                    "peer_type": "direct_competitor",
                    "relationship_area": "AI accelerators",
                    "why_relevant": (
                        "AMD competes in GPUs and accelerators, which can pressure "
                        "Nvidia pricing and share."
                    ),
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
                    "related_entities": ["AMD"],
                }
            ],
            "data_scope": "profile_with_peers_and_financial_signals",
        }
    )


def make_peer_context(asset: str = "NVDA") -> CompanyPeersContext:
    return CompanyPeersContext(
        asset=asset,
        peers=[
            CompanyPeer(
                ticker="AMD",
                name="Advanced Micro Devices",
            )
        ],
        provider="test",
    )


def make_fundamentals(asset: str = "NVDA") -> CompanyFundamentalsContext:
    return CompanyFundamentalsContext(
        asset=asset,
        provider="test",
        revenue=10.0,
        operating_margin=0.25,
    )


# ── company_profile_node ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_company_profile_returns_context_on_success() -> None:
    profile = make_profile()
    mock_tool = AsyncMock()
    mock_tool.run.return_value = profile

    state = {"request": make_request(), "errors": []}
    result = await company_profile_node(state, mock_tool)
    assert result["asset_profile_context"] == profile


@pytest.mark.asyncio
async def test_company_profile_calls_run_with_correct_args() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.return_value = make_profile()

    state = {
        "request": make_request(asset="NVDA", asset_type=AssetType.STOCK),
        "errors": [],
    }
    await company_profile_node(state, mock_tool)
    mock_tool.run.assert_awaited_once_with(asset="NVDA", asset_type=AssetType.STOCK)


@pytest.mark.asyncio
async def test_company_profile_uses_resolved_asset_when_available() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.return_value = make_profile("AAPL")

    state = {
        "request": make_request(asset="Apple", asset_type=AssetType.STOCK),
        "resolved_asset": "AAPL",
        "errors": [],
    }
    await company_profile_node(state, mock_tool)
    mock_tool.run.assert_awaited_once_with(asset="AAPL", asset_type=AssetType.STOCK)


@pytest.mark.asyncio
async def test_company_profile_handles_tool_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("network error")

    state = {"request": make_request(), "errors": []}
    result = await company_profile_node(state, mock_tool)
    assert result["asset_profile_context"] is None
    assert any("network error" in e for e in result["errors"])


# ── company_fundamentals_node ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_company_fundamentals_node_returns_context_on_success() -> None:
    mock_tool = AsyncMock()
    context = CompanyFundamentalsContext(
        asset="NVDA",
        provider="test",
        revenue=10.0,
    )
    mock_tool.run.return_value = context
    profile = make_profile()

    state = {"asset_profile_context": profile, "errors": []}
    result = await company_fundamentals_node(
        state | {"request": make_request()}, mock_tool
    )

    assert result["company_fundamentals_context"] == context
    mock_tool.run.assert_awaited_once_with(
        asset_profile_context=profile,
    )


@pytest.mark.asyncio
async def test_company_fundamentals_node_handles_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("fundamentals failed")

    state = {"request": make_request(), "asset_profile_context": None, "errors": []}
    result = await company_fundamentals_node(state, mock_tool)

    assert result["company_fundamentals_context"] is None
    assert any("fundamentals failed" in e for e in result["errors"])


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
    result = await company_peers_node(state, mock_tool)

    assert result["company_peers_context"] == peer_context
    mock_tool.run.assert_awaited_once_with(
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
    await company_peers_node(state, mock_tool)

    mock_tool.run.assert_awaited_once_with(
        asset_profile_context=profile,
    )


@pytest.mark.asyncio
async def test_company_peers_tool_handles_exception() -> None:
    mock_tool = AsyncMock()
    mock_tool.run.side_effect = RuntimeError("peer mapping failed")

    state = {"request": make_request(), "asset_profile_context": None, "errors": []}
    result = await company_peers_node(state, mock_tool)

    assert result["company_peers_context"] is None
    assert any("peer mapping failed" in e for e in result["errors"])


# ── generate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_snapshot_stores_only_typed_output() -> None:
    mock_llm = AsyncMock()
    snapshot = make_snapshot()
    mock_llm.generate.return_value = snapshot
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"

    state = {
        "request": make_request(),
        "asset_profile_context": None,
        "company_peers_context": None,
        "company_fundamentals_context": None,
        "errors": [],
    }
    mock_builder.data_scope.return_value = "model_static_knowledge_fallback"
    result = await generate_stock_snapshot_node(state, mock_llm, mock_builder)
    assert result["validated_output"] is snapshot
    assert set(result) == {"validated_output", "data_scope", "generation_prompt"}
    mock_llm.generate.assert_awaited_once_with(
        "prompt", response_schema=StockAssetSnapshot
    )


@pytest.mark.asyncio
async def test_generate_snapshot_passes_profile_context_to_builder() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = make_snapshot()
    mock_builder = MagicMock()
    mock_builder.build_prompt.return_value = "prompt"
    profile = make_profile()
    peer_context = make_peer_context()
    fundamentals = make_fundamentals()

    state = {
        "request": make_request(),
        "asset_profile_context": profile,
        "company_peers_context": peer_context,
        "company_fundamentals_context": fundamentals,
        "errors": [],
    }
    mock_builder.data_scope.return_value = "profile_with_peers_and_financial_signals"
    await generate_stock_snapshot_node(state, mock_llm, mock_builder)

    mock_builder.build_prompt.assert_called_once_with(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        asset_profile_context=profile,
        company_peers_context=peer_context,
        company_fundamentals_context=fundamentals,
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
        "company_fundamentals_context": None,
        "errors": [],
    }
    mock_builder.data_scope.return_value = "model_static_knowledge_fallback"
    result = await generate_stock_snapshot_node(state, mock_llm, mock_builder)
    assert result["validated_output"] is None
    assert any("timeout" in e for e in result["errors"])


# ── validate_snapshot_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_snapshot_preserves_typed_output_without_request() -> None:
    snapshot = make_snapshot()
    state = {"validated_output": snapshot, "errors": []}
    result = await validate_stock_snapshot_node(state)
    assert result["validated_output"] is snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("resolved_asset", [None, "NVDA"])
@pytest.mark.parametrize("data_scope", [None, "profile_only"])
async def test_validate_snapshot_normalizes_workflow_owned_metadata(
    resolved_asset, data_scope
) -> None:
    snapshot = make_snapshot("WRONG").model_copy(
        update={"asset_type": AssetType.ETF, "data_scope": "generated_scope"}
    )
    state = {
        "request": make_request("Nvidia"),
        "resolved_asset": resolved_asset,
        "data_scope": data_scope,
        "validated_output": snapshot,
        "errors": [],
    }

    result = await validate_stock_snapshot_node(state)

    output = result["validated_output"]
    assert isinstance(output, StockAssetSnapshot)
    assert output.asset == (resolved_asset or "NVIDIA")
    assert output.asset_type is AssetType.STOCK
    assert output.data_scope == (data_scope or "generated_scope")
    assert output is not snapshot
    assert snapshot.asset == "WRONG"
    assert snapshot.asset_type is AssetType.ETF
    assert snapshot.data_scope == "generated_scope"
    analytical_fields = {"asset", "asset_type", "data_scope"}
    assert output.model_dump(exclude=analytical_fields) == snapshot.model_dump(
        exclude=analytical_fields
    )


@pytest.mark.asyncio
async def test_validate_snapshot_fields_are_correct() -> None:
    state = {"validated_output": make_snapshot("MA"), "errors": []}
    result = await validate_stock_snapshot_node(state)
    output = result["validated_output"]
    assert output.asset == "MA"
    assert output.structural_drivers[0].title == "AI demand"
    assert output.structural_risks[0].title == "Supply chain concentration"
    assert output.structural_risks[0].materiality == "high"
    assert output.business_or_asset_profile == "Designs GPUs for gaming and AI."


@pytest.mark.asyncio
async def test_finalization_does_not_serialize_or_revalidate(monkeypatch) -> None:
    snapshot = make_snapshot()
    state = {
        "request": make_request(),
        "validated_output": snapshot,
        "data_scope": "profile_only",
        "errors": [],
    }

    def unexpected_round_trip(*args, **kwargs):
        raise AssertionError("Finalization must use the already-validated object")

    for method in ("model_dump_json", "model_validate_json", "model_validate"):
        monkeypatch.setattr(StockAssetSnapshot, method, unexpected_round_trip)

    result = await validate_stock_snapshot_node(state)

    assert isinstance(result["validated_output"], StockAssetSnapshot)
    assert result["validated_output"].asset == "NVDA"
    assert "errors" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_output", ["not a model", {"asset": "NVDA"}])
async def test_validate_snapshot_rejects_untyped_state(invalid_output) -> None:
    state = {"validated_output": invalid_output, "errors": ["earlier error"]}
    result = await validate_stock_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"][0] == "earlier error"
    assert any("Expected a validated StockAssetSnapshot" in e for e in result["errors"])


@pytest.mark.asyncio
@pytest.mark.parametrize("has_peers", [True, False])
@pytest.mark.parametrize("empty_landscape", [True, False])
async def test_validate_snapshot_warns_only_when_supplied_peers_are_omitted(
    has_peers, empty_landscape, caplog
) -> None:
    snapshot = make_snapshot()
    if empty_landscape:
        snapshot = snapshot.model_copy(update={"peer_landscape": []})
    state = {
        "request": make_request(),
        "validated_output": snapshot,
        "company_peers_context": make_peer_context() if has_peers else None,
        "errors": [],
    }
    result = await validate_stock_snapshot_node(state)
    assert result["validated_output"] is not None
    assert result["validated_output"].peer_landscape == snapshot.peer_landscape
    assert "errors" not in result
    assert ("stock.validate_snapshot.empty_landscape" in caplog.text) == (
        has_peers and empty_landscape
    )


@pytest.mark.asyncio
async def test_validate_snapshot_returns_none_when_no_output() -> None:
    state = {"validated_output": None, "errors": ["generation failed"]}
    result = await validate_stock_snapshot_node(state)
    assert result["validated_output"] is None
    assert result["errors"][0] == "generation failed"
