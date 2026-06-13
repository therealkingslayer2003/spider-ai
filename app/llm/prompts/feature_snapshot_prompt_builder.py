from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT


class AssetSnapshotPromptBuilder:
    def build_prompt(
        self,
        asset: str,
        asset_type: AssetType,
        asset_profile_context: AssetProfileContext | None = None,
    ) -> str:
        prompt = BASE_SYSTEM_PROMPT + "\n\n" + ASSET_SNAPSHOT_PROMPT.format(
            asset=asset,
            asset_type=asset_type.value,
        )

        if asset_profile_context:
            profile_section = (
                "\n\nAsset profile context (use this as additional grounding):\n"
                f"Name: {asset_profile_context.name}\n"
                f"Sector: {asset_profile_context.sector}\n"
                f"Industry: {asset_profile_context.industry}\n"
                f"Exchange: {asset_profile_context.exchange}\n"
                f"Currency: {asset_profile_context.currency}\n"
                f"Country: {asset_profile_context.country}\n"
                f"Business summary: {asset_profile_context.business_summary}"
            )
            prompt += profile_section

        return prompt
