import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.asset_snapshot.router.graph import AssetSnapshotRouterGraph
from app.agents.asset_snapshot.router.routing import route_asset_type
from app.agents.asset_snapshot.stock.graph import StockSnapshotSubgraph
from app.core.exceptions import UnsupportedAssetTypeError
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


def make_request(
    asset: str = "NVDA",
    asset_type: AssetType = AssetType.STOCK,
) -> AssetSnapshotRequest:
    return AssetSnapshotRequest(asset=asset, asset_type=asset_type)


def make_profile(
    asset: str = "NVDA",
    provider: str = "yfinance",
) -> AssetProfileContext:
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
        provider=provider,
    )


def make_peers(asset: str = "NVDA") -> CompanyPeersContext:
    return CompanyPeersContext(
        asset=asset,
        provider="fmp",
        peers=[CompanyPeer(ticker="AMD", name="Advanced Micro Devices")],
    )


def make_empty_peers(asset: str = "NVDA") -> CompanyPeersContext:
    return CompanyPeersContext(asset=asset, provider="fmp_unavailable", peers=[])


def make_fundamentals(asset: str = "NVDA") -> CompanyFundamentalsContext:
    return CompanyFundamentalsContext(
        asset=asset,
        provider="fmp",
        revenue=100.0,
        operating_margin=0.3,
    )


def make_empty_fundamentals(asset: str = "NVDA") -> CompanyFundamentalsContext:
    return CompanyFundamentalsContext(asset=asset, provider="fmp_unavailable")


def llm_response(
    asset: str = "NVDA",
    data_scope: str = "profile_only",
) -> str:
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
            "data_scope": data_scope,
        }
    )


@pytest.fixture
def mock_profile_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_profile()
    return tool


@pytest.fixture
def mock_company_peers_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_peers()
    return tool


@pytest.fixture
def mock_fundamentals_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = make_fundamentals()
    return tool


@pytest.fixture
def mock_prompt_builder() -> MagicMock:
    builder = MagicMock()
    builder.build_prompt.return_value = "mocked prompt"
    builder.data_scope.return_value = "profile_with_peers_and_financial_signals"
    return builder


@pytest.fixture
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.generate.return_value = llm_response(
        data_scope="profile_with_peers_and_financial_signals"
    )
    return llm


def build_stock_subgraph(
    profile_tool: AsyncMock,
    peers_tool: AsyncMock,
    fundamentals_tool: AsyncMock,
    prompt_builder: MagicMock,
    llm: AsyncMock,
) -> StockSnapshotSubgraph:
    return StockSnapshotSubgraph(
        company_profile_tool=profile_tool,
        company_peers_tool=peers_tool,
        company_fundamentals_tool=fundamentals_tool,
        prompt_builder=prompt_builder,
        llm_client=llm,
    )


@pytest.mark.asyncio
async def test_router_routes_stock_to_stock_subgraph() -> None:
    stock_subgraph = AsyncMock()
    stock_subgraph.ainvoke.return_value = {
        "validated_output": StockAssetSnapshot.model_validate(
            json.loads(llm_response(data_scope="profile_only"))
        ),
        "errors": [],
    }
    router = AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_subgraph)

    final_state = await router.ainvoke({"request": make_request()})

    stock_subgraph.ainvoke.assert_awaited_once()
    assert isinstance(final_state["validated_output"], StockAssetSnapshot)


@pytest.mark.asyncio
async def test_router_returns_stock_subgraph_validated_output() -> None:
    output = StockAssetSnapshot.model_validate(
        json.loads(llm_response(data_scope="profile_only"))
    )
    stock_subgraph = AsyncMock()
    stock_subgraph.ainvoke.return_value = {"validated_output": output, "errors": []}
    router = AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_subgraph)

    final_state = await router.ainvoke({"request": make_request()})

    assert final_state["validated_output"] == output


@pytest.mark.asyncio
async def test_router_freezes_exact_stock_contexts_as_evidence() -> None:
    output = StockAssetSnapshot.model_validate(
        json.loads(llm_response(data_scope="profile_with_peers_and_financial_signals"))
    )
    profile = make_profile()
    peers = make_peers()
    fundamentals = make_fundamentals()
    stock_subgraph = AsyncMock()
    stock_subgraph.ainvoke.return_value = {
        "validated_output": output,
        "asset_profile_context": profile,
        "company_peers_context": peers,
        "company_fundamentals_context": fundamentals,
        "data_scope": output.data_scope,
        "errors": [],
    }
    router = AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_subgraph)

    final_state = await router.ainvoke({"request": make_request()})

    evidence = final_state["snapshot_evidence"]
    assert evidence is not None
    assert evidence.asset_profile_context == profile
    assert evidence.company_peers_context == peers
    assert evidence.company_fundamentals_context == fundamentals
    assert evidence.data_scope == output.data_scope


@pytest.mark.asyncio
async def test_router_unsupported_asset_type_raises_controlled_error() -> None:
    stock_subgraph = AsyncMock()
    router = AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_subgraph)

    with pytest.raises(UnsupportedAssetTypeError):
        await router.ainvoke(
            {"request": make_request(asset="SPY", asset_type=AssetType.ETF)}
        )

    stock_subgraph.ainvoke.assert_not_awaited()


def test_router_state_does_not_expose_stock_intermediate_contexts() -> None:
    state = route_asset_type({"request": make_request()})

    assert "asset_profile_context" not in state
    assert "company_peers_context" not in state
    assert "company_fundamentals_context" not in state
    assert "raw_llm_output" not in state


def test_router_module_contains_no_vendor_behavior() -> None:
    import app.agents.asset_snapshot.router.graph as router_graph

    source_names = set(router_graph.__dict__)

    assert "YFinanceCompanyProfileProvider" not in source_names
    assert "FmpProvider" not in source_names
    assert "StockSnapshotPromptBuilder" not in source_names


@pytest.mark.asyncio
async def test_stock_subgraph_runs_capability_nodes(
    mock_profile_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_fundamentals_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    subgraph = build_stock_subgraph(
        mock_profile_tool,
        mock_company_peers_tool,
        mock_fundamentals_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await subgraph.ainvoke({"request": make_request(), "errors": []})

    mock_profile_tool.run.assert_awaited_once()
    mock_company_peers_tool.run.assert_awaited_once()
    mock_fundamentals_tool.run.assert_awaited_once()
    mock_llm.generate.assert_awaited_once()
    assert isinstance(final_state["validated_output"], StockAssetSnapshot)


@pytest.mark.asyncio
async def test_stock_subgraph_no_profile_continues_with_model_fallback(
    mock_profile_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_fundamentals_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_profile_tool.run.return_value = None
    mock_prompt_builder.data_scope.return_value = "model_static_knowledge_fallback"
    mock_llm.generate.return_value = llm_response(
        data_scope="model_static_knowledge_fallback"
    )
    subgraph = build_stock_subgraph(
        mock_profile_tool,
        mock_company_peers_tool,
        mock_fundamentals_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await subgraph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["data_scope"] == "model_static_knowledge_fallback"
    assert isinstance(final_state["validated_output"], StockAssetSnapshot)


@pytest.mark.asyncio
async def test_stock_subgraph_empty_peers_and_fundamentals_continue(
    mock_profile_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_fundamentals_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_company_peers_tool.run.return_value = make_empty_peers()
    mock_fundamentals_tool.run.return_value = make_empty_fundamentals()
    mock_prompt_builder.data_scope.return_value = "profile_only"
    mock_llm.generate.return_value = llm_response(data_scope="profile_only")
    subgraph = build_stock_subgraph(
        mock_profile_tool,
        mock_company_peers_tool,
        mock_fundamentals_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await subgraph.ainvoke({"request": make_request(), "errors": []})

    assert isinstance(final_state["validated_output"], StockAssetSnapshot)


@pytest.mark.asyncio
async def test_stock_subgraph_malformed_llm_json_records_controlled_error(
    mock_profile_tool: AsyncMock,
    mock_company_peers_tool: AsyncMock,
    mock_fundamentals_tool: AsyncMock,
    mock_prompt_builder: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    mock_llm.generate.return_value = "not valid json"
    subgraph = build_stock_subgraph(
        mock_profile_tool,
        mock_company_peers_tool,
        mock_fundamentals_tool,
        mock_prompt_builder,
        mock_llm,
    )

    final_state = await subgraph.ainvoke({"request": make_request(), "errors": []})

    assert final_state["validated_output"] is None
    assert final_state["errors"]
