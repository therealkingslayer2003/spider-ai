import logging
import subprocess
import time
from collections import defaultdict
from collections.abc import Sequence
from uuid import uuid4

from app.llm.base import BaseChatModelClient
from app.llm.prompts.company_peer_projection import PeerContextMode
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from evals.asset_snapshot.frozen import build_frozen_execution
from evals.asset_snapshot.graders import (
    DeterministicGrader,
    collect_failure_labels,
    default_deterministic_graders,
)
from evals.asset_snapshot.judge import JudgeEvaluationError, LLMJudgeGrader
from evals.asset_snapshot.models import (
    EvalAggregate,
    EvalCaseResult,
    StockSnapshotEvalCase,
    StockSnapshotEvalReport,
)
from evals.asset_snapshot.prompt_measurements import (
    MeasuredSnapshotPromptBuilder,
    text_sha256,
)

logger = logging.getLogger(__name__)


class StockSnapshotEvaluator:
    def __init__(
        self,
        *,
        generation_client: BaseChatModelClient,
        semantic_graders: Sequence[LLMJudgeGrader] = (),
        deterministic_graders: Sequence[DeterministicGrader] | None = None,
        peer_context_mode: PeerContextMode = "compact",
        feature_prompt: str = ASSET_SNAPSHOT_PROMPT,
    ) -> None:
        self._generation_client = generation_client
        self._peer_context_mode = peer_context_mode
        self._feature_prompt = feature_prompt
        self._semantic_graders = list(semantic_graders)
        self._deterministic_graders = list(
            deterministic_graders or default_deterministic_graders()
        )

    async def run(
        self,
        cases: Sequence[StockSnapshotEvalCase],
        *,
        dataset_version: str,
        deterministic_only: bool = False,
    ) -> StockSnapshotEvalReport:
        run_id = uuid4().hex[:8]
        started = time.perf_counter()
        generation_model = _model_name(self._generation_client)
        judge_model = (
            None
            if deterministic_only or not self._semantic_graders
            else _model_name(self._semantic_graders[0].client)
        )
        logger.info(
            "eval.run.start run_id=%s dataset=%s cases=%s "
            "generation_model=%s judge_model=%s deterministic_graders=%s "
            "semantic_graders=%s deterministic_only=%s peer_context_mode=%s",
            run_id,
            dataset_version,
            len(cases),
            generation_model,
            judge_model or "not_run",
            len(self._deterministic_graders),
            len(self._semantic_graders),
            deterministic_only,
            self._peer_context_mode,
        )
        case_results = [
            await self._run_case(
                case,
                run_id=run_id,
                deterministic_only=deterministic_only,
            )
            for case in cases
        ]
        total_runtime = time.perf_counter() - started
        report = StockSnapshotEvalReport(
            dataset_version=dataset_version,
            git_commit_sha=_git_commit_sha(),
            generation_model=generation_model,
            judge_model=judge_model,
            peer_context_mode=self._peer_context_mode,
            feature_prompt_sha256=text_sha256(self._feature_prompt),
            feature_prompt_chars=len(self._feature_prompt),
            case_count=len(cases),
            approved_case_count=sum(
                case.metadata.review_status == "approved" for case in cases
            ),
            pending_case_count=sum(
                case.metadata.review_status == "pending_manual_review" for case in cases
            ),
            unreviewed_dataset_run=any(
                case.metadata.review_status != "approved" for case in cases
            ),
            deterministic_only=deterministic_only,
            total_runtime_seconds=total_runtime,
            average_latency_seconds=(
                sum(result.latency_seconds for result in case_results)
                / len(case_results)
                if case_results
                else 0.0
            ),
            aggregate=_aggregate(case_results),
            cases=case_results,
        )
        logger.info(
            "eval.run.complete run_id=%s dataset=%s cases=%s failures=%s "
            "runtime_seconds=%.3f average_latency_seconds=%.3f",
            run_id,
            dataset_version,
            len(cases),
            sum(bool(result.failure_labels) for result in case_results),
            total_runtime,
            report.average_latency_seconds,
        )
        logger.info(
            "eval.run.aggregate run_id=%s deterministic_pass_rates=%s "
            "semantic_averages=%s weakest_cases=%s",
            run_id,
            report.aggregate.deterministic_pass_rates,
            report.aggregate.semantic_averages,
            report.aggregate.weakest_cases,
        )
        return report

    async def _run_case(
        self,
        case: StockSnapshotEvalCase,
        *,
        run_id: str,
        deterministic_only: bool,
    ) -> EvalCaseResult:
        started = time.perf_counter()
        logger.info(
            "eval.case.start run_id=%s case_id=%s asset=%s category=%s "
            "case_kind=%s review_status=%s",
            run_id,
            case.id,
            case.request.asset,
            case.metadata.category,
            case.metadata.case_kind,
            case.metadata.review_status,
        )
        logger.debug(
            "eval.case.context run_id=%s case_id=%s profile_fixture=%s "
            "peer_count=%s fundamentals_fixture=%s expectation_concepts=%s "
            "expected_risk_themes=%s",
            run_id,
            case.id,
            case.profile_fixture is not None,
            len(case.peers_fixture.peers) if case.peers_fixture else 0,
            case.fundamentals_fixture is not None,
            case.expectations.business_model_concepts,
            case.expectations.structural_risk_themes,
        )
        prompt_builder = MeasuredSnapshotPromptBuilder(
            peer_context_mode=self._peer_context_mode,
            feature_prompt=self._feature_prompt,
        )
        generation_started = time.perf_counter()
        try:
            execution = build_frozen_execution(
                case,
                self._generation_client,
                peer_context_mode=self._peer_context_mode,
                prompt_builder=prompt_builder,
            )
            generation_started = time.perf_counter()
            logger.info(
                "eval.case.generation.start run_id=%s case_id=%s asset=%s",
                run_id,
                case.id,
                case.request.asset,
            )
            output = await execution.runner.run(case.request)
        except Exception as exc:
            latency = time.perf_counter() - started
            logger.exception(
                "eval.case.generation.failed run_id=%s case_id=%s asset=%s "
                "latency_seconds=%.3f",
                run_id,
                case.id,
                case.request.asset,
                latency,
            )
            return EvalCaseResult(
                case_id=case.id,
                category=case.metadata.category,
                review_status=case.metadata.review_status,
                output=None,
                semantic_metrics_expected=(
                    0 if deterministic_only else len(self._semantic_graders)
                ),
                failure_labels=["generation_failure"],
                latency_seconds=latency,
                generation_latency_seconds=time.perf_counter() - generation_started,
                prompt_measurements=prompt_builder.measurements,
                error=str(exc),
            )
        generation_latency = time.perf_counter() - generation_started
        logger.info(
            "eval.case.generation.success run_id=%s case_id=%s "
            "duration_seconds=%.3f data_scope=%s drivers=%s risks=%s peers=%s",
            run_id,
            case.id,
            time.perf_counter() - generation_started,
            output.data_scope,
            len(output.structural_drivers),
            len(output.structural_risks),
            len(output.peer_landscape),
        )

        deterministic_results = [
            grader.grade(case, output) for grader in self._deterministic_graders
        ]
        for deterministic_result in deterministic_results:
            log = logger.info if deterministic_result.passed else logger.warning
            log(
                "eval.grader.deterministic.result run_id=%s case_id=%s "
                "metric=%s passed=%s score=%.3f labels=%s reason=%s",
                run_id,
                case.id,
                deterministic_result.metric,
                deterministic_result.passed,
                deterministic_result.score,
                deterministic_result.failure_labels,
                _compact(deterministic_result.reason),
            )

        semantic_results = []
        judge_errors: list[str] = []
        if not deterministic_only:
            for grader in self._semantic_graders:
                try:
                    semantic_result = await grader.grade(case, output)
                    semantic_results.append(semantic_result)
                    log = logger.info if semantic_result.score == 2 else logger.warning
                    log(
                        "eval.grader.semantic.result run_id=%s case_id=%s "
                        "metric=%s score=%s labels=%s evidence_paths=%s reason=%s",
                        run_id,
                        case.id,
                        semantic_result.metric,
                        semantic_result.score,
                        semantic_result.failure_labels,
                        [evidence.field_path for evidence in semantic_result.evidence],
                        _compact(semantic_result.reason),
                    )
                except JudgeEvaluationError as exc:
                    judge_errors.append(str(exc))
                    logger.error(
                        "eval.grader.semantic.failed run_id=%s case_id=%s "
                        "metric=%s error=%s",
                        run_id,
                        case.id,
                        grader.metric,
                        _compact(str(exc)),
                    )

        failure_labels = set(collect_failure_labels(deterministic_results))
        failure_labels.update(
            label
            for semantic_result in semantic_results
            for label in semantic_result.failure_labels
        )
        if judge_errors:
            failure_labels.add("judge_failure")

        latency = time.perf_counter() - started
        case_result = EvalCaseResult(
            case_id=case.id,
            category=case.metadata.category,
            review_status=case.metadata.review_status,
            output=output,
            deterministic_metrics=deterministic_results,
            semantic_metrics=semantic_results,
            semantic_metrics_expected=(
                0 if deterministic_only else len(self._semantic_graders)
            ),
            failure_labels=sorted(failure_labels),
            latency_seconds=latency,
            generation_latency_seconds=generation_latency,
            prompt_measurements=prompt_builder.measurements,
            error="; ".join(judge_errors) if judge_errors else None,
        )
        logger.info(
            "eval.case.complete run_id=%s case_id=%s latency_seconds=%.3f "
            "failure_labels=%s judge_errors=%s",
            run_id,
            case.id,
            latency,
            case_result.failure_labels,
            len(judge_errors),
        )
        return case_result


def _aggregate(case_results: Sequence[EvalCaseResult]) -> EvalAggregate:
    deterministic_values: dict[str, list[bool]] = defaultdict(list)
    semantic_values: dict[str, list[int]] = defaultdict(list)
    for case in case_results:
        for deterministic_metric in case.deterministic_metrics:
            deterministic_values[deterministic_metric.metric].append(
                deterministic_metric.passed
            )
        for semantic_metric in case.semantic_metrics:
            semantic_values[semantic_metric.metric].append(semantic_metric.score)

    deterministic_pass_rates = {
        metric: sum(values) / len(values)
        for metric, values in deterministic_values.items()
        if values
    }
    semantic_averages = {
        metric: sum(values) / len(values)
        for metric, values in semantic_values.items()
        if values
    }
    weakest_cases = [
        case.case_id
        for case in sorted(
            case_results,
            key=lambda item: (
                _case_quality(item),
                -len(item.failure_labels),
            ),
        )[:5]
        if case.failure_labels or case.semantic_metrics
    ]
    return EvalAggregate(
        deterministic_pass_rates=deterministic_pass_rates,
        semantic_averages=semantic_averages,
        weakest_cases=weakest_cases,
    )


def _case_quality(case: EvalCaseResult) -> float:
    if case.semantic_metrics:
        return sum(result.score for result in case.semantic_metrics) / len(
            case.semantic_metrics
        )
    if case.deterministic_metrics:
        return sum(result.score for result in case.deterministic_metrics) / len(
            case.deterministic_metrics
        )
    return 0.0


def _model_name(client: BaseChatModelClient) -> str:
    value = getattr(client, "model_name", None)
    return str(value) if value else type(client).__name__


def _compact(value: str | None, max_chars: int = 500) -> str:
    if not value:
        return "none"
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _git_commit_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None
