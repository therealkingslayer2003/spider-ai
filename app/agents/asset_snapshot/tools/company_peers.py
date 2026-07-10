from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import CompetitivePeer
from app.domain.schemas.company_peer_context import CompanyPeerContext


def _peer(
    name: str,
    ticker: str | None,
    competition_area: str,
    why_competitor: str,
    why_it_matters: str,
) -> CompetitivePeer:
    return CompetitivePeer(
        ticker=ticker,
        name=name,
        competition_area=competition_area,
        why_competitor=why_competitor,
        why_it_matters=why_it_matters,
    )


_STATIC_PEERS: dict[str, list[CompetitivePeer]] = {
    "MA": [
        _peer(
            name="Visa",
            ticker="V",
            competition_area="Global card network processing",
            why_competitor=(
                "Visa operates a similar global payments network connecting "
                "issuers, merchants, acquirers, and cardholders."
            ),
            why_it_matters=(
                "Visa competes directly for transaction volume, issuer "
                "partnerships, merchant acceptance, and cross-border flows."
            ),
        ),
        _peer(
            name="American Express",
            ticker="AXP",
            competition_area="Card payments and premium consumer/business spending",
            why_competitor=(
                "American Express competes in card-based payments through a "
                "closed-loop network and premium customer base."
            ),
            why_it_matters=(
                "It can pressure Mastercard in high-value spending categories "
                "and corporate or premium payment relationships."
            ),
        ),
        _peer(
            name="PayPal",
            ticker="PYPL",
            competition_area="Digital wallets and online checkout",
            why_competitor=(
                "PayPal competes for online checkout placement, wallet usage, "
                "and merchant payment relationships."
            ),
            why_it_matters=(
                "Wallet-based checkout can redirect transaction flows away "
                "from traditional card-network economics."
            ),
        ),
        _peer(
            name="Block",
            ticker="SQ",
            competition_area="Merchant payments and fintech ecosystems",
            why_competitor=(
                "Block serves merchants and consumers through Square, Cash App, "
                "and related payment services."
            ),
            why_it_matters=(
                "Integrated merchant and consumer ecosystems can pressure "
                "card acceptance, acquiring relationships, and payment flows."
            ),
        ),
        _peer(
            name="Adyen",
            ticker="ADYEN.AS",
            competition_area="Merchant acquiring and payment processing",
            why_competitor=(
                "Adyen provides global merchant acquiring, processing, and "
                "checkout infrastructure for large merchants."
            ),
            why_it_matters=(
                "Large merchant relationships influence routing, acceptance, "
                "and the economics around digital payment processing."
            ),
        ),
    ],
    "V": [
        _peer(
            name="Mastercard",
            ticker="MA",
            competition_area="Global card network processing",
            why_competitor=(
                "Mastercard operates a similar card network and competes for "
                "issuer, merchant, and cross-border volume."
            ),
            why_it_matters=(
                "The two networks compete directly for acceptance, card "
                "issuance partnerships, and transaction economics."
            ),
        ),
        _peer(
            name="American Express",
            ticker="AXP",
            competition_area="Card payments and premium spending",
            why_competitor=(
                "American Express competes in payment cards through a "
                "closed-loop model and premium cardholder base."
            ),
            why_it_matters=(
                "Premium and corporate spending relationships can affect card "
                "network share in high-value categories."
            ),
        ),
        _peer(
            name="PayPal",
            ticker="PYPL",
            competition_area="Digital wallets and online checkout",
            why_competitor=(
                "PayPal competes for digital checkout usage and wallet-based "
                "merchant payment flows."
            ),
            why_it_matters=(
                "Alternative checkout flows can influence network volume and "
                "consumer payment preference."
            ),
        ),
    ],
    "AAPL": [
        _peer(
            name="Samsung Electronics",
            ticker=None,
            competition_area="Smartphones and consumer electronics",
            why_competitor=(
                "Samsung competes directly in premium smartphones, tablets, "
                "wearables, and device ecosystems."
            ),
            why_it_matters=(
                "Device competition affects iPhone unit demand, ecosystem "
                "retention, and pricing power."
            ),
        ),
        _peer(
            name="Alphabet",
            ticker="GOOGL",
            competition_area="Mobile operating systems and services",
            why_competitor=(
                "Alphabet controls Android and competes across mobile services, "
                "distribution, and app ecosystem economics."
            ),
            why_it_matters=(
                "Mobile platform control shapes default services, search "
                "distribution, and developer relationships."
            ),
        ),
        _peer(
            name="Microsoft",
            ticker="MSFT",
            competition_area="Devices, productivity, and platform ecosystems",
            why_competitor=(
                "Microsoft competes in productivity software, cloud services, "
                "devices, and developer ecosystems."
            ),
            why_it_matters=(
                "Platform and productivity competition can influence enterprise "
                "adoption and services growth."
            ),
        ),
    ],
    "MSFT": [
        _peer(
            name="Amazon",
            ticker="AMZN",
            competition_area="Cloud infrastructure",
            why_competitor=(
                "Amazon Web Services competes directly with Azure in cloud "
                "infrastructure and platform services."
            ),
            why_it_matters=(
                "Cloud share drives long-term enterprise relationships, "
                "infrastructure scale, and AI platform economics."
            ),
        ),
        _peer(
            name="Alphabet",
            ticker="GOOGL",
            competition_area="Cloud, search, AI, and productivity ecosystems",
            why_competitor=(
                "Google competes through Google Cloud, search, AI models, "
                "advertising, and productivity software."
            ),
            why_it_matters=(
                "AI and cloud competition can affect Microsoft platform "
                "adoption, pricing, and enterprise wallet share."
            ),
        ),
        _peer(
            name="Apple",
            ticker="AAPL",
            competition_area="Operating systems and devices",
            why_competitor=(
                "Apple competes in devices, operating systems, and ecosystem "
                "control for consumers and professionals."
            ),
            why_it_matters=(
                "Device and platform competition affects distribution, "
                "developer ecosystems, and productivity workflows."
            ),
        ),
    ],
    "AMZN": [
        _peer(
            name="Microsoft",
            ticker="MSFT",
            competition_area="Cloud infrastructure",
            why_competitor=(
                "Microsoft Azure competes directly with AWS for enterprise "
                "cloud workloads and AI infrastructure."
            ),
            why_it_matters=(
                "Cloud competition affects AWS growth, margins, and long-term "
                "enterprise customer relationships."
            ),
        ),
        _peer(
            name="Alphabet",
            ticker="GOOGL",
            competition_area="Cloud and product search advertising",
            why_competitor=(
                "Google competes in cloud services and digital advertising, "
                "including product discovery budgets."
            ),
            why_it_matters=(
                "Cloud and ad competition affects two important Amazon profit "
                "pools: AWS and retail media."
            ),
        ),
        _peer(
            name="Walmart",
            ticker="WMT",
            competition_area="Retail and marketplace commerce",
            why_competitor=(
                "Walmart competes in retail, grocery, marketplace, fulfillment, "
                "and retail media."
            ),
            why_it_matters=(
                "Retail competition affects merchant selection, fulfillment "
                "costs, customer loyalty, and advertising budgets."
            ),
        ),
    ],
    "META": [
        _peer(
            name="Alphabet",
            ticker="GOOGL",
            competition_area="Digital advertising and video attention",
            why_competitor=(
                "Google competes for advertiser budgets through search, "
                "YouTube, display ads, and ad technology."
            ),
            why_it_matters=(
                "Ad budget competition affects pricing, measurement, and "
                "growth across Meta's social platforms."
            ),
        ),
        _peer(
            name="TikTok / ByteDance",
            ticker=None,
            competition_area="Short-form video attention and creator engagement",
            why_competitor=(
                "TikTok competes for user time, creator activity, and brand ad "
                "budgets in short-form video."
            ),
            why_it_matters=(
                "Attention shifts can pressure engagement, ad impressions, and "
                "Meta's ability to monetize social discovery."
            ),
        ),
        _peer(
            name="Snap",
            ticker="SNAP",
            competition_area="Social advertising and messaging",
            why_competitor=(
                "Snap competes for younger audiences, messaging behavior, and "
                "mobile ad budgets."
            ),
            why_it_matters=(
                "Audience fragmentation can affect ad demand and engagement "
                "across Meta's apps."
            ),
        ),
    ],
    "NVDA": [
        _peer(
            name="Advanced Micro Devices",
            ticker="AMD",
            competition_area="GPUs and AI accelerators",
            why_competitor=(
                "AMD competes with Nvidia in data center GPUs, accelerators, "
                "gaming GPUs, and CPU/GPU platform offerings."
            ),
            why_it_matters=(
                "Competitive accelerators can pressure pricing, availability, "
                "and customer diversification."
            ),
        ),
        _peer(
            name="Intel",
            ticker="INTC",
            competition_area="Accelerators, CPUs, and data center platforms",
            why_competitor=(
                "Intel competes in data center compute, CPUs, accelerators, "
                "and platform-level enterprise relationships."
            ),
            why_it_matters=(
                "Data center platform competition can influence customer "
                "architecture choices and procurement decisions."
            ),
        ),
        _peer(
            name="Broadcom",
            ticker="AVGO",
            competition_area="Custom ASICs and networking silicon",
            why_competitor=(
                "Broadcom supplies networking chips and custom silicon used in "
                "large-scale data center and AI infrastructure."
            ),
            why_it_matters=(
                "Custom silicon and networking bottlenecks can affect how much "
                "AI infrastructure spend flows to Nvidia GPUs."
            ),
        ),
    ],
}

_STATIC_PEERS["GOOGL"] = [
    _peer(
        name="Microsoft",
        ticker="MSFT",
        competition_area="Search, cloud, AI platforms, and productivity software",
        why_competitor=(
            "Microsoft competes through Bing, Azure, AI-integrated search, "
            "productivity software, and enterprise AI platforms."
        ),
        why_it_matters=(
            "Microsoft can pressure Alphabet in search behavior, cloud share, "
            "AI platform adoption, and enterprise customer relationships."
        ),
    ),
    _peer(
        name="Meta Platforms",
        ticker="META",
        competition_area="Digital advertising and user attention",
        why_competitor=(
            "Meta competes for advertiser budgets and user attention through "
            "Facebook, Instagram, WhatsApp, and Threads."
        ),
        why_it_matters=(
            "Ad budget and attention competition affects pricing, targeting, "
            "measurement, and growth across digital ads."
        ),
    ),
    _peer(
        name="Amazon",
        ticker="AMZN",
        competition_area="Cloud and product search advertising",
        why_competitor=(
            "Amazon competes through AWS and retail media, including product "
            "search advertising budgets."
        ),
        why_it_matters=(
            "Amazon can pressure Google Cloud and divert high-intent shopping "
            "ad budgets away from Google search."
        ),
    ),
    _peer(
        name="Apple",
        ticker="AAPL",
        competition_area="Mobile ecosystem, browsers, privacy controls, distribution",
        why_competitor=(
            "Apple controls major mobile distribution surfaces and privacy "
            "settings that affect search and advertising access."
        ),
        why_it_matters=(
            "Distribution and privacy changes can affect default search "
            "placement, ad measurement, and traffic acquisition economics."
        ),
    ),
    _peer(
        name="TikTok / ByteDance",
        ticker=None,
        competition_area="Video attention and advertising budgets",
        why_competitor=(
            "TikTok competes with YouTube and other Google surfaces for user "
            "attention, creator activity, and brand advertising."
        ),
        why_it_matters=(
            "Video attention shifts can affect YouTube engagement and ad "
            "monetization growth."
        ),
    ),
]
_STATIC_PEERS["GOOG"] = _STATIC_PEERS["GOOGL"]


class CompanyPeersTool:
    async def run(
        self,
        asset: str,
        asset_profile_context: AssetProfileContext | None,
    ) -> CompanyPeerContext:
        normalized_asset = asset.strip().upper()
        peers = list(_STATIC_PEERS.get(normalized_asset, []))

        if not peers and asset_profile_context is not None:
            peers = list(_STATIC_PEERS.get(asset_profile_context.asset.upper(), []))

        return CompanyPeerContext(
            asset=normalized_asset,
            peers=peers,
            provider="static_company_peer_mapping_v1",
            confidence="high" if peers else "low",
        )
