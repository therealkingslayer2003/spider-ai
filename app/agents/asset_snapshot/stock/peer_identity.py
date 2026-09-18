import logging
import re

from app.domain.schemas.asset_snapshot import PeerRelationship, StockAssetSnapshot
from app.domain.schemas.company_peer_context import CompanyPeersContext

logger = logging.getLogger(__name__)


def restore_peer_tickers(
    snapshot: StockAssetSnapshot,
    context: CompanyPeersContext | None,
) -> StockAssetSnapshot:
    """Restore omitted identity metadata from unambiguous supplied names only."""
    if context is None or not context.peers:
        return snapshot

    identities: dict[str, set[str | None]] = {}
    for candidate in context.peers:
        ticker = (candidate.ticker or "").strip().upper() or None
        for name in (
            candidate.name,
            candidate.profile.name if candidate.profile else None,
            ticker,
        ):
            key = _identity_key(name or "")
            if key:
                identities.setdefault(key, set()).add(ticker)

    restored: list[PeerRelationship] = []
    changed = False
    for peer in snapshot.peer_landscape:
        if (peer.ticker or "").strip():
            restored.append(peer)
            continue

        candidates = identities.get(_identity_key(peer.name), set())
        ticker = next(iter(candidates)) if len(candidates) == 1 else None
        if ticker is None:
            logger.warning(
                "stock.validate_snapshot.peer_ticker_unresolved name=%s "
                "reason=no_unique_supplied_ticker",
                peer.name,
            )
            restored.append(peer)
            continue

        logger.info(
            "stock.validate_snapshot.peer_ticker_restored name=%s ticker=%s",
            peer.name,
            ticker,
        )
        restored.append(peer.model_copy(update={"ticker": ticker}))
        changed = True

    return (
        snapshot.model_copy(update={"peer_landscape": restored})
        if changed
        else snapshot
    )


def _identity_key(value: str) -> str:
    # Ignore presentation differences, not legal suffixes or parts of company names.
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()
