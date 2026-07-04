from typing import Literal

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.sector_context import (
    SectorContext,
    SectorDriverContext,
    SectorRiskContext,
)


def _driver(
    title: str,
    explanation: str,
    materiality: Literal["low", "medium", "high"],
) -> SectorDriverContext:
    return SectorDriverContext(
        title=title,
        explanation=explanation,
        materiality=materiality,
    )


def _risk(
    title: str,
    explanation: str,
    materiality: Literal["low", "medium", "high"],
) -> SectorRiskContext:
    return SectorRiskContext(
        title=title,
        explanation=explanation,
        materiality=materiality,
    )


_PAYMENTS_CONTEXT = SectorContext(
    sector="Financial Services",
    industry="Payments / Transaction Processing / Financial Technology",
    business_model_pattern=(
        "Network, processing, wallet, acquiring, or merchant-services economics "
        "based on payment volume, acceptance, trust, and transaction routing."
    ),
    market_context=(
        "Payments companies are structurally shaped by merchant acceptance, "
        "issuer and acquirer relationships, consumer spending, cross-border "
        "travel, fraud prevention, and regulation around interchange and fees."
    ),
    common_drivers=[
        _driver(
            "Card network effects and acceptance scale",
            (
                "More cardholders, issuers, merchants, and acquirers improve "
                "acceptance and reinforce transaction volume."
            ),
            "high",
        ),
        _driver(
            "Cross-border volume and travel recovery",
            (
                "International transactions often carry stronger economics, so "
                "travel and cross-border commerce can materially influence growth."
            ),
            "high",
        ),
        _driver(
            "Digital checkout and wallet adoption",
            (
                "Online checkout, tokenization, wallets, and merchant routing "
                "shape how payment volume reaches networks and processors."
            ),
            "medium",
        ),
    ],
    common_risks=[
        _risk(
            "Interchange and payment regulation",
            (
                "Regulators can cap interchange fees, change routing rules, or "
                "pressure network economics, affecting payment revenue per "
                "transaction."
            ),
            "high",
        ),
        _risk(
            "Alternative payment rails and wallets",
            (
                "Real-time payments, account-to-account transfers, and wallets "
                "can redirect transaction flows away from traditional card rails."
            ),
            "medium",
        ),
        _risk(
            "Fraud, cybersecurity, and trust",
            (
                "Payment networks and processors depend on reliability and "
                "trust; fraud or outages can harm acceptance and relationships."
            ),
            "high",
        ),
    ],
    competition_dimensions=[
        "issuer and merchant partnerships",
        "global acceptance",
        "cross-border payment flows",
        "digital checkout placement",
        "merchant acquiring and payment processing",
        "alternative payment rails",
    ],
    provider="static_sector_context_v1",
)

_DIGITAL_ADS_CONTEXT = SectorContext(
    sector="Communication Services",
    industry="Digital Advertising / Internet Content / Search",
    business_model_pattern=(
        "Advertising and platform economics based on user attention, intent, "
        "targeting, measurement, distribution, and content engagement."
    ),
    market_context=(
        "Digital advertising platforms compete for user attention and advertiser "
        "budgets across search, social feeds, video, retail media, and emerging "
        "AI or vertical discovery experiences."
    ),
    common_drivers=[
        _driver(
            "Search and high-intent advertising demand",
            (
                "Search and commerce-oriented discovery can produce valuable ad "
                "inventory because users often signal purchase or research intent."
            ),
            "high",
        ),
        _driver(
            "Video, creator, and attention engagement",
            (
                "Platforms with durable video and creator engagement can expand "
                "ad inventory and defend user time."
            ),
            "medium",
        ),
        _driver(
            "AI and cloud adjacency",
            (
                "AI models, cloud platforms, and developer ecosystems can create "
                "new product surfaces and enterprise relationships."
            ),
            "medium",
        ),
    ],
    common_risks=[
        _risk(
            "AI search and vertical discovery disruption",
            (
                "AI assistants, retail media, and vertical platforms can change "
                "where users begin discovery, pressuring search ad economics."
            ),
            "high",
        ),
        _risk(
            "Privacy regulation and measurement limits",
            (
                "Platform privacy controls and regulation can reduce targeting "
                "precision, attribution quality, and ad pricing power."
            ),
            "high",
        ),
        _risk(
            "Antitrust and distribution pressure",
            (
                "Regulators may challenge platform bundling, default placement, "
                "data usage, or ecosystem control."
            ),
            "high",
        ),
    ],
    competition_dimensions=[
        "search advertising",
        "YouTube and video attention",
        "social advertising",
        "retail media",
        "AI-assisted search",
        "mobile ecosystem distribution",
    ],
    provider="static_sector_context_v1",
)

_CLOUD_CONTEXT = SectorContext(
    sector="Technology",
    industry="Cloud / Enterprise Software / AI Infrastructure",
    business_model_pattern=(
        "Enterprise platform economics based on recurring software, cloud usage, "
        "developer ecosystems, AI infrastructure, and switching costs."
    ),
    market_context=(
        "Cloud and enterprise software companies compete on platform breadth, "
        "developer adoption, AI capabilities, reliability, security, and total "
        "cost of ownership."
    ),
    common_drivers=[
        _driver(
            "Cloud adoption and workload migration",
            (
                "Enterprise migration to cloud platforms expands infrastructure, "
                "database, analytics, and platform-service revenue."
            ),
            "high",
        ),
        _driver(
            "AI infrastructure and platform demand",
            (
                "AI workloads can increase demand for compute, data platforms, "
                "developer tools, and enterprise software integration."
            ),
            "high",
        ),
        _driver(
            "Ecosystem lock-in and enterprise relationships",
            (
                "Integrated platforms can deepen switching costs and expand "
                "wallet share across software, cloud, and security."
            ),
            "medium",
        ),
    ],
    common_risks=[
        _risk(
            "Hyperscaler competition and pricing pressure",
            (
                "AWS, Azure, and Google Cloud compete for workloads, which can "
                "pressure pricing, margins, and customer acquisition economics."
            ),
            "high",
        ),
        _risk(
            "Capex intensity",
            (
                "AI and cloud infrastructure require large capital spending, "
                "which can pressure free cash flow if demand or utilization lags."
            ),
            "medium",
        ),
        _risk(
            "Enterprise spending cycles",
            (
                "IT budget slowdowns can delay migrations, expansions, and "
                "software seat growth."
            ),
            "medium",
        ),
    ],
    competition_dimensions=[
        "cloud infrastructure",
        "AI platforms",
        "enterprise software suites",
        "developer ecosystems",
        "security and data platforms",
    ],
    provider="static_sector_context_v1",
)

_SEMICONDUCTOR_CONTEXT = SectorContext(
    sector="Technology",
    industry="Semiconductors / AI Hardware",
    business_model_pattern=(
        "Chip and platform economics based on accelerator demand, ecosystem "
        "software, supply chain capacity, and data center capital spending."
    ),
    market_context=(
        "AI hardware and semiconductor companies are shaped by data center "
        "capex, accelerator performance, supply constraints, foundry capacity, "
        "export controls, cyclicality, and custom silicon competition."
    ),
    common_drivers=[
        _driver(
            "AI accelerator and data center demand",
            (
                "Training and inference workloads can drive sustained demand "
                "for high-performance accelerators and networking."
            ),
            "high",
        ),
        _driver(
            "Software ecosystem and platform adoption",
            (
                "Developer tools, libraries, and installed base can reinforce "
                "customer adoption and switching costs."
            ),
            "high",
        ),
        _driver(
            "Supply chain execution and foundry capacity",
            (
                "Advanced packaging, foundry access, and memory supply can "
                "shape revenue timing and customer availability."
            ),
            "medium",
        ),
    ],
    common_risks=[
        _risk(
            "Custom ASIC and alternative accelerator competition",
            (
                "Cloud providers, AMD, Intel, and ASIC vendors can reduce "
                "dependence on incumbent GPU platforms."
            ),
            "high",
        ),
        _risk(
            "Export controls and geopolitical constraints",
            (
                "Restrictions on advanced chips can limit access to major "
                "markets and require product redesigns."
            ),
            "high",
        ),
        _risk(
            "Semiconductor cyclicality",
            (
                "Demand can swing with inventory cycles, capex digestion, and "
                "customer budget timing."
            ),
            "medium",
        ),
    ],
    competition_dimensions=[
        "AI accelerators",
        "data center GPUs",
        "custom ASICs",
        "foundry and packaging capacity",
        "networking and systems platforms",
    ],
    provider="static_sector_context_v1",
)

_GENERIC_STOCK_CONTEXT = SectorContext(
    sector=None,
    industry=None,
    business_model_pattern="Public company business economics.",
    market_context=(
        "The company should be evaluated through stable business model, sector, "
        "competitive position, customer demand, cost structure, and regulation."
    ),
    common_drivers=[
        _driver(
            "Revenue growth and market demand",
            (
                "Long-term demand for the company's products or services "
                "usually shapes revenue durability."
            ),
            "medium",
        ),
        _driver(
            "Competitive position",
            (
                "Scale, differentiation, brand, distribution, or technology can "
                "support or weaken business economics."
            ),
            "medium",
        ),
    ],
    common_risks=[
        _risk(
            "Competitive pressure",
            (
                "Competitors can pressure pricing, market share, margins, or "
                "customer relationships."
            ),
            "medium",
        ),
        _risk(
            "Execution and operating risk",
            (
                "Poor execution can affect product quality, customer retention, "
                "cost discipline, or strategic positioning."
            ),
            "medium",
        ),
    ],
    competition_dimensions=[
        "market share",
        "pricing power",
        "customer relationships",
        "operating execution",
    ],
    provider="static_sector_context_v1",
)


class SectorContextTool:
    async def run(
        self,
        asset_profile_context: AssetProfileContext | None,
    ) -> SectorContext:
        if asset_profile_context is None:
            return _GENERIC_STOCK_CONTEXT

        return _select_context(
            sector=asset_profile_context.sector,
            industry=asset_profile_context.industry,
            business_summary=asset_profile_context.business_summary,
        )


def _select_context(
    sector: str | None,
    industry: str | None,
    business_summary: str | None,
) -> SectorContext:
    text = " ".join(
        value.lower()
        for value in (sector, industry, business_summary)
        if value is not None
    )

    if any(
        keyword in text
        for keyword in (
            "payment",
            "transaction",
            "card",
            "financial technology",
            "fintech",
        )
    ):
        return _PAYMENTS_CONTEXT

    if any(
        keyword in text
        for keyword in (
            "advertising",
            "search",
            "internet content",
            "social",
            "communication services",
        )
    ):
        return _DIGITAL_ADS_CONTEXT

    if any(
        keyword in text
        for keyword in (
            "cloud",
            "enterprise software",
            "productivity",
            "software infrastructure",
            "ai infrastructure",
        )
    ):
        return _CLOUD_CONTEXT

    if any(
        keyword in text
        for keyword in (
            "semiconductor",
            "gpu",
            "accelerator",
            "chip",
            "ai hardware",
        )
    ):
        return _SEMICONDUCTOR_CONTEXT

    return _GENERIC_STOCK_CONTEXT
