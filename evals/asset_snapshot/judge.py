import json
import logging
import time
from dataclasses import dataclass

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from app.llm.json_parser import parse_llm_json
from evals.asset_snapshot.models import (
    JudgeResult,
    SemanticMetricResult,
    StockSnapshotEvalCase,
)

logger = logging.getLogger(__name__)


class JudgeEvaluationError(RuntimeError):
    """Raised when the semantic judge cannot return a valid structured result."""


_COMMON_JUDGE_RULES = """
Judge only against the supplied request, normalized provider fixtures, explicit
expectations, and rubric. Do not use current market knowledge, current news,
stock prices, or facts not supplied here.

Return only JSON, example:
{
  "score": 0,
  "reason": "concise evidence-based explanation"
}
Score must be exactly 0, 1, or 2.
""".strip()


@dataclass(frozen=True)
class LLMJudgeGrader:
    metric: str
    rubric: str
    failure_label: str
    client: BaseChatModelClient

    async def grade(
        self,
        case: StockSnapshotEvalCase,
        output: StockAssetSnapshot,
    ) -> SemanticMetricResult:
        started = time.perf_counter()
        prompt = self._build_prompt(case=case, output=output)
        logger.info(
            "eval.judge.start case_id=%s metric=%s model=%s prompt_chars=%s",
            case.id,
            self.metric,
            _model_name(self.client),
            len(prompt),
        )
        try:
            raw_result = await self.client.generate(prompt)
            judge_result = JudgeResult.model_validate(parse_llm_json(raw_result))
        except Exception as exc:
            logger.exception(
                "eval.judge.failed case_id=%s metric=%s model=%s duration_seconds=%.3f",
                case.id,
                self.metric,
                _model_name(self.client),
                time.perf_counter() - started,
            )
            raise JudgeEvaluationError(
                f"Judge failed for metric={self.metric}: {exc}"
            ) from exc

        logger.info(
            "eval.judge.success case_id=%s metric=%s score=%s duration_seconds=%.3f",
            case.id,
            self.metric,
            judge_result.score,
            time.perf_counter() - started,
        )
        return SemanticMetricResult(
            metric=self.metric,
            score=judge_result.score,
            reason=judge_result.reason,
            failure_labels=[] if judge_result.score == 2 else [self.failure_label],
        )

    def _build_prompt(
        self,
        case: StockSnapshotEvalCase,
        output: StockAssetSnapshot,
    ) -> str:
        context = {
            "request": case.request.model_dump(mode="json"),
            "profile_fixture": case.profile_fixture.model_dump(mode="json")
            if case.profile_fixture
            else None,
            "peers_fixture": case.peers_fixture.model_dump(mode="json")
            if case.peers_fixture
            else None,
            "fundamentals_fixture": case.fundamentals_fixture.model_dump(mode="json")
            if case.fundamentals_fixture
            else None,
            "expectations": case.expectations.model_dump(mode="json"),
            "generated_snapshot": output.model_dump(mode="json"),
        }
        return (
            f"You are grading Stock Asset Snapshot metric: {self.metric}.\n\n"
            f"Rubric:\n{self.rubric}\n\n"
            f"{_COMMON_JUDGE_RULES}\n\n"
            f"Evaluation context:\n{json.dumps(context, indent=2)}"
        )


def _model_name(client: BaseChatModelClient) -> str:
    value = getattr(client, "model_name", None)
    return str(value) if value else type(client).__name__


def default_semantic_graders(
    client: BaseChatModelClient,
) -> list[LLMJudgeGrader]:
    return [
        LLMJudgeGrader(
            metric="business_model_correctness",
            rubric=(
                "0 = materially wrong business category or economics. "
                "1 = partially correct but generic or incomplete. "
                "2 = correctly captures what the business does and its central "
                "revenue/value mechanism from supplied context."
            ),
            failure_label="wrong_business_model",
            client=client,
        ),
        LLMJudgeGrader(
            metric="structural_risk_quality",
            rubric=(
                "0 = risks are irrelevant, temporary/current-news driven, or generic. "
                "1 = risks are relevant but weak or generic. "
                "2 = risks are persistent, specific, and tied to this business."
            ),
            failure_label="generic_risk",
            client=client,
        ),
        LLMJudgeGrader(
            metric="risk_mechanism_quality",
            rubric=(
                "0 = risk labels without causal mechanism. "
                "1 = partial causal explanation. "
                "2 = clear structural cause to affected business area to economic "
                "consequence such as revenue, margins, growth durability, balance "
                "sheet, competitive position, or risk premium."
            ),
            failure_label="weak_risk_mechanism",
            client=client,
        ),
        LLMJudgeGrader(
            metric="groundedness",
            rubric=(
                "0 = material unsupported factual claims or contradictions. "
                "1 = mostly grounded with weak extrapolation. "
                "2 = factual statements align with supplied fixtures and inferences "
                "are reasonable. Missing context must not be invented."
            ),
            failure_label="grounding_failure",
            client=client,
        ),
        LLMJudgeGrader(
            metric="company_specificity",
            rubric=(
                "0 = boilerplate reusable for unrelated companies. "
                "1 = some company or industry specificity. "
                "2 = strongly tied to the supplied business model, dependencies, "
                "competitive context, and available financial signals."
            ),
            failure_label="generic_risk",
            client=client,
        ),
    ]
