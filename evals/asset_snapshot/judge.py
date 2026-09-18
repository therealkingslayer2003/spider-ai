import json
import logging
import time
from dataclasses import dataclass

from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.base import BaseChatModelClient
from app.llm.json_parser import parse_llm_json
from evals.asset_snapshot.models import (
    JudgeEvidence,
    JudgeResult,
    SemanticMetricResult,
    StockSnapshotEvalCase,
)

logger = logging.getLogger(__name__)

_MAX_REPORTED_EVIDENCE = 3


class JudgeEvaluationError(RuntimeError):
    """Raised when the semantic judge cannot return a valid structured result."""


PEER_RESEARCH_JUDGE_RULES = """
Judge against the supplied request, normalized provider fixtures, expectations,
and rubric. Provider evidence is the primary factual anchor and overrides
contradictory memory. Stable model knowledge may supplement even present/compact
profiles ONLY for high-confidence, widely established, structurally persistent,
non-obscure company or industry facts. Long-established products/platforms,
activities and relationships are acceptable secondary support, not provider facts.
Do not require these claims to occur literally in fixtures. Explain whether disputed
claims are provider-grounded, stable-knowledge-supported, or unsupported.
Do not invent company-specific knowledge for fictional entities.

Model memory cannot supply numerical claims, current metrics, market shares,
recent contracts, supplier/customer links, partnerships, regulatory actions, or
latest product/news developments. Time-sensitive relationships require provider
evidence. Reject uncertain/obscure facts asserted confidently and contradictions
of supplied facts. General economics may interpret supported facts. Missing
financial data is not negative evidence; metrics require business-model context,
not automatic bullish/bearish or leverage conclusions. No trading/news/valuation.

Every distinct identifiable supplied peer should be acknowledged exactly once.
Peer membership is not proof of direct competition. peer_type, relationship_area,
why_relevant are analytical outputs, not provider fields:
- direct_competitor requires substantial offering AND demand/customer/revenue overlap.
- indirect_competitor requires a different offering substituting for the same need,
  spending, platform usage, transactions, advertising, or ecosystem participation.
- comparable requires broad economic similarity without a supported competitive
  mechanism; it is a legitimate outcome, not a failed competition explanation.
- unclear is correct when neither supplied evidence nor permitted stable knowledge
  supports reliable classification. Do not force type diversity or supplier,
  customer, partner, or complementor types.

Evaluate peer coverage, peer_type correctness, direct-competition overclaiming,
indirect substitution justification, appropriate comparable/unclear classifications,
specific relationship_area and a grounded why_relevant that combines the supported
relationship with its target-focused causal economic significance. Both parts must
be covered (or explicitly qualified); a bare high/medium/low rating is insufficient.
Missing enrichment alone neither invalidates a peer nor
prohibits reliable stable-knowledge classification. If support is insufficient,
accurate uncertainty is substantive analysis, not a placeholder; do not force an
economic mechanism. If support establishes overlap, blanket disclaimers are weak.
Check consistency between peer_type and the explanation: comparable cannot excuse
a supported competitive mechanism described in why_relevant.
A shared sector alone is weaker than a specific, supported relationship area.
Empty landscapes are appropriate only without identifiable supplied peers,
not when enrichment fails. Do not invent additional peer identities.

related_entities must identify supplied peers materially connected to the specific
risk mechanism, not just copy the landscape. They need not be competitors.
An empty related_entities list is valid when no supplied peer materially participates.
Do not penalize it solely for being empty or require every risk to be competitive.
Risks still require pressure -> company exposure -> transmission -> economic
consequence. Mere membership in related_entities does not justify a relationship.
""".strip()


_COMMON_JUDGE_RULES = (
    PEER_RESEARCH_JUDGE_RULES
    + """

Return only JSON, example:
{
  "score": 0,
  "reason": "concise evidence-based explanation",
  "evidence": [
    {
      "field_path": "structural_risks[0].explanation",
      "quote": "exact text copied from that generated snapshot field"
    }
  ]
}
Score must be exactly 0, 1, or 2.
Return one to three evidence items for every score. Each quote must be a literal,
contiguous excerpt copied exactly from the generated_snapshot field identified by
field_path. Do not paraphrase, change capitalization, or insert ellipses. Paths
start at the snapshot root, for example summary, business_or_asset_profile,
structural_drivers[0].explanation, or structural_risks[0].explanation.
""".strip()
)


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
            evidence = _validate_evidence(
                judge_result.evidence,
                output,
                case_id=case.id,
                metric=self.metric,
            )
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
            evidence=evidence,
            failure_labels=[] if judge_result.score == 2 else [self.failure_label],
        )

    def _build_prompt(
        self,
        case: StockSnapshotEvalCase,
        output: StockAssetSnapshot,
    ) -> str:
        context = {
            "entity_kind": case.metadata.entity_kind,
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


def _validate_evidence(
    evidence: list[JudgeEvidence],
    output: StockAssetSnapshot,
    *,
    case_id: str,
    metric: str,
) -> list[JudgeEvidence]:
    snapshot_fields = _snapshot_fields(output.model_dump(mode="json"))
    validated: list[JudgeEvidence] = []
    seen: set[tuple[str, str]] = set()
    rejected: list[str] = []
    for item in evidence:
        try:
            normalized = _normalize_evidence(item, snapshot_fields)
        except ValueError as exc:
            rejected.append(str(exc))
            logger.warning(
                "eval.judge.evidence.skipped case_id=%s metric=%s "
                "field_path=%s error=%s",
                case_id,
                metric,
                item.field_path,
                exc,
            )
            continue

        key = (normalized.field_path, normalized.quote)
        if key in seen:
            continue
        validated.append(normalized)
        seen.add(key)
        if len(validated) == _MAX_REPORTED_EVIDENCE:
            break

    if not validated:
        reasons = "; ".join(rejected) or "no evidence supplied"
        raise ValueError(f"Judge returned no valid snapshot evidence: {reasons}")
    if len(evidence) > len(validated):
        logger.info(
            "eval.judge.evidence.normalized case_id=%s metric=%s received=%s kept=%s",
            case_id,
            metric,
            len(evidence),
            len(validated),
        )
    return validated


def _normalize_evidence(
    evidence: JudgeEvidence,
    snapshot_fields: dict[str, object],
) -> JudgeEvidence:
    field_path = evidence.field_path.removeprefix("generated_snapshot.")
    if field_path in snapshot_fields:
        field_text = _field_text(snapshot_fields[field_path])
        if evidence.quote not in field_text:
            raise ValueError(f"quote is not present in field {field_path!r}")
        return JudgeEvidence(field_path=field_path, quote=evidence.quote)

    matching_paths = [
        path
        for path, value in snapshot_fields.items()
        if isinstance(value, str) and evidence.quote in value
    ]
    if len(matching_paths) != 1:
        raise ValueError(f"unknown field {evidence.field_path!r}")
    return JudgeEvidence(field_path=matching_paths[0], quote=evidence.quote)


def _snapshot_fields(value: object, path: str = "") -> dict[str, object]:
    fields: dict[str, object] = {path: value} if path else {}
    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            fields.update(_snapshot_fields(nested_value, nested_path))
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            fields.update(_snapshot_fields(nested_value, f"{path}[{index}]"))
    return fields


def _field_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


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
                "revenue/value mechanism anchored in supplied context, with only "
                "permitted stable knowledge as secondary support."
            ),
            failure_label="wrong_business_model",
            client=client,
        ),
        LLMJudgeGrader(
            metric="structural_risk_quality",
            rubric=(
                "0 = risks are irrelevant, temporary/current-news driven, or generic. "
                "1 = risks are relevant but weak or generic. "
                "2 = risks are persistent, specific, and tied to this business; "
                "related_entities materially participate in the stated mechanism, "
                "rather than being copied from the peer list."
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
                "2 = claims respect provider evidence, permitted stable knowledge "
                "and conservative inference. Do not penalize reliable persistent "
                "knowledge merely because compact fixtures omit it. Penalize "
                "numerical/current/obscure inventions, contradictory claims, "
                "speculative direct competition, unsupported indirect substitution "
                "and unjustified related_entities. Explain the support basis."
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
                "peer context, and available financial signals. Assess peer_type, "
                "relationship_area and the combined why_relevant explanation: "
                "specific supported overlap/substitution or accurate broader "
                "comparability/uncertainty, not automatic competitor labels or "
                "blanket disclaimers. Missing profiles do not justify omissions."
            ),
            failure_label="generic_risk",
            client=client,
        ),
    ]
