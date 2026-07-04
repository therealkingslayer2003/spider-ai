from typing import Literal

from pydantic import BaseModel


class SectorDriverContext(BaseModel):
    title: str
    explanation: str
    materiality: Literal["low", "medium", "high"]


class SectorRiskContext(BaseModel):
    title: str
    explanation: str
    materiality: Literal["low", "medium", "high"]


class SectorContext(BaseModel):
    sector: str | None
    industry: str | None
    business_model_pattern: str | None
    market_context: str
    common_drivers: list[SectorDriverContext]
    common_risks: list[SectorRiskContext]
    competition_dimensions: list[str]
    provider: str
