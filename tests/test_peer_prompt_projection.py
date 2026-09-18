from datetime import UTC, datetime

import pytest

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.llm.prompts.company_peer_projection import (
    PEER_BUSINESS_SUMMARY_MAX_CHARS,
    PEER_BUSINESS_SUMMARY_MAX_SENTENCES,
    CompanyPeerPromptProjection,
    PeerContextMode,
    compress_peer_business_summary,
    project_company_peer,
)
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder


@pytest.fixture
def peer() -> CompanyPeer:
    return CompanyPeer(
        ticker="MSFT",
        name="Microsoft Corporation",
        provider="fmp",
        profile=AssetProfileContext(
            asset="MSFT",
            asset_type=AssetType.STOCK,
            name="Microsoft Corporation",
            sector="Technology",
            industry="Software - Infrastructure",
            business_summary=(
                "Develops software and cloud services. Serves enterprise customers. "
                + "Additional detailed provider evidence. " * 40
            ),
            exchange="NASDAQ",
            currency="USD",
            country="United States",
            website="https://example.com",
            provider="yfinance",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def test_projection_whitelist_and_canonical_evidence_are_unchanged(peer) -> None:
    original = peer.model_dump_json()

    projection = project_company_peer(peer)

    assert isinstance(projection, CompanyPeerPromptProjection)
    assert projection.model_dump() == {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "business_summary": (
            "Develops software and cloud services. Serves enterprise customers. "
            "Additional detailed provider evidence. "
            "Additional detailed provider evidence. "
            "Additional detailed provider evidence."
        ),
    }
    assert peer.model_dump_json() == original


@pytest.mark.parametrize("value", [None, "", " ", "\n\t\r"])
def test_missing_summary(value) -> None:
    assert compress_peer_business_summary(value) is None


def test_short_summary_only_normalizes_whitespace() -> None:
    value = "  Makes\tchips.\n Sells  hardware.\r\nOffers services. "
    assert compress_peer_business_summary(value) == (
        "Makes chips. Sells hardware. Offers services."
    )


@pytest.mark.parametrize(
    "value", ["Makes chips", "Makes chips. Sells hardware without a final period"]
)
def test_short_summary_preserves_text_without_final_punctuation(value) -> None:
    assert compress_peer_business_summary(value) == value


def test_summary_at_character_budget_is_unchanged() -> None:
    value = "A" * (PEER_BUSINESS_SUMMARY_MAX_CHARS - 1) + "."
    assert compress_peer_business_summary(value) == value


@pytest.mark.parametrize("extra_sentences", [1, 100])
def test_summary_keeps_five_opening_sentences_even_below_character_budget(
    extra_sentences,
) -> None:
    opening = (
        "Makes chips. Sells hardware. Licenses software. "
        "Operates data centers. Provides technical support."
    )
    value = opening + " Offers services." * extra_sentences
    result = compress_peer_business_summary(value)
    assert result == opening
    assert result.count(".") == PEER_BUSINESS_SUMMARY_MAX_SENTENCES == 5
    assert len(result) <= PEER_BUSINESS_SUMMARY_MAX_CHARS
    assert compress_peer_business_summary(value) == result
    assert value.startswith(result)


def test_five_sentences_can_exceed_previous_character_budget() -> None:
    sentences = [
        "Develops enterprise software for business customers managing accounting, "
        "procurement, and workforce operations.",
        "Operates cloud infrastructure that hosts customer applications and "
        "supports their data processing workloads.",
        "Licenses productivity software to organizations through recurring "
        "subscriptions and long term service agreements.",
        "Provides security products that protect customer identities, endpoints, "
        "and access to hosted applications.",
        "Sells technical support and implementation services to help customers "
        "deploy and maintain its software products.",
    ]
    opening = " ".join(sentences)
    assert 420 < len(opening) < PEER_BUSINESS_SUMMARY_MAX_CHARS
    assert compress_peer_business_summary(opening) == opening
    assert compress_peer_business_summary(opening + " A sixth sentence.") == opening


def test_second_sentence_does_not_fit_returns_complete_first_sentence() -> None:
    first = "Manufactures processors."
    value = first + " Supplies" * PEER_BUSINESS_SUMMARY_MAX_CHARS + "."
    assert compress_peer_business_summary(value) == first


@pytest.mark.parametrize(
    "opening",
    [
        "Alphabet Inc. provides online services. It operates cloud platforms.",
        "Acme Corp. sells devices in the U.S. and Europe. It licenses software.",
        'It sells devices! It also offers "cloud services."',
        "It supplies 2.5 liter containers. It recycles packaging?",
    ],
)
def test_sentence_boundaries_preserve_abbreviations_decimals_and_quotes(
    opening,
) -> None:
    expected = opening + " Further evidence." * 3
    assert (
        compress_peer_business_summary(opening + " Further evidence." * 100) == expected
    )


@pytest.mark.parametrize("punctuation", [".", ""])
def test_oversized_first_sentence_truncates_at_word_boundary(punctuation) -> None:
    value = "Manufactures " + "semiconductors " * 80 + punctuation
    result = compress_peer_business_summary(value)
    assert result is not None
    assert result.endswith("semiconductors...")
    assert len(result) <= PEER_BUSINESS_SUMMARY_MAX_CHARS
    assert value.startswith(result[:-3])
    assert compress_peer_business_summary(value) == result


def test_single_oversized_word_is_not_split() -> None:
    assert (
        compress_peer_business_summary("A" * (PEER_BUSINESS_SUMMARY_MAX_CHARS + 1))
        == "..."
    )


def test_missing_profile_and_name_only_peer_are_preserved() -> None:
    assert project_company_peer(CompanyPeer(ticker="XYZ")).model_dump(
        exclude_none=True
    ) == {"ticker": "XYZ"}
    assert project_company_peer(CompanyPeer(name="Private Company")).model_dump(
        exclude_none=True
    ) == {"name": "Private Company"}


def test_name_can_come_from_profile(peer) -> None:
    peer.name = None
    assert project_company_peer(peer).name == "Microsoft Corporation"


def test_compact_context_whitelist_provenance_and_debug_budget(peer, caplog) -> None:
    context = CompanyPeersContext(asset="AAPL", provider="fmp", peers=[peer])
    original = context.model_dump_json()
    with caplog.at_level("DEBUG"):
        section = StockSnapshotPromptBuilder()._build_peer_context_section(context)

    assert "Peer discovery provider: fmp" in section
    assert "Peer profile provider: yfinance" in section
    assert "- MSFT | Microsoft Corporation" in section
    assert "Sector: Technology" in section
    assert "Industry: Software - Infrastructure" in section
    assert "Business: Develops software and cloud services." in section
    for omitted in ("Fetched at", "Exchange", "Currency", "Country", "Website", "None"):
        assert omitted not in section
    assert context.model_dump_json() == original
    assert "snapshot_prompt.peer_context peer_count=1" in caplog.text
    assert f"peer_context_chars={len(section)} mode=compact" in caplog.text


def test_mixed_profile_provenance_and_missing_profiles(peer) -> None:
    other = peer.model_copy(deep=True)
    other.ticker = "GOOGL"
    assert other.profile is not None
    other.profile.provider = "fmp"
    context = CompanyPeersContext(
        asset="AAPL",
        provider="fmp",
        peers=[peer, other, CompanyPeer(ticker="XYZ"), CompanyPeer(name="Private Co")],
    )
    section = StockSnapshotPromptBuilder()._build_peer_context_section(context)
    assert "Peer discovery provider: fmp" in section
    assert "Peer profile providers: yfinance (MSFT); fmp (GOOGL)" in section
    assert section.endswith("- XYZ\n- Private Co")
    assert "Retain peers without profiles" in section


def test_sparse_context_has_no_profile_attribution() -> None:
    section = StockSnapshotPromptBuilder()._build_peer_context_section(
        CompanyPeersContext(
            asset="AAPL", provider="fmp", peers=[CompanyPeer(ticker="XYZ")]
        )
    )
    assert section.endswith("- XYZ")
    assert "Peer profile provider" not in section
    assert "Sector:" not in section
    assert "Business:" not in section


@pytest.mark.parametrize("mode", ["names_only", "compact", "full"])
def test_all_nine_peers_retained_in_order_in_every_mode(peer, mode: PeerContextMode):
    context = CompanyPeersContext(
        asset="AAPL",
        provider="fmp",
        peers=[peer.model_copy(update={"ticker": f"PEER{i}"}) for i in range(9)],
    )
    section = StockSnapshotPromptBuilder(
        peer_context_mode=mode
    )._build_peer_context_section(context)
    positions = [section.index(f"PEER{i}") for i in range(9)]
    assert positions == sorted(positions)
    assert len([line for line in section.splitlines() if line.startswith("- ")]) == 9


def test_ablation_changes_only_peer_context_not_target_or_feature_prompt(peer) -> None:
    assert peer.profile is not None
    context = CompanyPeersContext(asset="AAPL", provider="fmp", peers=[peer])
    sections = {}
    prompts = []
    modes: tuple[PeerContextMode, ...] = ("names_only", "compact", "full")
    for mode in modes:
        builder = StockSnapshotPromptBuilder(peer_context_mode=mode)
        sections[mode] = builder._build_peer_context_section(context)
        prompt = builder.build_prompt("AAPL", AssetType.STOCK, peer.profile, context)
        prompts.append(prompt.replace(sections[mode], "PEER CONTEXT"))

    assert prompts[0] == prompts[1] == prompts[2]
    assert "Additional detailed provider evidence." in prompts[0]  # Target unchanged.
    assert (
        len(sections["names_only"]) < len(sections["compact"]) < len(sections["full"])
    )
    assert "Business:" not in sections["names_only"]
    assert "Peer profile provider:" not in sections["names_only"]
    assert sections["compact"].count("Additional detailed provider evidence.") == 3
    assert sections["full"].count("Additional detailed provider evidence.") > 3
    assert "Fetched at:" in sections["full"]
