"""Synthetic contract examples only; no research, pricing, or valuation execution."""

import asyncio
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.asset_thesis.graph import AssetThesisGraph
from app.agents.asset_thesis.runner import AssetThesisGraphRunner
from app.agents.asset_thesis.state import PreparedThesisData
from app.agents.asset_thesis.subgraphs import (
    ThesisAssetOverviewGraph,
    ThesisCatalystsGraph,
    ThesisDataPreparationGraph,
)
from app.api.dependencies import (
    get_asset_thesis_graph,
    get_asset_thesis_graph_runner,
    get_asset_thesis_service,
)
from app.core.exceptions import AssetThesisNotImplementedError, ServiceError
from app.domain.schemas.asset_snapshot import AssetSnapshotRequest
from app.domain.schemas.asset_thesis import (
    AssetThesisRequest,
    DcfAssumptionBasis,
    DcfAssumptions,
    DcfSensitivityPoint,
    FinancialValue,
    StockAssetThesis,
    ThesisFinancialInput,
    ThesisReferencePrice,
)
from app.main import create_app
from app.services.asset_thesis_service import AssetThesisService


@pytest.fixture
def assumptions_payload():
    return {
        "discount_rate": 0.10,
        "terminal_growth_rate": 0.02,
        "forecast_years": [
            {
                "year": year,
                "revenue_growth": 0.03,
                "operating_margin": 0.20,
                "tax_rate": 0.21,
                "depreciation_and_amortization_to_revenue": 0.04,
                "capital_expenditures_to_revenue": 0.05,
                "change_in_working_capital_to_revenue": 0.01,
            }
            for year in range(1, 6)
        ],
    }


@pytest.fixture
def thesis_payload(assumptions_payload):
    missing = {"value": None, "unavailable_reason": "Incomplete financial history."}
    limitation = {
        "text": "Only one annual revenue fact is available.",
        "evidence_ids": [],
    }
    coverage = {
        "status": "unavailable",
        "explanation": "No usable document in this synthetic corpus.",
        "evidence_ids": [],
    }
    return {
        "asset": "EXAMPLE",
        "asset_type": "stock",
        "company_name": "Synthetic Example Inc.",
        "cik": "0000000001",
        "researched_at": "2026-09-27T10:00:00Z",
        "data_coverage": {
            "latest_10k": {
                "status": "complete",
                "explanation": "Annual filing indexed.",
                "evidence_ids": ["filing-2025-business"],
            },
            "subsequent_10q": coverage,
            "recent_8k_and_html_exhibits": coverage,
            "company_facts": {
                "status": "partial",
                "explanation": "Only one year of revenue is available.",
                "evidence_ids": ["fact-2025-revenue"],
            },
            "market_price": {
                "status": "complete",
                "explanation": "One USD quote.",
                "evidence_ids": ["quote-example"],
            },
            "complete_financial_years": [2025],
            "limitations": ["Incomplete historical financial inputs."],
        },
        "short_thesis_overview": {
            "investment_thesis": {
                "text": "Recurring contracts may support stable cash flows.",
                "evidence_ids": ["filing-2025-business"],
            },
            "valuation_conclusion": "uncertain",
            "valuation_rationale": limitation,
            "principal_limitations": [limitation],
        },
        "asset_overview": {
            "business_description": {
                "text": "Provides contract services.",
                "evidence_ids": ["filing-2025-business"],
            },
            "main_economic_drivers": [
                {
                    "text": "Contract renewals support demand.",
                    "evidence_ids": ["filing-2025-business"],
                }
            ],
            "historical_financial_context": [
                {
                    "text": "Annual revenue was USD 100.",
                    "evidence_ids": ["fact-2025-revenue"],
                }
            ],
        },
        "valuation": {
            "historical_base": [
                {
                    "metric": "revenue",
                    "value": 100,
                    "unit": "USD",
                    "period_start": "2025-01-01",
                    "period_end": "2025-12-31",
                    "evidence_ids": ["fact-2025-revenue"],
                }
            ],
            "assumptions": {
                "config_version": "synthetic-policy-v1",
                "values": assumptions_payload,
            },
            "reference_price": {
                "value": 10,
                "as_of": "2026-09-25T20:00:00Z",
                "evidence_ids": ["quote-example"],
            },
            "calculated_results": {
                "forecast_fcff": [missing] * 5,
                "terminal_value": missing,
                "enterprise_value": missing,
                "equity_value": missing,
                "intrinsic_value_per_share": missing,
                "upside_downside": missing,
            },
            "sensitivity": [],
            "limitations": [limitation],
        },
        "current_catalysts": [],
        "thesis_risks_and_invalidation": {
            "risks": [
                {
                    "observable_risk": "Customer renewals may weaken.",
                    "uncertainty": "Renewal rates are not disclosed.",
                    "affected_assumptions": ["Forecast revenue growth"],
                    "reassessment_signals": ["Disclosure of material contract losses"],
                    "evidence_ids": ["filing-2025-business"],
                }
            ],
            "uncertainties": [limitation],
        },
        "sources_and_evidence": [
            {
                "kind": "filing",
                "evidence_id": "filing-2025-business",
                "url": "https://example.test/annual-report.html",
                "retrieved_at": "2026-09-27T09:00:00Z",
                "form": "10-K",
                "accession_number": "0000000001-26-000001",
                "filed_on": "2026-02-01",
                "passage_locator": "item-1/chunk-1",
            },
            {
                "kind": "company_fact",
                "evidence_id": "fact-2025-revenue",
                "url": "https://example.test/companyfacts.json",
                "retrieved_at": "2026-09-27T09:00:00Z",
                "accession_number": "0000000001-26-000001",
                "filed_on": "2026-02-01",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "unit": "USD",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "value": 100,
            },
            {
                "kind": "market_price",
                "evidence_id": "quote-example",
                "url": "https://example.test/quote",
                "retrieved_at": "2026-09-27T09:00:00Z",
                "provider": "Synthetic quote fixture",
                "price_as_of": "2026-09-25T20:00:00Z",
            },
        ],
    }


@pytest.fixture
def prepared_data(thesis_payload):
    return PreparedThesisData.model_validate(
        {
            "filings_index": {"artifact_id": "filings", "version": "v1"},
            "financials": {"artifact_id": "facts", "version": "v1"},
            "quote": {"artifact_id": "quote", "version": "v1"},
            "coverage": thesis_payload["data_coverage"],
            "data_gaps": ["Two historical years are missing."],
        }
    )


def snapshot_context(asset="EXAMPLE"):
    return {
        "asset": asset,
        "asset_type": "stock",
        "summary": "Synthetic context.",
        "business_or_asset_profile": "Contract services.",
        "market_context": "Services.",
        "peer_landscape": [],
        "structural_drivers": [],
        "structural_risks": [],
        "data_scope": "profile_only",
    }


def test_request_matches_snapshot_normalization_and_is_standalone():
    payload = {"asset": " nvda ", "asset_type": "stock"}
    request = AssetThesisRequest.model_validate(payload)
    assert request.asset == AssetSnapshotRequest.model_validate(payload).asset == "NVDA"
    assert request.snapshot_context is None
    assert "assumptions" not in AssetThesisRequest.model_fields


@pytest.mark.parametrize("asset", ["", "   ", "A" * 33, None, 123])
def test_request_rejects_invalid_asset(asset):
    with pytest.raises(ValidationError):
        AssetThesisRequest.model_validate({"asset": asset, "asset_type": "stock"})


def test_optional_snapshot_is_same_asset_context():
    request = AssetThesisRequest.model_validate(
        {
            "asset": " example ",
            "asset_type": "stock",
            "snapshot_context": snapshot_context(),
        }
    )
    assert request.snapshot_context.asset == request.asset
    with pytest.raises(ValidationError, match="requested stock"):
        AssetThesisRequest.model_validate(
            {
                "asset": "OTHER",
                "asset_type": "stock",
                "snapshot_context": snapshot_context(),
            }
        )


def test_request_rejects_caller_supplied_dcf_assumptions(assumptions_payload):
    with pytest.raises(ValidationError, match="assumptions"):
        AssetThesisRequest.model_validate(
            {
                "asset": "EXAMPLE",
                "asset_type": "stock",
                "assumptions": assumptions_payload,
            }
        )


@pytest.mark.parametrize(
    "conclusion", ["undervalued", "fairly_valued", "overvalued", "uncertain"]
)
def test_response_roundtrips_all_research_conclusions(thesis_payload, conclusion):
    thesis_payload["short_thesis_overview"]["valuation_conclusion"] = conclusion
    thesis = StockAssetThesis.model_validate(thesis_payload)
    assert StockAssetThesis.model_validate_json(thesis.model_dump_json()) == thesis
    assert thesis.current_catalysts == []
    assert thesis.valuation.calculated_results.equity_value.value is None
    assert "snapshot_context" not in thesis.model_dump()


@pytest.mark.parametrize(
    "kind", ["duplicate", "claim", "financial_input", "coverage", "price", "risk"]
)
def test_response_rejects_invalid_evidence_references(thesis_payload, kind):
    if kind == "duplicate":
        thesis_payload["sources_and_evidence"].append(
            deepcopy(thesis_payload["sources_and_evidence"][0])
        )
        message = "unique"
    else:
        locations = {
            "claim": thesis_payload["asset_overview"]["business_description"],
            "financial_input": thesis_payload["valuation"]["historical_base"][0],
            "coverage": thesis_payload["data_coverage"]["latest_10k"],
            "price": thesis_payload["valuation"]["reference_price"],
            "risk": thesis_payload["thesis_risks_and_invalidation"]["risks"][0],
        }
        locations[kind]["evidence_ids"] = ["missing"]
        message = "Unknown evidence IDs"
    with pytest.raises(ValidationError, match=message):
        StockAssetThesis.model_validate(thesis_payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"value": None},
        {"value": None, "unavailable_reason": "  "},
        {"value": 1, "unavailable_reason": "missing"},
        {"value": float("nan")},
        {"value": float("inf")},
    ],
)
def test_missing_financial_values_require_explanations_and_finite_numbers(payload):
    with pytest.raises(ValidationError):
        FinancialValue.model_validate(payload)


def test_zero_and_unavailable_values_remain_distinct():
    assert FinancialValue(value=0).value == 0
    assert FinancialValue(value=None, unavailable_reason="No quote.").value is None


def test_missing_assumptions_require_an_explanation(thesis_payload):
    thesis_payload["valuation"]["assumptions"] = None
    with pytest.raises(ValidationError, match="missing assumptions"):
        StockAssetThesis.model_validate(thesis_payload)
    thesis_payload["valuation"]["assumptions_unavailable_reason"] = (
        "No approved assumptions."
    )
    assert StockAssetThesis.model_validate(thesis_payload).valuation.assumptions is None


def test_fixed_dcf_and_versioned_assumptions(assumptions_payload):
    with pytest.raises(ValidationError, match="config_version"):
        DcfAssumptionBasis.model_validate({"values": assumptions_payload})
    basis = DcfAssumptionBasis(config_version="test-v1", values=assumptions_payload)
    assert basis.config_version == "test-v1"
    assumptions_payload["terminal_growth_rate"] = 0.10
    with pytest.raises(ValidationError, match="below"):
        DcfAssumptions.model_validate(assumptions_payload)
    assumptions_payload["terminal_growth_rate"] = 0.02
    assumptions_payload["forecast_years"][4]["year"] = 4
    with pytest.raises(ValidationError, match="years 1 through 5"):
        DcfAssumptions.model_validate(assumptions_payload)


def test_invalid_sensitivity_can_only_be_reported_as_unavailable():
    payload = {
        "discount_rate": 0.02,
        "terminal_growth_rate": 0.02,
        "intrinsic_value_per_share": {"value": 10},
    }
    with pytest.raises(ValidationError, match="requires null"):
        DcfSensitivityPoint.model_validate(payload)
    payload["intrinsic_value_per_share"] = {
        "value": None,
        "unavailable_reason": "Growth equals WACC.",
    }
    assert (
        DcfSensitivityPoint.model_validate(payload).intrinsic_value_per_share.value
        is None
    )


def test_financial_inputs_need_evidence_and_correct_units(thesis_payload):
    financial_input = thesis_payload["valuation"]["historical_base"][0]
    financial_input["evidence_ids"] = []
    with pytest.raises(ValidationError, match="require evidence"):
        ThesisFinancialInput.model_validate(financial_input)
    financial_input["evidence_ids"] = ["fact-2025-revenue"]
    financial_input["unit"] = "shares"
    with pytest.raises(ValidationError, match="must use USD"):
        ThesisFinancialInput.model_validate(financial_input)


@pytest.mark.parametrize(
    "changes",
    [
        {"as_of": None},
        {"as_of": "2026-09-25T20:00:00"},
        {"evidence_ids": []},
        {"value": 0},
    ],
)
def test_available_price_requires_timestamp_and_source(thesis_payload, changes):
    price = thesis_payload["valuation"]["reference_price"] | changes
    with pytest.raises(ValidationError):
        ThesisReferencePrice.model_validate(price)


@pytest.mark.asyncio
async def test_service_signals_unimplemented_without_http_or_research_output():
    graph = get_asset_thesis_graph()
    runner = get_asset_thesis_graph_runner(thesis_graph=graph)
    service = get_asset_thesis_service(graph_runner=runner)
    assert isinstance(service, AssetThesisService)
    with pytest.raises(AssetThesisNotImplementedError) as caught:
        await service.get_thesis(
            AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
        )
    assert not isinstance(caught.value, (HTTPException, ServiceError))


def test_thesis_dependency_chain_injects_graph_into_runner_and_service():
    graph = get_asset_thesis_graph()
    runner = get_asset_thesis_graph_runner(thesis_graph=graph)
    service = get_asset_thesis_service(graph_runner=runner)

    assert isinstance(graph, AssetThesisGraph)
    assert isinstance(runner, AssetThesisGraphRunner)
    assert runner._thesis_graph is graph
    assert service.graph_runner is runner


@pytest.mark.asyncio
async def test_thesis_runner_passes_request_state_and_returns_validated_response(
    thesis_payload,
):
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
    thesis = StockAssetThesis.model_validate(thesis_payload)
    graph = AsyncMock(spec=AssetThesisGraph)
    graph.ainvoke.return_value = {"request": request, "final_response": thesis}
    runner = AssetThesisGraphRunner(thesis_graph=graph)

    result = await runner.run(request)

    graph.ainvoke.assert_awaited_once_with({"request": request})
    assert result is thesis


@pytest.mark.parametrize(
    "final_state", [{}, {"final_response": None, "error": "failed"}]
)
@pytest.mark.asyncio
async def test_thesis_runner_rejects_completed_state_without_response(final_state):
    graph = AsyncMock(spec=AssetThesisGraph)
    graph.ainvoke.return_value = final_state
    runner = AssetThesisGraphRunner(thesis_graph=graph)

    with pytest.raises(ServiceError, match="Asset thesis generation failed"):
        await runner.run(AssetThesisRequest(asset="EXAMPLE", asset_type="stock"))


@pytest.mark.asyncio
async def test_thesis_service_delegates_request_to_runner(thesis_payload):
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
    thesis = StockAssetThesis.model_validate(thesis_payload)
    runner = AsyncMock(spec=AssetThesisGraphRunner)
    runner.run.return_value = thesis
    service = AssetThesisService(graph_runner=runner)

    result = await service.get_thesis(request)

    runner.run.assert_awaited_once_with(request)
    assert result is thesis


@pytest.mark.asyncio
async def test_thesis_service_propagates_runner_failure():
    runner = AsyncMock(spec=AssetThesisGraphRunner)
    runner.run.side_effect = ServiceError("Research failed.")
    service = AssetThesisService(graph_runner=runner)

    with pytest.raises(ServiceError, match="Research failed"):
        await service.get_thesis(
            AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
        )


@pytest.mark.asyncio
async def test_parent_initialization_freezes_research_identity_and_time():
    graph = AssetThesisGraph()
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")

    first = await graph.initialize_research({"request": request})
    second = await graph.initialize_research({"request": request, **first})

    assert first == second
    assert first["asset"] == "EXAMPLE"
    assert UUID(hex=first["research_id"]).hex == first["research_id"]
    assert first["as_of"].tzinfo is not None
    assert first["as_of"].utcoffset() == datetime.now(UTC).utcoffset()


@pytest.mark.parametrize(
    "partial_state",
    [
        {"research_id": "existing"},
        {"as_of": datetime(2026, 10, 1, tzinfo=UTC)},
        {"research_id": "existing", "as_of": datetime(2026, 10, 1)},
        {"research_id": "  ", "as_of": datetime(2026, 10, 1, tzinfo=UTC)},
    ],
)
@pytest.mark.asyncio
async def test_parent_initialization_rejects_incomplete_or_naive_resume(partial_state):
    graph = AssetThesisGraph()
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")

    with pytest.raises(ServiceError):
        await graph.initialize_research({"request": request, **partial_state})


@pytest.mark.parametrize("with_snapshot", [False, True])
@pytest.mark.asyncio
async def test_subgraph_wrappers_project_only_required_inputs_and_selected_outputs(
    thesis_payload, prepared_data, with_snapshot
):
    thesis = StockAssetThesis.model_validate(thesis_payload)
    preparation = AsyncMock(spec=ThesisDataPreparationGraph)
    overview = AsyncMock(spec=ThesisAssetOverviewGraph)
    catalysts = AsyncMock(spec=ThesisCatalystsGraph)
    preparation.ainvoke.return_value = {
        "prepared_data": prepared_data,
        "internal_chunks": ["not parent state"],
    }
    overview.ainvoke.return_value = {
        "result": thesis.asset_overview,
        "internal_passages": ["not parent state"],
    }
    catalysts.ainvoke.return_value = {"result": [], "internal_passages": []}
    graph = AssetThesisGraph(
        data_preparation=preparation,
        asset_overview=overview,
        catalysts=catalysts,
    )
    payload = {"asset": "EXAMPLE", "asset_type": "stock"}
    if with_snapshot:
        payload["snapshot_context"] = snapshot_context()
    request = AssetThesisRequest.model_validate(payload)
    state = {
        "request": request,
        **await graph.initialize_research({"request": request}),
    }

    preparation_update = await graph.prepare_data(state)
    preparation.ainvoke.assert_awaited_once_with(
        {
            "asset": "EXAMPLE",
            "research_id": state["research_id"],
            "as_of": state["as_of"],
        }
    )
    assert preparation_update == {"prepared_data": prepared_data}

    state.update(preparation_update)
    overview_update = await graph.run_asset_overview(state)
    expected_overview_input = {
        "asset": "EXAMPLE",
        "as_of": state["as_of"],
        "prepared_data": prepared_data,
    }
    if with_snapshot:
        expected_overview_input["snapshot_context"] = request.snapshot_context
    overview.ainvoke.assert_awaited_once_with(expected_overview_input)
    assert overview_update == {"asset_overview": thesis.asset_overview}

    catalyst_update = await graph.run_current_catalysts(state)
    catalysts.ainvoke.assert_awaited_once_with(
        {
            "asset": "EXAMPLE",
            "as_of": state["as_of"],
            "prepared_data": prepared_data,
        }
    )
    assert catalyst_update == {"current_catalysts": []}


@pytest.mark.parametrize("stage", ["preparation", "overview", "catalysts"])
@pytest.mark.asyncio
async def test_subgraph_wrappers_reject_missing_results(stage, prepared_data):
    preparation = AsyncMock(spec=ThesisDataPreparationGraph)
    overview = AsyncMock(spec=ThesisAssetOverviewGraph)
    catalysts = AsyncMock(spec=ThesisCatalystsGraph)
    preparation.ainvoke.return_value = {}
    overview.ainvoke.return_value = {}
    catalysts.ainvoke.return_value = {}
    graph = AssetThesisGraph(
        data_preparation=preparation,
        asset_overview=overview,
        catalysts=catalysts,
    )
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
    state = {
        "request": request,
        "asset": request.asset,
        "research_id": "research-1",
        "as_of": datetime(2026, 10, 1, tzinfo=UTC),
        "prepared_data": prepared_data,
    }
    node = {
        "preparation": graph.prepare_data,
        "overview": graph.run_asset_overview,
        "catalysts": graph.run_current_catalysts,
    }[stage]

    with pytest.raises(ServiceError, match="produced no valid result"):
        await node(state)


@pytest.mark.asyncio
async def test_parent_graph_joins_all_analysis_branches_once(
    thesis_payload, prepared_data
):
    thesis = StockAssetThesis.model_validate(thesis_payload)
    preparation = AsyncMock(spec=ThesisDataPreparationGraph)
    overview = AsyncMock(spec=ThesisAssetOverviewGraph)
    catalysts = AsyncMock(spec=ThesisCatalystsGraph)
    preparation.ainvoke.return_value = {"prepared_data": prepared_data}
    overview.ainvoke.return_value = {"result": thesis.asset_overview}
    catalyst_started = asyncio.Event()
    release_catalysts = asyncio.Event()
    valuation_finished = asyncio.Event()
    risk_calls = []

    async def delayed_catalysts(_state):
        catalyst_started.set()
        await release_catalysts.wait()
        return {"result": []}

    catalysts.ainvoke.side_effect = delayed_catalysts

    class CompletedGraph(AssetThesisGraph):
        async def valuation(self, state):
            assert state["prepared_data"] is prepared_data
            valuation_finished.set()
            return {"valuation": thesis.valuation}

        async def thesis_risks_and_invalidation(self, state):
            assert state["asset_overview"] is thesis.asset_overview
            assert state["valuation"] is thesis.valuation
            assert state["current_catalysts"] == []
            risk_calls.append(1)
            return {
                "thesis_risks_and_invalidation": thesis.thesis_risks_and_invalidation
            }

        async def short_thesis_overview(self, state):
            assert len(risk_calls) == 1
            return {"short_thesis_overview": thesis.short_thesis_overview}

        async def assemble_and_validate(self, state):
            assert state["short_thesis_overview"] is thesis.short_thesis_overview
            return {"final_response": thesis}

        async def persist_thesis(self, state):
            assert state["final_response"] is thesis
            return {"final_response": thesis}

    graph = CompletedGraph(
        data_preparation=preparation,
        asset_overview=overview,
        catalysts=catalysts,
    )
    request = AssetThesisRequest(asset="EXAMPLE", asset_type="stock")
    execution = asyncio.create_task(graph.ainvoke({"request": request}))
    try:
        await asyncio.wait_for(
            asyncio.gather(catalyst_started.wait(), valuation_finished.wait()),
            timeout=5,
        )
        assert risk_calls == []
    finally:
        release_catalysts.set()
    final_state = await asyncio.wait_for(execution, timeout=5)

    assert risk_calls == [1]
    assert final_state["final_response"] is thesis
    assert final_state["prepared_data"] is prepared_data


def test_import_registration_openapi_and_501_without_clients():
    # Fresh process proves import-time behavior as well as request dependency wiring.
    script = """
from unittest.mock import patch
from contextlib import ExitStack
from fastapi.testclient import TestClient
from app.llm.ollama_client import OllamaChatClient
from app.market_data.fmp_provider import FmpProvider
from app.market_data.yfinance_provider import YFinanceCompanyProfileProvider
from app.infrastructure.db.database import Database
with ExitStack() as stack:
    clients = (OllamaChatClient, FmpProvider, YFinanceCompanyProfileProvider, Database)
    for client in clients:
        stack.enter_context(patch.object(
            client, "__init__", side_effect=AssertionError("Client constructed")
        ))
    from app.main import create_app
    from app.domain.schemas.asset_thesis import StockAssetThesis
    app = create_app()
    operation = app.openapi()["paths"]["/api/v1/asset/thesis"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/StockAssetThesis")
    assert "501" in operation["responses"]
    assert StockAssetThesis.model_json_schema()["properties"]["valuation"]
    response = TestClient(app).post(
        "/api/v1/asset/thesis", json={"asset": "example", "asset_type": "stock"}
    )
    assert response.status_code == 501, response.text
    assert response.json() == {
        "detail": "Asset thesis research is not implemented yet."
    }
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"asset": "EXAMPLE"},
        {"asset": " ", "asset_type": "stock"},
        {"asset": "X" * 33, "asset_type": "stock"},
        {"asset": "SPY", "asset_type": "etf"},
        {"asset": "BTC", "asset_type": "crypto"},
        {"asset": "EXAMPLE", "asset_type": "stock", "assumptions": {}},
    ],
)
def test_endpoint_rejects_invalid_requests_before_service_call(payload):
    app = create_app()
    service = AsyncMock()
    app.dependency_overrides[get_asset_thesis_service] = lambda: service
    response = TestClient(app).post("/api/v1/asset/thesis", json=payload)
    assert response.status_code == 422
    service.get_thesis.assert_not_awaited()


@pytest.mark.parametrize("with_snapshot", [False, True])
def test_endpoint_delegates_and_preserves_response_shape(thesis_payload, with_snapshot):
    thesis = StockAssetThesis.model_validate(thesis_payload)
    service = AsyncMock()
    service.get_thesis.return_value = thesis
    app = create_app()
    app.dependency_overrides[get_asset_thesis_service] = lambda: service
    payload = {"asset": " example ", "asset_type": "stock"}
    if with_snapshot:
        payload["snapshot_context"] = snapshot_context()
    response = TestClient(app).post("/api/v1/asset/thesis", json=payload)
    assert response.status_code == 200
    assert response.json() == thesis.model_dump(mode="json")
    service.get_thesis.assert_awaited_once_with(
        AssetThesisRequest.model_validate(payload)
    )


def test_execution_failure_is_distinct_from_unimplemented_and_uncertain():
    service = AsyncMock()
    service.get_thesis.side_effect = ServiceError("Thesis research failed.")
    app = create_app()
    app.dependency_overrides[get_asset_thesis_service] = lambda: service
    response = TestClient(app).post(
        "/api/v1/asset/thesis", json={"asset": "EXAMPLE", "asset_type": "stock"}
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "Thesis research failed."}
