# ruff: noqa: E501

ASSET_SNAPSHOT_PROMPT = """
Your task is to generate a structured asset snapshot.

The goal is to provide a stable structural profile of the asset.
It should help a retail investor understand what the asset is, how it works, what usually drives it, and what structural risks are associated with it.

This is NOT an investment thesis.
Do NOT create a bull/bear investment thesis.
Do NOT discuss whether the asset is attractive right now.
Do NOT provide buy/sell/hold recommendations.
Do NOT provide personalized financial advice.
Do NOT make guaranteed predictions.

Use only stable, general, structural knowledge about the asset.
Do NOT rely on or pretend to have live market data.
Do NOT mention recent price moves, latest earnings, latest news, or current valuation unless this information is explicitly provided in the user input.

Asset:
{asset}

Asset type:
{asset_type}

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations outside JSON.
Do not wrap the JSON in ```json.

Required JSON schema:

{{
  "asset": "string",
  "asset_type": "string",
  "summary": "string",
  "business_or_asset_profile": "string",
  "market_context": "string",
  "structural_drivers": [
    "string"
  ],
  "structural_risks": [
    "string"
  ],
  "data_scope": "static_asset_profile"
}}

Field requirements:

- "asset": must match the provided asset.
- "asset_type": must match the provided asset type.
- "summary": 2-4 sentences explaining what the asset is, what it represents, and why it is relevant.
- "business_or_asset_profile": explain how the company, asset, currency pair, commodity, index, or crypto asset fundamentally works.
  - For equities: explain the business model, main segments, and economic role.
  - For FX: explain the currency pair and the economies or monetary systems behind it.
  - For commodities: explain the commodity, its use cases, and supply/demand structure.
  - For indices: explain what the index represents and what kind of market exposure it gives.
  - For crypto: explain the asset's purpose, network role, or economic design at a high level.
- "market_context": explain the broader market, sector, macro, or industry environment this asset is usually sensitive to.
- "structural_drivers": list 3-6 long-term or recurring factors that can structurally influence the asset.
- "structural_risks": list 3-6 asset-specific structural risks.
- "data_scope": must be exactly "static_asset_profile".

Important distinction:
This is a stable structural asset profile, not a current investment recommendation.
Do not include current catalysts, live news, valuation judgment, confidence score, evidence score, or thesis conclusion.
"""
