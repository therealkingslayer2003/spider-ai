import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from evals.asset_snapshot.comparison import PromptComparisonEvaluator
from evals.asset_snapshot.comparison_reporting import write_comparison_report
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.judge import default_semantic_graders
from evals.asset_snapshot.models import JudgeEvidence
from evals.asset_snapshot.pairwise import PairwiseDecision, PairwiseSnapshotJudge
from evals.asset_snapshot.prompt_measurements import MeasuredSnapshotPromptBuilder
from evals.asset_snapshot.run import build_parser, run_from_args
from tests.test_evals_execution import FakeGenerationClient
from tests.test_graph import llm_response


@pytest.fixture
def case():
    return next(c for c in load_dataset() if c.id == "amzn_peer_profiles_001")


def decision(winner="tie", a="Company earns revenue.", b="Company earns revenue."):
    return PairwiseDecision(
        winner=winner,
        reason="Comparable evidence-grounded quality.",
        evidence_a=[JudgeEvidence(field_path="summary", quote=a)],
        evidence_b=[JudgeEvidence(field_path="summary", quote=b)],
    )


def snapshot(summary):
    result = StockAssetSnapshot.model_validate_json(llm_response())
    result.summary = summary
    return result


@pytest.mark.parametrize(
    ("forward", "reverse", "expected", "status"),
    [
        ("A", "B", "original", "judged"),
        ("B", "A", "compressed", "judged"),
        ("tie", "tie", "tie", "judged"),
        ("A", "A", None, "order_disagreement"),
        ("tie", "A", None, "order_disagreement"),
    ],
)
async def test_pairwise_is_blinded_order_checked_and_quotes_are_verified(
    case, forward, reverse, expected, status
):
    a, b = "Sells subscriptions.", "Earns recurring fees."
    client = AsyncMock(spec=BaseChatModelClient)
    client.generate.side_effect = [decision(forward, a, b), decision(reverse, b, a)]
    result = await PairwiseSnapshotJudge(client).compare(case, snapshot(a), snapshot(b))
    assert result.winner == expected
    assert result.status == status
    assert client.generate.await_count == 2
    payloads = []
    for call in client.generate.await_args_list:
        assert call.kwargs["response_schema"] is PairwiseDecision
        prompt = call.args[0]
        assert "original" not in prompt.lower()
        assert "compressed" not in prompt.lower()
        payloads.append(json.loads(prompt.split("Evaluation data:\n")[1]))
    assert payloads[0]["candidate_a"] == payloads[1]["candidate_b"]
    assert payloads[0]["candidate_b"] == payloads[1]["candidate_a"]
    assert payloads[0]["profile_fixture"] == payloads[1]["profile_fixture"]


@pytest.mark.parametrize("failure", ["invalid_quote", "wrong_source", "transport"])
async def test_pairwise_failure_is_not_a_tie_or_win(case, failure):
    client = AsyncMock(spec=BaseChatModelClient)
    if failure == "transport":
        client.generate.side_effect = TimeoutError("judge offline")
    else:
        client.generate.return_value = decision(
            a="invented quote" if failure == "invalid_quote" else "Only in candidate B."
        )
    result = await PairwiseSnapshotJudge(client).compare(
        case, snapshot("Only in candidate A."), snapshot("Only in candidate B.")
    )
    assert result.status == "judge_failure"
    assert result.winner is None
    assert result.error


async def test_second_judgment_failure_retains_first_but_does_not_declare_winner(case):
    client = AsyncMock(spec=BaseChatModelClient)
    client.generate.side_effect = [decision(), RuntimeError("failed")]
    result = await PairwiseSnapshotJudge(client).compare(
        case, snapshot("Company earns revenue."), snapshot("Company earns revenue.")
    )
    assert result.status == "judge_failure" and result.winner is None
    assert result.forward is not None and result.reverse is None


async def test_comparison_reuses_graders_freezes_context_and_records_all_outputs(
    case, tmp_path
):
    before = case.model_dump_json()
    generation = FakeGenerationClient(case.request.asset, "profile_with_peers")
    judge = AsyncMock(spec=BaseChatModelClient)
    judge.model_name = "frozen-judge"
    quote = "A synthetic company with a defined business model."
    judge.generate.return_value = json.dumps(
        {
            "score": 2,
            "reason": "Supported.",
            "evidence": [{"field_path": "summary", "quote": quote}],
        }
    )
    pairwise_client = AsyncMock(spec=BaseChatModelClient)
    pairwise_client.model_name = "pairwise-judge"
    pairwise_client.generate.side_effect = [
        decision(a=quote, b=quote),
        decision(a=quote, b=quote),
    ]
    report = await PromptComparisonEvaluator(
        generation_client=generation,
        semantic_graders=default_semantic_graders(judge),
        pairwise_judge=PairwiseSnapshotJudge(pairwise_client),
    ).run([case], dataset_version="test")

    assert generation.calls == 2
    assert judge.generate.await_count == 10
    assert pairwise_client.generate.await_count == 2
    assert report.pairwise[0].winner == "tie"
    assert case.model_dump_json() == before
    left, right = report.original.cases[0], report.compressed.cases[0]
    assert (
        left.prompt_measurements.dynamic_context_sha256
        == right.prompt_measurements.dynamic_context_sha256
    )
    assert (
        left.prompt_measurements.total_prompt_chars
        > right.prompt_measurements.total_prompt_chars
    )
    assert left.output is not None and right.output is not None
    assert len(left.semantic_metrics) == len(right.semantic_metrics) == 5
    assert left.generation_latency_seconds <= left.latency_seconds
    json_path, md_path = write_comparison_report(report, tmp_path)
    saved = json.loads(json_path.read_text())
    assert saved["original"]["cases"][0]["output"] == left.output.model_dump(
        mode="json"
    )
    markdown = md_path.read_text()
    for text in (
        "risk_mechanism_quality",
        "unsupported_numeric_claims",
        "peer_coverage",
        "Full snapshot:",
        "A=original, B=compressed",
        "A=compressed, B=original",
        "ties: 1",
        quote,
    ):
        assert text in markdown


async def test_generation_failure_preserves_other_output_and_skips_pairwise(case):
    generation = FakeGenerationClient(case.request.asset, "profile_with_peers")
    generate = generation.generate
    calls = 0

    async def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("generation unavailable")
        return await generate(*args, **kwargs)

    generation.generate = fail_once
    judge = AsyncMock(spec=PairwiseSnapshotJudge)
    judge.client = AsyncMock()
    report = await PromptComparisonEvaluator(
        generation_client=generation, pairwise_judge=judge
    ).run([case], dataset_version="test")
    assert report.original.cases[0].output is None
    assert report.compressed.cases[0].output is not None
    assert report.pairwise[0].status == "generation_failure"
    judge.compare.assert_not_awaited()


async def test_context_mismatch_prevents_pairwise_judgment(case, monkeypatch):
    original = MeasuredSnapshotPromptBuilder.build_prompt
    calls = 0

    def changed(self, *args, **kwargs):
        nonlocal calls
        result = original(self, *args, **kwargs)
        calls += 1
        self.measurements.dynamic_context_sha256 = str(calls)
        return result

    monkeypatch.setattr(MeasuredSnapshotPromptBuilder, "build_prompt", changed)
    judge = AsyncMock(spec=PairwiseSnapshotJudge)
    judge.client = AsyncMock()
    report = await PromptComparisonEvaluator(
        generation_client=FakeGenerationClient(
            case.request.asset, "profile_with_peers"
        ),
        pairwise_judge=judge,
    ).run([case], dataset_version="test")
    assert report.pairwise[0].status == "context_mismatch"
    assert report.pairwise[0].winner is None
    judge.compare.assert_not_awaited()


async def test_generation_order_alternates_and_deterministic_only_skips_judges(case):
    second = case.model_copy(update={"id": "second_case"}, deep=True)
    generation = FakeGenerationClient(case.request.asset, "profile_with_peers")
    judge = AsyncMock(spec=PairwiseSnapshotJudge)
    report = await PromptComparisonEvaluator(
        generation_client=generation,
        pairwise_judge=judge,
    ).run([case, second], dataset_version="test", deterministic_only=True)
    assert report.generation_order == [
        f"{case.id}:original",
        f"{case.id}:compressed",
        "second_case:compressed",
        "second_case:original",
    ]
    assert generation.calls == 4
    assert report.original.case_count == report.compressed.case_count == 2
    assert all(pair.status == "not_run" for pair in report.pairwise)
    judge.compare.assert_not_awaited()


async def test_comparison_requires_nonempty_unique_cases(case):
    evaluator = PromptComparisonEvaluator(
        generation_client=FakeGenerationClient("AMZN", "profile_only")
    )
    for cases in ([], [case, case]):
        with pytest.raises(ValueError):
            await evaluator.run(cases, dataset_version="test")


async def test_cli_comparison_writes_report_without_live_models(
    case, monkeypatch, tmp_path
):
    generation = FakeGenerationClient(case.request.asset, "profile_with_peers")
    monkeypatch.setattr("evals.asset_snapshot.run.OllamaChatClient", lambda: generation)
    args = build_parser().parse_args(
        [
            "--compare-prompts",
            "--deterministic-only",
            "--case",
            case.id,
            "--output",
            str(tmp_path),
        ]
    )
    assert await run_from_args(args) == 0
    saved = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert (
        saved["original"]["dataset_version"]
        == saved["compressed"]["dataset_version"]
        == "stock_snapshot_v1_peer_landscape_v2"
    )
    assert saved["original"]["case_count"] == saved["compressed"]["case_count"] == 1
    assert saved["pairwise"][0]["status"] == "not_run"
    assert generation.calls == 2


async def test_cli_pairwise_only_uses_configured_judge_and_no_individual_graders(
    case, monkeypatch, tmp_path
):
    generation = FakeGenerationClient(case.request.asset, "profile_with_peers")
    judge = AsyncMock(spec=BaseChatModelClient)
    judge.model_name = "independent-judge"
    quote = "A synthetic company with a defined business model."
    judge.generate.side_effect = [
        decision(a=quote, b=quote),
        decision(a=quote, b=quote),
    ]
    judge_factory = Mock(return_value=judge)
    semantic_factory = Mock(
        side_effect=AssertionError("Semantic graders not requested")
    )
    monkeypatch.setattr("evals.asset_snapshot.run.OllamaChatClient", lambda: generation)
    monkeypatch.setattr("evals.asset_snapshot.run.EvalOllamaClient", judge_factory)
    monkeypatch.setattr(
        "evals.asset_snapshot.run.default_semantic_graders", semantic_factory
    )
    monkeypatch.setattr(
        "evals.asset_snapshot.run.get_eval_settings",
        lambda: Mock(
            eval_judge_model="independent-judge",
            eval_judge_base_url="http://unused-test-server",
        ),
    )
    args = build_parser().parse_args(
        [
            "--compare-prompts",
            "--pairwise-only",
            "--case",
            case.id,
            "--output",
            str(tmp_path),
        ]
    )
    assert await run_from_args(args) == 0
    judge_factory.assert_called_once_with(
        model="independent-judge", base_url="http://unused-test-server"
    )
    semantic_factory.assert_not_called()
    assert generation.calls == 2
    assert judge.generate.await_count == 2
    saved = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert saved["pairwise_judge_model"] == "independent-judge"
    assert saved["pairwise"][0]["winner"] == "tie"
    assert not saved["original"]["cases"][0]["semantic_metrics"]
    assert not saved["compressed"]["cases"][0]["semantic_metrics"]


@pytest.mark.parametrize(
    "options",
    [
        ["--pairwise-only"],
        ["--compare-prompts", "--pairwise-only", "--deterministic-only"],
    ],
)
async def test_cli_rejects_incompatible_pairwise_flags(options):
    with pytest.raises(ValueError, match="requires --compare-prompts"):
        await run_from_args(build_parser().parse_args(options))
