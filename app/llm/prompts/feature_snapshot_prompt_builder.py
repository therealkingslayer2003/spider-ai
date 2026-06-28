from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT

_BUSINESS_SUMMARY_MAX_LENGTH = 1_200


class AssetSnapshotPromptBuilder:
    def build_prompt(
        self,
        asset: str,
        asset_type: AssetType,
        asset_profile_context: AssetProfileContext | None = None,
    ) -> str:
        prompt = (
            BASE_SYSTEM_PROMPT
            + "\n\n"
            + ASSET_SNAPSHOT_PROMPT.format(
                asset=asset,
                asset_type=asset_type.value,
            )
        )

        prompt += "\n\n" + self._build_profile_context_section(asset_profile_context)

        return prompt

    def _build_profile_context_section(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> str:
        if asset_profile_context is None:
            return (
                "Asset profile context:\n"
                "Provider: none\n"
                "Status: No provider profile was found. Use stable, general "
                "structural knowledge only."
            )

        return (
            "Asset profile context:\n"
            f"Provider: {asset_profile_context.provider}\n"
            f"Fetched at: {asset_profile_context.fetched_at.isoformat()}\n"
            f"Name: {self._format_optional(asset_profile_context.name)}\n"
            f"Sector: {self._format_optional(asset_profile_context.sector)}\n"
            f"Industry: {self._format_optional(asset_profile_context.industry)}\n"
            f"Exchange: {self._format_optional(asset_profile_context.exchange)}\n"
            f"Currency: {self._format_optional(asset_profile_context.currency)}\n"
            f"Country: {self._format_optional(asset_profile_context.country)}\n"
            "Business summary: "
            f"{self._truncate(asset_profile_context.business_summary)}"
        )

    @staticmethod
    def _format_optional(value: str | None) -> str:
        return value or "Not available"

    @staticmethod
    def _truncate(value: str | None) -> str:
        if not value:
            return "Not available"

        if len(value) <= _BUSINESS_SUMMARY_MAX_LENGTH:
            return value

        return value[: _BUSINESS_SUMMARY_MAX_LENGTH - 3].rstrip() + "..."
