# ruff: noqa: E501

ASSET_SNAPSHOT_PROMPT = """
Your task is to generate a structured Asset Snapshot v1.

The goal is to provide a stable structural profile of the asset. The answer must be specific, competitor-aware, risk-mechanism-aware, and useful for understanding the company as a business.

Asset:
{asset}

Asset type:
{asset_type}

Required data_scope:
{data_scope}

Safety / guardrail rules:
- This is NOT an investment thesis.
- Do NOT create a bull/bear thesis.
- Do NOT provide buy/sell/hold recommendations.
- Do NOT provide personalized financial advice.
- Do NOT make guaranteed predictions.
- Do NOT rely on or pretend to have live market data.
- Do NOT mention recent price moves, latest earnings, latest news, or current valuation unless provided in context.
- For stock snapshots, explain the company as a business, not as a trading recommendation.
- Treat the company profile and business model as the primary basis of the analysis.
- Treat financial fundamentals as supporting evidence for interpreting the economics of the already-understood business model, not the central subject.
- Revenue may provide scale context; revenue growth may characterize growth or maturity; operating margin may inform scalability, pricing power, profitability, or cost sensitivity.
- Use the debt-to-equity ratio as supporting evidence about capital structure and financing dependence. Interpret it with the company's business model and sector. A high ratio is not automatically a structural risk, and a low ratio is not automatically evidence of safety.
- Do not force leverage into the output when it is not material. When it is material, explain the mechanism, such as weaker operating cash generation -> reduced financial flexibility -> greater refinancing or debt-service pressure -> increased balance-sheet vulnerability.
- Interpret every financial fundamental in a company- and sector-aware way. High margin is not automatically bullish, high growth is not automatically a good investment, and high debt is not automatically bad.
- Do NOT perform valuation analysis, estimate fair value, decide whether the stock is cheap or expensive, or introduce P/E, P/S, EV/EBITDA, DCF, or price targets.

Output requirements:
- Return ONLY valid JSON.
- Do not include markdown.
- Do not include code fences.
- Do not include explanations outside JSON.
- Prefer specific competitor names and tickers when provided.
- Named peers in competitive_landscape should come from the provided competitive landscape context.
- If peer context is empty, do not invent obscure competitors.
- If supporting financial fundamentals are empty, continue from the company profile without interpreting their absence.
- Use supplied financial fundamentals only as quantitative evidence for company-specific structural interpretation, never as standalone good/bad signals or valuation evidence.
- Avoid vague risks such as "competition", "regulation", or "technology change" unless each risk explains the concrete mechanism.
- Drivers and risks should follow: business characteristic or structural pressure -> company exposure or dependency -> transmission mechanism -> economic consequence.
- Every structural risk must explain what can go wrong, why it matters, which business area is affected, and materiality.
- Every structural driver and structural risk must use materiality: "low", "medium", or "high".
- data_scope must be exactly: "{data_scope}".

Required JSON schema:

{{
  "asset": "string",
  "asset_type": "string",
  "summary": "string",
  "business_or_asset_profile": "string",
  "market_context": "string",
  "competitive_landscape": [
    {{
      "ticker": "string or null",
      "name": "string",
      "competition_area": "string",
      "why_competitor": "string",
      "why_it_matters": "string"
    }}
  ],
  "structural_drivers": [
    {{
      "title": "string",
      "explanation": "string",
      "materiality": "low | medium | high"
    }}
  ],
  "structural_risks": [
    {{
      "title": "string",
      "explanation": "string",
      "materiality": "low | medium | high",
      "related_competitors": ["string"]
    }}
  ],
  "data_scope": "{data_scope}"
}}

Field requirements:
- "asset": must match the provided asset.
- "asset_type": must match the provided asset type.
- "summary": 2-4 sentences explaining what the company is, what it represents, and why it is relevant.
- "business_or_asset_profile": explain the business model, major economic engines, customer/merchant/user relationships, and economic role.
- "market_context": explain sector, industry, and regulatory context using the company profile and supporting financial fundamentals when available.
- "competitive_landscape": include named competitors from provided peer context when available; explain why each competitor matters.
- "structural_drivers": list 3-6 long-term or recurring drivers with concrete mechanisms and materiality.
- "structural_risks": list 3-6 structural risks with concrete mechanisms, affected business area, materiality, and related_competitors when applicable.
"""
