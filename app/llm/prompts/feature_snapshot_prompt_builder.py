from datetime import date

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT

_BUSINESS_SUMMARY_MAX_LENGTH = 1_200


class StockSnapshotPromptBuilder:
    def build_prompt(
        self,
        asset: str,
        asset_type: AssetType,
        asset_profile_context: AssetProfileContext | None = None,
        company_peers_context: CompanyPeersContext | None = None,
        company_fundamentals_context: CompanyFundamentalsContext | None = None,
    ) -> str:
        data_scope = self.data_scope(
            asset_profile_context=asset_profile_context,
            company_peers_context=company_peers_context,
            company_fundamentals_context=company_fundamentals_context,
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
            "1. COMPANY PROFILE",
            self._build_profile_context_section(asset_profile_context),
            "2. COMPETITIVE CONTEXT",
            self._build_peer_context_section(company_peers_context),
            "3. SUPPORTING FINANCIAL FUNDAMENTALS",
            self._build_fundamentals_context_section(company_fundamentals_context),
            "4. Output requirements",
            (
                "Use the required JSON schema above. Make risks and drivers "
                "specific, materiality-labeled, and mechanism-based. The company "
                "profile and business model are the primary basis of the structural "
                "analysis. Financial fundamentals are quantitative supporting "
                "evidence for interpreting business economics, not standalone "
                "bullish/bearish or valuation signals."
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

    def _build_peer_context_section(
        self,
        company_peers_context: CompanyPeersContext | None,
    ) -> str:
        if company_peers_context is None:
            return "Provider: none\nStatus: No competitive peer context was provided."

        if not company_peers_context.peers:
            return (
                f"Provider: {company_peers_context.provider}\n"
                f"Asset: {company_peers_context.asset}\n"
                f"Fetched at: {company_peers_context.fetched_at.isoformat()}\n"
                "Peers: none provided. Do not invent obscure competitors."
            )

        peers = "\n".join(
            (
                f"- {self._format_optional(peer.name)}"
                f"{f' ({peer.ticker})' if peer.ticker else ''}: "
                f"competition_area={self._format_optional(peer.competition_area)}; "
                f"why_competitor={self._format_optional(peer.why_competitor)}; "
                f"why_it_matters={self._format_optional(peer.why_it_matters)}"
            )
            for peer in company_peers_context.peers
        )

        return (
            f"Provider: {company_peers_context.provider}\n"
            f"Asset: {company_peers_context.asset}\n"
            f"Fetched at: {company_peers_context.fetched_at.isoformat()}\n"
            f"Peers:\n{peers}"
        )

    def _build_fundamentals_context_section(
        self,
        context: CompanyFundamentalsContext | None,
    ) -> str:
        if context is None:
            return (
                "Provider: none\n"
                "Status: No supporting financial fundamentals were provided. "
                "Continue from "
                "the company profile; do not infer weak financial quality from "
                "missing metrics."
            )

        metrics = {
            "Revenue": self._format_number(context.revenue),
            "Revenue growth": self._format_ratio(context.revenue_growth),
            "Operating margin": self._format_ratio(context.operating_margin),
            "Debt-to-equity ratio": self._format_multiple(context.debt_to_equity_ratio),
            "Financial currency": context.financial_currency,
            "Latest fiscal year end": self._format_date(context.last_fiscal_year_end),
            "Most recent quarter": self._format_date(context.most_recent_quarter),
        }
        available_metrics = {
            key: value for key, value in metrics.items() if value is not None
        }

        if not available_metrics:
            return (
                f"Provider: {context.provider}\n"
                f"Asset: {context.asset}\n"
                f"Fetched at: {context.fetched_at.isoformat()}\n"
                "Status: No supporting financial fundamentals were available. "
                "Continue "
                "from the company profile and do not interpret their absence."
            )

        formatted = "\n".join(
            f"- {key}: {value}" for key, value in available_metrics.items()
        )

        return (
            f"Provider: {context.provider}\n"
            f"Asset: {context.asset}\n"
            f"Fetched at: {context.fetched_at.isoformat()}\n"
            f"Financial fundamentals:\n{formatted}\n"
            "Interpret these values only together with the supplied company profile "
            "and business model. Revenue provides scale context; revenue growth "
            "helps characterize growth or maturity; operating margin informs "
            "profitability, scalability, pricing power, and cost sensitivity; "
            "the debt-to-equity ratio informs capital structure and financing "
            "dependence. Interpret leverage with the company's business model and "
            "sector: a high ratio is not automatically a structural risk, and a "
            "low ratio is not automatically evidence of safety. Do not invent "
            "missing metrics, force leverage into the analysis when it is not "
            "material, or draw valuation, fair-value, or cheap/expensive conclusions."
        )

    @staticmethod
    def data_scope(
        asset_profile_context: AssetProfileContext | None,
        company_peers_context: CompanyPeersContext | None,
        company_fundamentals_context: CompanyFundamentalsContext | None,
    ) -> str:
        has_peers = bool(company_peers_context and company_peers_context.peers)
        has_financial_signals = bool(
            company_fundamentals_context
            and any(
                value is not None
                for value in (
                    company_fundamentals_context.revenue,
                    company_fundamentals_context.revenue_growth,
                    company_fundamentals_context.operating_margin,
                    company_fundamentals_context.debt_to_equity_ratio,
                )
            )
        )

        if asset_profile_context is None:
            return "model_static_knowledge_fallback"

        if asset_profile_context.provider == "fmp":
            return "fmp_profile_fallback"

        if has_peers and has_financial_signals:
            return "profile_with_peers_and_financial_signals"

        if has_peers:
            return "profile_with_peers"

        if has_financial_signals:
            return "profile_with_financial_signals"

        return "profile_only"

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

    @staticmethod
    def _format_number(value: float | None) -> str | None:
        if value is None:
            return None

        return f"{value:,.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_ratio(value: float | None) -> str | None:
        return f"{value:.2%}" if value is not None else None

    @staticmethod
    def _format_multiple(value: float | None) -> str | None:
        return f"{value:.2f}x" if value is not None else None

    @staticmethod
    def _format_date(value: date | None) -> str | None:
        return value.isoformat() if value is not None else None
