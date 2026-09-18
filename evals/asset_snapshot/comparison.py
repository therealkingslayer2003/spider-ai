import json
import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from app.llm.prompts.company_peer_projection import PeerContextMode
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT
from evals.asset_snapshot.judge import LLMJudgeGrader
from evals.asset_snapshot.models import StockSnapshotEvalCase, StockSnapshotEvalReport
from evals.asset_snapshot.original_feature_prompt import (
    ASSET_SNAPSHOT_PROMPT as ORIGINAL_FEATURE_PROMPT,
)
from evals.asset_snapshot.pairwise import PairwiseResult, PairwiseSnapshotJudge
from evals.asset_snapshot.prompt_measurements import text_sha256
from evals.asset_snapshot.runner import StockSnapshotEvaluator, _aggregate

logger = logging.getLogger(__name__)


class PromptComparisonReport(BaseModel):
    original: StockSnapshotEvalReport
    compressed: StockSnapshotEvalReport
    pairwise: list[PairwiseResult]
    pairwise_judge_model: str | None
    selected_fixture_sha256: str
    system_prompt_sha256: str
    output_schema_sha256: str
    runtime_settings: dict[str, str | float | None] = Field(default_factory=dict)
    generation_order: list[str]


class PromptComparisonEvaluator:
    def __init__(
        self,
        *,
        generation_client: BaseChatModelClient,
        semantic_graders: Sequence[LLMJudgeGrader] = (),
        pairwise_judge: PairwiseSnapshotJudge | None = None,
        peer_context_mode: PeerContextMode = "compact",
    ) -> None:
        self._pairwise = pairwise_judge
        self._evaluators = {
            variant: StockSnapshotEvaluator(
                generation_client=generation_client,
                semantic_graders=semantic_graders,
                peer_context_mode=peer_context_mode,
                feature_prompt=prompt,
            )
            for variant, prompt in (
                ("original", ORIGINAL_FEATURE_PROMPT),
                ("compressed", ASSET_SNAPSHOT_PROMPT),
            )
        }

    async def run(
        self,
        cases: Sequence[StockSnapshotEvalCase],
        *,
        dataset_version: str,
        deterministic_only: bool = False,
        runtime_settings: dict[str, str | float | None] | None = None,
    ) -> PromptComparisonReport:
        if not cases:
            raise ValueError("Prompt comparison requires at least one case")
        if len({case.id for case in cases}) != len(cases):
            raise ValueError("Prompt comparison requires unique case IDs")
        reports: dict[str, list[StockSnapshotEvalReport]] = {
            "original": [],
            "compressed": [],
        }
        comparisons: list[PairwiseResult] = []
        generation_order = []
        for index, case in enumerate(cases):
            order = (
                ("original", "compressed")
                if index % 2 == 0
                else ("compressed", "original")
            )
            for variant in order:
                logger.info(
                    "eval.ab.variant.start case_id=%s variant=%s", case.id, variant
                )
                generation_order.append(f"{case.id}:{variant}")
                reports[variant].append(
                    await self._evaluators[variant].run(
                        [case.model_copy(deep=True)],
                        dataset_version=dataset_version,
                        deterministic_only=deterministic_only,
                    )
                )
            original = reports["original"][-1].cases[0]
            compressed = reports["compressed"][-1].cases[0]
            left, right = original.prompt_measurements, compressed.prompt_measurements
            if original.output is None or compressed.output is None:
                comparison = PairwiseResult(
                    case_id=case.id, status="generation_failure"
                )
            elif (
                left is None
                or right is None
                or left.dynamic_context_sha256 != right.dynamic_context_sha256
            ):
                comparison = PairwiseResult(
                    case_id=case.id,
                    status="context_mismatch",
                    error=(
                        "Dynamic context differed; "
                        "pairwise comparison is not controlled."
                    ),
                )
            elif deterministic_only or self._pairwise is None:
                comparison = PairwiseResult(case_id=case.id, status="not_run")
            else:
                comparison = await self._pairwise.compare(
                    case, original.output, compressed.output
                )
            comparisons.append(comparison)
        pairwise_model = (
            str(
                getattr(
                    self._pairwise.client,
                    "model_name",
                    type(self._pairwise.client).__name__,
                )
            )
            if self._pairwise is not None and not deterministic_only
            else None
        )
        return PromptComparisonReport(
            original=_combine_reports(reports["original"]),
            compressed=_combine_reports(reports["compressed"]),
            pairwise=comparisons,
            pairwise_judge_model=pairwise_model,
            selected_fixture_sha256=text_sha256(
                json.dumps(
                    [case.model_dump(mode="json") for case in cases],
                    sort_keys=True,
                )
            ),
            system_prompt_sha256=text_sha256(BASE_SYSTEM_PROMPT),
            output_schema_sha256=text_sha256(
                json.dumps(StockAssetSnapshot.model_json_schema(), sort_keys=True)
            ),
            runtime_settings=runtime_settings or {},
            generation_order=generation_order,
        )


def _combine_reports(reports: list[StockSnapshotEvalReport]) -> StockSnapshotEvalReport:
    cases = [case for report in reports for case in report.cases]
    return reports[0].model_copy(
        update={
            "cases": cases,
            "case_count": len(cases),
            "approved_case_count": sum(r.approved_case_count for r in reports),
            "pending_case_count": sum(r.pending_case_count for r in reports),
            "unreviewed_dataset_run": any(r.unreviewed_dataset_run for r in reports),
            "total_runtime_seconds": sum(r.total_runtime_seconds for r in reports),
            "average_latency_seconds": sum(c.latency_seconds for c in cases)
            / len(cases),
            "aggregate": _aggregate(cases),
        }
    )
