from datetime import UTC, datetime
from hashlib import sha256

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import CompanyFundamentalsContext
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT
from evals.asset_snapshot.models import PromptMeasurements

# Empty fallback contexts have no source timestamp; keep this clock noise out of A/B.
_MISSING_EVIDENCE_TIME = datetime(1970, 1, 1, tzinfo=UTC)


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class MeasuredSnapshotPromptBuilder(StockSnapshotPromptBuilder):
    measurements: PromptMeasurements | None = None

    def build_prompt(
        self,
        asset: str,
        asset_type: AssetType,
        asset_profile_context: AssetProfileContext | None = None,
        company_peers_context: CompanyPeersContext | None = None,
        company_fundamentals_context: CompanyFundamentalsContext | None = None,
    ) -> str:
        peers = company_peers_context
        fundamentals = company_fundamentals_context
        if peers is not None and peers.provider in {
            "unavailable",
            "frozen_eval_unavailable",
        }:
            peers = peers.model_copy(update={"fetched_at": _MISSING_EVIDENCE_TIME})
        if fundamentals is not None and fundamentals.provider in {
            "unavailable",
            "frozen_eval_unavailable",
        }:
            fundamentals = fundamentals.model_copy(
                update={"fetched_at": _MISSING_EVIDENCE_TIME}
            )
        prompt = super().build_prompt(
            asset, asset_type, asset_profile_context, peers, fundamentals
        )
        feature = self._feature_prompt.format(
            asset=asset,
            asset_type=asset_type.value,
            data_scope=self.data_scope(asset_profile_context, peers, fundamentals),
        )
        static_chars = len(BASE_SYSTEM_PROMPT + "\n\n" + feature + "\n\n")
        dynamic = prompt[static_chars:]
        self.measurements = PromptMeasurements(
            feature_prompt_chars=len(feature),
            static_prompt_chars=static_chars,
            dynamic_context_chars=len(dynamic),
            total_prompt_chars=len(prompt),
            dynamic_context_sha256=text_sha256(dynamic),
            prompt_sha256=text_sha256(prompt),
        )
        return prompt
