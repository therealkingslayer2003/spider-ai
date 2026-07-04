from typing import Literal

from pydantic import BaseModel

from app.domain.schemas.asset_snapshot import CompetitivePeer


class CompanyPeerContext(BaseModel):
    asset: str
    peers: list[CompetitivePeer]
    provider: str
    confidence: Literal["low", "medium", "high"]
