from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_peer_context import CompanyPeerContext
from app.domain.schemas.sector_context import SectorContext
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT

_BUSINESS_SUMMARY_MAX_LENGTH = 1_200


class AssetSnapshotPromptBuilder:
    def build_prompt(
        self,
        asset: str,
        asset_type: AssetType,
        asset_profile_context: AssetProfileContext | None = None,
        company_peers_context: CompanyPeerContext | None = None,
        sector_context: SectorContext | None = None,
    ) -> str:
        data_scope = self._data_scope(
            asset_profile_context=asset_profile_context,
            company_peers_context=company_peers_context,
            sector_context=sector_context,
        )
        prompt = (
            BASE_SYSTEM_PROMPT
            + "\n\n"
            + ASSET_SNAPSHOT_PROMPT.format(
                asset=asset,
                asset_type=asset_type.value,
                data_scope=data_scope,
            )
        )

        context_sections = [
            "LLM context block:",
            "1. Provider company profile",
            self._build_profile_context_section(asset_profile_context),
            "2. Sector / industry context",
            self._build_sector_context_section(sector_context),
            "3. Competitive landscape context",
            self._build_peer_context_section(company_peers_context),
            "4. Output requirements",
            (
                "Use the required JSON schema above. Make risks and drivers "
                "specific, materiality-labeled, and mechanism-based."
            ),
            "5. Safety / guardrail rules",
            (
                "Do not provide investment advice, live market claims, recent "
                "news claims, price targets, or buy/sell/hold recommendations."
            ),
            "6. JSON schema",
            f"data_scope must be exactly: {data_scope}",
        ]
        prompt += "\n\n" + "\n".join(context_sections)

        return prompt

    def _build_profile_context_section(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> str:
        if asset_profile_context is None:
            return (
                "Provider: none\n"
                "Status: No provider profile was found. Use stable, general "
                "structural knowledge only."
            )

        return (
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

    def _build_sector_context_section(
        self,
        sector_context: SectorContext | None,
    ) -> str:
        if sector_context is None:
            return "Provider: none\nStatus: No sector context was provided."

        drivers = "\n".join(
            (f"- {driver.title} ({driver.materiality}): {driver.explanation}")
            for driver in sector_context.common_drivers
        )
        risks = "\n".join(
            f"- {risk.title} ({risk.materiality}): {risk.explanation}"
            for risk in sector_context.common_risks
        )
        competition_dimensions = ", ".join(sector_context.competition_dimensions)

        return (
            f"Provider: {sector_context.provider}\n"
            f"Sector: {self._format_optional(sector_context.sector)}\n"
            f"Industry: {self._format_optional(sector_context.industry)}\n"
            "Business model pattern: "
            f"{self._format_optional(sector_context.business_model_pattern)}\n"
            f"Market context: {sector_context.market_context}\n"
            f"Common drivers:\n{drivers or '- Not available'}\n"
            f"Common risks:\n{risks or '- Not available'}\n"
            "Competition dimensions: "
            f"{competition_dimensions or 'Not available'}"
        )

    def _build_peer_context_section(
        self,
        company_peers_context: CompanyPeerContext | None,
    ) -> str:
        if company_peers_context is None:
            return "Provider: none\nStatus: No competitive peer context was provided."

        if not company_peers_context.peers:
            return (
                f"Provider: {company_peers_context.provider}\n"
                f"Asset: {company_peers_context.asset}\n"
                f"Confidence: {company_peers_context.confidence}\n"
                "Peers: none provided. Do not invent obscure competitors."
            )

        peers = "\n".join(
            (
                f"- {peer.name}"
                f"{f' ({peer.ticker})' if peer.ticker else ''}: "
                f"{peer.competition_area}. {peer.why_competitor} "
                f"Why it matters: {peer.why_it_matters}"
            )
            for peer in company_peers_context.peers
        )

        return (
            f"Provider: {company_peers_context.provider}\n"
            f"Asset: {company_peers_context.asset}\n"
            f"Confidence: {company_peers_context.confidence}\n"
            f"Peers:\n{peers}"
        )

    @staticmethod
    def _data_scope(
        asset_profile_context: AssetProfileContext | None,
        company_peers_context: CompanyPeerContext | None,
        sector_context: SectorContext | None,
    ) -> str:
        has_profile = asset_profile_context is not None
        has_sector = sector_context is not None
        has_peers = bool(company_peers_context and company_peers_context.peers)

        if has_profile and has_sector and has_peers:
            return "provider_profile_with_static_sector_and_peer_context"

        if has_profile and has_sector:
            return "provider_profile_with_static_sector_context"

        if has_profile:
            return "provider_profile_only"

        return "model_static_knowledge_fallback"

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
