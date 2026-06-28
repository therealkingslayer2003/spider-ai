from pydantic import BaseModel, Field


class AmbiguousAssetResolution(BaseModel):
    original_asset: str
    resolved_asset: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
