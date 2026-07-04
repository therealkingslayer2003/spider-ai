import pytest
from pydantic import ValidationError

from app.domain.schemas.asset_snapshot import (
    AssetSnapshot,
    AssetType,
    CompetitivePeer,
)


def test_asset_snapshot_validates_with_structured_fields() -> None:
    snapshot = AssetSnapshot.model_validate(
        {
            "asset": "MA",
            "asset_type": "stock",
            "summary": "Mastercard operates a global card network.",
            "business_or_asset_profile": "It earns fees from payment volume.",
            "market_context": "Payments are shaped by merchant acceptance.",
            "competitive_landscape": [
                {
                    "ticker": "V",
                    "name": "Visa",
                    "competition_area": "Card network processing",
                    "why_competitor": "Visa operates a similar network.",
                    "why_it_matters": "It competes for transaction volume.",
                }
            ],
            "structural_drivers": [
                {
                    "title": "Cross-border volume",
                    "explanation": "Travel and commerce support payment volume.",
                    "materiality": "high",
                }
            ],
            "structural_risks": [
                {
                    "title": "Payment regulation",
                    "explanation": "Fee caps can reduce transaction economics.",
                    "materiality": "high",
                    "related_competitors": ["V"],
                }
            ],
            "data_scope": "provider_profile_with_static_sector_and_peer_context",
        }
    )

    assert snapshot.asset == "MA"
    assert snapshot.asset_type == AssetType.STOCK
    assert snapshot.competitive_landscape[0].ticker == "V"
    assert snapshot.structural_risks[0].materiality == "high"


def test_asset_snapshot_normalizes_materiality_case() -> None:
    snapshot = AssetSnapshot.model_validate(
        {
            "asset": "GOOGL",
            "asset_type": "stock",
            "summary": "Alphabet operates digital platforms.",
            "business_or_asset_profile": "It earns revenue from advertising.",
            "market_context": "Digital advertising is competitive.",
            "competitive_landscape": [],
            "structural_drivers": [
                {
                    "title": "Search advertising",
                    "explanation": "Search intent supports ad demand.",
                    "materiality": "High",
                }
            ],
            "structural_risks": [
                {
                    "title": "AI search substitution",
                    "explanation": "New discovery formats can pressure queries.",
                    "materiality": "Medium",
                    "related_competitors": ["MSFT"],
                }
            ],
            "data_scope": "provider_profile_with_static_sector_and_peer_context",
        }
    )

    assert snapshot.structural_drivers[0].materiality == "high"
    assert snapshot.structural_risks[0].materiality == "medium"


def test_structural_risk_requires_materiality() -> None:
    with pytest.raises(ValidationError):
        AssetSnapshot.model_validate(
            {
                "asset": "MA",
                "asset_type": "stock",
                "summary": "Mastercard operates a global card network.",
                "business_or_asset_profile": "It earns fees from payment volume.",
                "market_context": "Payments are shaped by merchant acceptance.",
                "competitive_landscape": [],
                "structural_drivers": [],
                "structural_risks": [
                    {
                        "title": "Payment regulation",
                        "explanation": "Fee caps can reduce economics.",
                        "related_competitors": ["V"],
                    }
                ],
                "data_scope": "provider_profile_only",
            }
        )


def test_competitive_peer_validates_with_nullable_ticker() -> None:
    peer = CompetitivePeer(
        ticker=None,
        name="TikTok / ByteDance",
        competition_area="Video attention",
        why_competitor="Competes for user time and creator activity.",
        why_it_matters="Attention shifts can pressure ad inventory.",
    )

    assert peer.ticker is None
