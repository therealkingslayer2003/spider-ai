import pytest

from app.agents.asset_snapshot.stock.nodes import validate_stock_snapshot_node
from app.agents.asset_snapshot.stock.peer_identity import restore_peer_tickers
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from tests.test_nodes import make_profile, make_snapshot


@pytest.mark.parametrize("missing_ticker", [None, "", "   "])
async def test_finalization_restores_missing_tickers_by_name_not_order(
    missing_ticker, caplog
):
    snapshot = make_snapshot("V")
    template = snapshot.peer_landscape[0]
    snapshot.peer_landscape = [
        template.model_copy(update={"name": name, "ticker": missing_ticker})
        for name in ("American Express Company", "Mastercard Inc.")
    ]
    context = CompanyPeersContext(
        asset="V",
        provider="test",
        peers=[
            CompanyPeer(ticker="MA", name="Mastercard Inc."),
            CompanyPeer(ticker="AXP", name="American Express Company"),
        ],
    )
    original_snapshot = snapshot.model_dump_json()
    original_context = context.model_dump_json()
    with caplog.at_level("INFO"):
        result = await validate_stock_snapshot_node(
            {"validated_output": snapshot, "company_peers_context": context}
        )
    output = result["validated_output"]
    assert [peer.ticker for peer in output.peer_landscape] == ["AXP", "MA"]
    for generated, finalized in zip(
        snapshot.peer_landscape, output.peer_landscape, strict=True
    ):
        assert finalized.model_dump(exclude={"ticker"}) == generated.model_dump(
            exclude={"ticker"}
        )
    assert snapshot.model_dump_json() == original_snapshot
    assert context.model_dump_json() == original_context
    assert "peer_ticker_restored" in caplog.text


@pytest.mark.parametrize(
    ("supplied_name", "profile_name", "generated_name"),
    [
        ("Mastercard Inc.", None, "  MASTERCARD   INC "),
        ("Mastercard", "Mastercard Incorporated", "Mastercard Incorporated"),
        (None, "Mastercard Inc.", "Mastercard Inc."),
        (None, None, "ma"),
    ],
)
def test_supplied_names_enriched_names_and_ticker_only_identities(
    supplied_name, profile_name, generated_name
):
    profile = make_profile("MA").model_copy(update={"name": profile_name})
    context = CompanyPeersContext(
        asset="V",
        provider="test",
        peers=[CompanyPeer(ticker=" ma ", name=supplied_name, profile=profile)],
    )
    snapshot = make_snapshot("V")
    snapshot.peer_landscape[0].ticker = None
    snapshot.peer_landscape[0].name = generated_name
    assert restore_peer_tickers(snapshot, context).peer_landscape[0].ticker == "MA"


@pytest.mark.parametrize(
    "peers",
    [
        [],
        [CompanyPeer(name="Shared Name")],
        [CompanyPeer(ticker="ONE", name="Different Name")],
        [CompanyPeer(ticker="ONE", name="Shared Name Incorporated")],
        [
            CompanyPeer(ticker="ONE", name="Shared Name"),
            CompanyPeer(ticker="TWO", name="Shared Name"),
        ],
        [
            CompanyPeer(ticker="ONE", name="Shared Name"),
            CompanyPeer(name="Shared Name"),
        ],
    ],
)
def test_unknown_missing_or_ambiguous_identity_is_not_guessed(peers):
    snapshot = make_snapshot()
    snapshot.peer_landscape[0].ticker = None
    snapshot.peer_landscape[0].name = "Shared Name"
    context = CompanyPeersContext(asset="NVDA", provider="test", peers=peers)
    assert restore_peer_tickers(snapshot, context) is snapshot
    assert snapshot.peer_landscape[0].ticker is None


def test_duplicate_source_records_with_same_ticker_are_not_ambiguous():
    snapshot = make_snapshot()
    snapshot.peer_landscape[0].ticker = None
    peer = CompanyPeer(ticker="AMD", name=snapshot.peer_landscape[0].name)
    context = CompanyPeersContext(asset="NVDA", provider="test", peers=[peer, peer])
    assert restore_peer_tickers(snapshot, context).peer_landscape[0].ticker == "AMD"


def test_no_context_does_not_infer_ticker_from_memory():
    snapshot = make_snapshot()
    snapshot.peer_landscape[0].ticker = None
    assert restore_peer_tickers(snapshot, None) is snapshot


def test_nonempty_generated_ticker_is_not_overwritten_by_name_matching():
    snapshot = make_snapshot()
    context = CompanyPeersContext(
        asset="NVDA",
        provider="test",
        peers=[CompanyPeer(ticker="OTHER", name=snapshot.peer_landscape[0].name)],
    )
    assert restore_peer_tickers(snapshot, context) is snapshot
    assert snapshot.peer_landscape[0].ticker == "AMD"


def test_ambiguous_identity_is_logged(caplog):
    snapshot = make_snapshot()
    snapshot.peer_landscape[0].ticker = None
    context = CompanyPeersContext(
        asset="NVDA", provider="test", peers=[CompanyPeer(ticker="UNKNOWN")]
    )
    with caplog.at_level("WARNING"):
        restore_peer_tickers(snapshot, context)
    assert "peer_ticker_unresolved" in caplog.text
    assert "reason=no_unique_supplied_ticker" in caplog.text
