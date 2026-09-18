import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.schemas.company_peer_context import CompanyPeer

PeerContextMode = Literal["names_only", "compact", "full"]

PEER_BUSINESS_SUMMARY_MAX_CHARS = 1_200
PEER_BUSINESS_SUMMARY_MAX_SENTENCES = 5

_SENTENCE_END = re.compile(r"[.!?][\"')\]]*(?=\s|$)")
_ABBREVIATIONS = {"inc.", "corp.", "co.", "ltd.", "plc.", "e.g.", "i.e."}


class CompanyPeerPromptProjection(BaseModel):
    """Ephemeral prompt fields, never a replacement for canonical evidence."""

    model_config = ConfigDict(frozen=True)

    ticker: str | None = None
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    business_summary: str | None = None


def project_company_peer(peer: CompanyPeer) -> CompanyPeerPromptProjection:
    profile = peer.profile
    return CompanyPeerPromptProjection(
        ticker=peer.ticker,
        name=peer.name or (profile.name if profile else None),
        sector=profile.sector if profile else None,
        industry=profile.industry if profile else None,
        business_summary=compress_peer_business_summary(
            profile.business_summary if profile else None
        ),
    )


def compress_peer_business_summary(value: str | None) -> str | None:
    normalized = " ".join((value or "").split())
    if not normalized:
        return None
    end = 0
    sentences = 0
    for match in _SENTENCE_END.finditer(normalized):
        # Keep company suffixes and dotted initials within their sentence.
        word = normalized[: match.start() + 1].rsplit(" ", 1)[-1]
        if word.lower() in _ABBREVIATIONS or re.fullmatch(r"(?:[A-Za-z]\.){2,}", word):
            continue
        if match.end() > PEER_BUSINESS_SUMMARY_MAX_CHARS:
            break
        end = match.end()
        sentences += 1
        if sentences == PEER_BUSINESS_SUMMARY_MAX_SENTENCES:
            break

    if (
        sentences < PEER_BUSINESS_SUMMARY_MAX_SENTENCES
        and len(normalized) <= PEER_BUSINESS_SUMMARY_MAX_CHARS
    ):
        return normalized
    if end:
        return normalized[:end]

    limit = PEER_BUSINESS_SUMMARY_MAX_CHARS - 3
    prefix = normalized[:limit]
    if not normalized[limit].isspace():
        prefix = prefix.rpartition(" ")[0]
    return prefix.rstrip() + "..."
