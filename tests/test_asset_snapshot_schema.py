from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.schemas.asset_snapshot import (
    AssetType,
    CompetitivePeer,
    StockAssetSnapshot,
)
from app.domain.schemas.asset_snapshot_evidence import AssetSnapshotEvidence
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)


def test_fundamentals_schema_contains_only_v1_financial_signals() -> None:
    fields = set(CompanyFundamentalsContext.model_fields)

    assert fields == {
        "asset",
        "provider",
        "revenue",
        "revenue_growth",
        "operating_margin",
        "debt_to_equity_ratio",
        "financial_currency",
        "last_fiscal_year_end",
        "most_recent_quarter",
        "fetched_at",
    }


def test_fundamentals_schema_deserializes_reporting_metadata() -> None:
    context = CompanyFundamentalsContext.model_validate(
        {
            "asset": "NVDA",
            "provider": "yfinance",
            "revenue": 100.0,
            "debt_to_equity_ratio": 2.09,
            "financial_currency": "USD",
            "last_fiscal_year_end": "2025-01-26",
            "most_recent_quarter": "2025-07-27",
        }
    )

    assert context.last_fiscal_year_end == date(2025, 1, 26)
    assert context.most_recent_quarter == date(2025, 7, 27)
    assert context.debt_to_equity_ratio == 2.09
    assert "debt_to_equity" not in CompanyFundamentalsContext.model_fields


def test_fundamentals_schema_optional_fields_default_to_none() -> None:
    context = CompanyFundamentalsContext(asset="NVDA", provider="unavailable")

    assert context.revenue is None
    assert context.financial_currency is None
    assert context.last_fiscal_year_end is None
    assert "market_cap" not in context.model_dump()


def test_asset_snapshot_validates_with_structured_fields() -> None:
    snapshot = StockAssetSnapshot.model_validate(
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
            "data_scope": "profile_with_peers_and_financial_signals",
        }
    )

    assert snapshot.asset == "MA"
    assert snapshot.asset_type == AssetType.STOCK
    assert snapshot.competitive_landscape[0].ticker == "V"
    assert snapshot.structural_risks[0].materiality == "high"


def test_asset_snapshot_evidence_contains_contexts_not_snapshot_envelope() -> None:
    assert set(AssetSnapshotEvidence.model_fields) == {
        "asset_profile_context",
        "company_peers_context",
        "company_fundamentals_context",
        "data_scope",
    }


def test_asset_snapshot_normalizes_materiality_case() -> None:
    snapshot = StockAssetSnapshot.model_validate(
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
            "data_scope": "profile_with_peers_and_financial_signals",
        }
    )

    assert snapshot.structural_drivers[0].materiality == "high"
    assert snapshot.structural_risks[0].materiality == "medium"


def test_structural_risk_requires_materiality() -> None:
    with pytest.raises(ValidationError):
        StockAssetSnapshot.model_validate(
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
                "data_scope": "profile_only",
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
