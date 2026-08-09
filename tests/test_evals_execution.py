import argparse
import inspect
import json
import logging
from pathlib import Path

import pytest

import evals.asset_snapshot.frozen as frozen_module
from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.frozen import build_frozen_execution
from evals.asset_snapshot.models import JudgeEvidence, SemanticMetricResult
from evals.asset_snapshot.reporting import write_report
from evals.asset_snapshot.run import (
    NO_APPROVED_CASES_MESSAGE,
    build_parser,
    run_from_args,
)
from evals.asset_snapshot.runner import StockSnapshotEvaluator


class FakeGenerationClient(BaseChatModelClient):
    def __init__(self, asset: str, data_scope: str) -> None:
        self.asset = asset
        self.data_scope = data_scope
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "fake-generation"

    async def generate(self, message: str) -> str:
        self.calls += 1
        return json.dumps(
            {
                "asset": self.asset,
                "asset_type": "stock",
                "summary": "A synthetic company with a defined business model.",
                "business_or_asset_profile": (
                    "The company earns recurring revenue from its supplied "
                    "business activity."
                ),
                "market_context": "It operates in the supplied industry context.",
                "competitive_landscape": [],
                "structural_drivers": [
                    {
                        "title": "Durable demand",
                        "explanation": "Demand supports recurring revenue.",
                        "materiality": "medium",
                    }
                ],
                "structural_risks": [
                    {
                        "title": "Competition",
                        "explanation": (
                            "Substitutes can reduce customer retention and pressure "
                            "revenue growth."
                        ),
                        "materiality": "medium",
                        "related_competitors": [],
                    }
                ],
                "data_scope": self.data_scope,
            }
        )


def test_cli_accepts_multiple_case_options() -> None:
    args = build_parser().parse_args(
        [
            "--case",
            "ma_payment_network_001",
            "--case",
            "jpm_bank_001",
        ]
    )

    assert args.case_ids == ["ma_payment_network_001", "jpm_bank_001"]


@pytest.mark.asyncio
async def test_frozen_execution_uses_production_graph_without_live_providers() -> None:
    case = next(case for case in load_dataset() if case.id == "profile_only_saas_001")
    client = FakeGenerationClient(case.request.asset, "profile_only")
    execution = build_frozen_execution(case, client)

    result = await execution.runner.run(case.request)

    assert isinstance(result, StockAssetSnapshot)
    assert execution.profile_provider.calls == 1
    assert execution.peers_provider.calls == 1
    assert execution.fundamentals_provider.calls == 1
    assert client.calls == 1


@pytest.mark.asyncio
async def test_frozen_providers_return_exact_case_fixtures() -> None:
    case = next(case for case in load_dataset() if case.id == "cloudx_saas_001")
    execution = build_frozen_execution(
        case,
        FakeGenerationClient(case.request.asset, "profile_with_financial_signals"),
    )

    profile = await execution.profile_provider.get_company_profile(
        case.request.asset,
        case.request.asset_type,
    )
    peers = await execution.peers_provider.get_company_peers(profile)
    fundamentals = await execution.fundamentals_provider.get_fundamentals(profile)

    assert profile == case.profile_fixture
    assert profile is not case.profile_fixture
    assert peers == case.peers_fixture
    assert fundamentals == case.fundamentals_fixture


def test_frozen_execution_module_has_no_live_vendor_dependencies() -> None:
    source = inspect.getsource(frozen_module).lower()

    assert "yfinance" not in source
    assert "fmp" not in source


@pytest.mark.asyncio
async def test_runner_executes_approved_test_fixture_and_aggregates() -> None:
    case = next(
        case for case in load_dataset() if case.id == "profile_only_saas_001"
    ).model_copy(deep=True)
    case.metadata.review_status = "approved"
    client = FakeGenerationClient(case.request.asset, "profile_only")
    evaluator = StockSnapshotEvaluator(generation_client=client)

    report = await evaluator.run(
        [case],
        dataset_version="test_fixture",
        deterministic_only=True,
    )

    assert report.case_count == 1
    assert report.approved_case_count == 1
    assert report.unreviewed_dataset_run is False
    assert report.aggregate.deterministic_pass_rates["schema_validity"] == 1.0


@pytest.mark.asyncio
async def test_evaluator_logs_case_and_grader_progress(
    caplog: pytest.LogCaptureFixture,
) -> None:
    case = next(
        case for case in load_dataset() if case.id == "profile_only_saas_001"
    ).model_copy(deep=True)
    case.metadata.review_status = "approved"
    evaluator = StockSnapshotEvaluator(
        generation_client=FakeGenerationClient(case.request.asset, "profile_only")
    )

    with caplog.at_level(logging.INFO):
        await evaluator.run(
            [case],
            dataset_version="test_fixture",
            deterministic_only=True,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("eval.run.start" in message for message in messages)
    assert any(
        "eval.case.generation.success" in message and case.id in message
        for message in messages
    )
    assert any(
        "eval.grader.deterministic.result" in message
        and "metric=schema_validity" in message
        for message in messages
    )
    assert any("eval.run.complete" in message for message in messages)


@pytest.mark.asyncio
async def test_default_cli_exits_before_constructing_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def fail_if_constructed() -> None:
        raise AssertionError("LLM must not be constructed for pending-only dataset")

    monkeypatch.setattr(
        "evals.asset_snapshot.run.OllamaChatClient",
        fail_if_constructed,
    )
    pending_case = load_dataset()[0].model_copy(deep=True)
    pending_case.metadata.review_status = "pending_manual_review"
    dataset_path = tmp_path / "pending.jsonl"
    dataset_path.write_text(pending_case.model_dump_json() + "\n", encoding="utf-8")
    args = argparse.Namespace(
        dataset=str(dataset_path),
        case_ids=None,
        category=None,
        include_pending=False,
        deterministic_only=False,
        validate_only=False,
        output=None,
    )

    assert await run_from_args(args) == 0
    assert NO_APPROVED_CASES_MESSAGE in capsys.readouterr().out


@pytest.mark.asyncio
async def test_report_writes_json_and_markdown(tmp_path: Path) -> None:
    case = next(
        case for case in load_dataset() if case.id == "profile_only_saas_001"
    ).model_copy(deep=True)
    case.metadata.review_status = "approved"
    evaluator = StockSnapshotEvaluator(
        generation_client=FakeGenerationClient(case.request.asset, "profile_only")
    )
    report = await evaluator.run(
        [case],
        dataset_version="test_fixture",
        deterministic_only=True,
    )
    report.cases[0].semantic_metrics = [
        SemanticMetricResult(
            metric="groundedness",
            score=1,
            reason="The explanation relies on a broad inference.",
            evidence=[
                JudgeEvidence(
                    field_path="business_or_asset_profile",
                    quote=(
                        "The company earns recurring revenue from its supplied "
                        "business activity."
                    ),
                )
            ],
            failure_labels=["grounding_failure"],
        )
    ]
    report.cases[0].semantic_metrics_expected = 5
    report.cases[0].failure_labels = ["grounding_failure"]

    json_path, markdown_path = write_report(report, tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert "schema_validity" in json_path.read_text()
    markdown = markdown_path.read_text()
    assert "Deterministic score: `7/7 (100.0%)`" in markdown
    assert "Semantic score: `1.00 / 2 (1/5 graded)`" in markdown
    assert "| `groundedness` | 1 / 2 | grounding_failure |" in markdown
    assert "Source field: `business_or_asset_profile`" in markdown
    assert (
        "The company earns recurring revenue from its supplied business activity."
        in markdown
    )
