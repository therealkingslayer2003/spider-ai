ASSET_SNAPSHOT_PROMPT = """
Generate a structured Stock Asset Snapshot for {asset}, asset_type {asset_type},
with data_scope exactly "{data_scope}".

## TASK AND SCOPE

Explain this company's economic identity, monetization, major business engines,
durable strengths/dependencies, and material competitive/industry forces. Focus on
persistent characteristics, not temporary events, current investment theses,
news analysis, price forecasts, or trading recommendations.

## RESEARCH METHOD

Act as a careful equity researcher. Internally reason:
business model -> economic engines and dependencies -> financial characterization
-> competitive pressures -> structural drivers/risks -> causal economic consequences.
Explain why THIS business is scalable, resilient, dependent, exposed, or hard to
compete with. Build an economic model, not a paraphrase or dataset-completeness review.

## GROUNDING AND MISSING DATA

Evidence priority: supplied target company profile > supplied peer profile/context
> supplied financial fundamentals > stable model knowledge > conservative inference.
The company profile and business model are primary; peers and financial signals
refine them. Provider evidence takes precedence over memory.

Provider evidence is the primary source of truth. Stable model knowledge MAY
supplement it, including when profiles are present or compressed, ONLY for
high-confidence, widely established, structurally persistent company/industry facts:
long-established products/platforms, durable activities, competitive relationships,
industry structure, and general economic principles. It must never override
contradictory provider evidence. Example: established Android/iOS platform competition
may clarify an overlap omitted by compact profiles; do not label it provider-retrieved.

Model memory must not introduce unsupplied numerical claims, current metrics or market
shares, recent contracts, supplier/customer relationships, partnerships, regulatory
actions, product/news developments, or obscure/uncertain company-specific facts.
Time-sensitive relationships require supplied provider evidence. Economic reasoning
may interpret supported facts and consequences; distinguish provider facts, stable
knowledge and analytical inference. Do not invent facts about fictional entities.
Use partial evidence,
never guess missing values or infer characteristics requiring them. Missing data
is absence of evidence, not positive/negative evidence or a business driver/risk.
No margin -> no financial profitability claim; no debt-to-equity ratio -> no leverage
claim; no revenue growth -> no fast/declining growth classification from that metric.
When the company profile is unavailable, data_scope remains
"model_static_knowledge_fallback": use stable general knowledge conservatively under
the same limits. Supplemental knowledge never authorizes inventing peer identities
or silently upgrading missing provider data. If support is unreliable, qualify it.

## EVIDENCE INTERPRETATION

### Company profile

- name identifies the company only.
- sector is broad context, insufficient for company-specific risks. industry refines
  economic/competitive context and durable pressures, not identical firm economics.
- exchange is identification/listing context only, not a business conclusion.
  currency is trading/listing context, not revenue exposure or reporting currency.
- country needs a defensible business link: regulation, geographic concentration,
  production dependency, or jurisdictional constraints; it alone proves no risk.
- business_summary is the primary source for products/services, customers/users/
  merchants, value creation, supported monetization or economic role, central
  activities, dependencies, and visible advantages. Translate facts into economics.

Avoid "Technology companies face innovation risk": connect a specific change to
this company's product, revenue engine, cost structure, or advantage.

### Provider-reported peers

Acknowledge EVERY distinct identifiable supplied peer in peer_landscape,
including failed/partial enrichment and different businesses. Preserve supplied
tickers/names; ticker-only -> use ticker as name, never invent an identity.
Enrichment qualifies explanations, not eligibility. Empty landscape is acceptable
ONLY without identifiable supplied peers, not proof the company has no competitors.

Provider-reported peer != proven direct competitor. Inspect the target profile and
compact peer profile first; optionally add permitted stable knowledge; identify
economic overlap; classify peer_type conservatively; explain the relationship and
its relevance to the TARGET. Inspect products/services, customers/user groups,
spending, channels, platforms/ecosystems, technology, transaction flows, monetization/
revenue pools and broader activities. peer_type and the explanation fields are
analytical OUTPUT fields, not expected provider fields.

peer_type must be exactly one of:
- direct_competitor: substantial competition through the same/strongly overlapping
  offering AND demand, customers, economic activity or revenue pool.
- indirect_competitor: different offering that substitutes for part of the same
  economic need, e.g. spending, platform usage, transactions, advertising or ecosystems.
- comparable: broad economic/industry/business similarity, but no sufficiently
  supported competitive mechanism. Provider grouping alone does not prove similarity.
- unclear: supplied evidence plus permitted stable knowledge cannot classify reliably.
Prefer comparable when broad similarity is supported, otherwise unclear, rather than
hallucinating competition. Do not force diversity across types. Do not add supplier,
customer, partner or complementor types; a profile alone does not prove those links.

For each peer:
- relationship_area: specific supported overlap (e.g. operating systems, payment
  processing), broader comparability, or an explicit area-of-relationship limitation.
- why_relevant: one coherent explanation combining WHY the relationship exists
  AND HOW it could structurally matter to the TARGET's economics. Use evidence and
  permitted stable knowledge; distinguish competition from broad comparability
  or unconfirmed relevance. Connect the supported relationship to target pricing,
  retention, activity, ecosystem, differentiation, R&D, distribution, monetization,
  growth, margins or competitive position, or explain why impact cannot be assessed.
  Preserve both the relationship reasoning and economic significance without
  repetitive sections. Use explanatory prose, never only a high/medium/low rating.
  Never invent measured impacts, market shares, dominance, or facts.

Pricing, switching, distribution, acquisition costs, R&D demands, differentiation,
market share, transaction volume, and substitution require supported mechanisms;
none follows from peer membership. Missing enrichment limits explanation, not inclusion.

Example with insufficient evidence AND no reliable stable knowledge: peer_type =
"unclear"; relationship_area = "Provider-reported peer; specific overlap is not
established"; why_relevant = "Included by the provider, but available information
does not establish the relationship or its specific economic impact on the target."
For a present but different business, qualify absent overlap, not a "missing profile".
Accurate qualifications are substantive analysis; bare "Not available" is not.
Explain supported overlap when present instead of using a blanket disclaimer.
Missing enrichment alone does not prohibit classification using reliable stable facts.

### Financial fundamentals

Financial fundamentals are quantitative supporting evidence, not standalone
drivers/risks, quality judgments, bullish/bearish signals, or investment conclusions.
Connect each use to the business model and an actual economic mechanism.

- revenue: scale context only; alone it proves neither quality, profitability,
  growth, nor valuation attractiveness. Large does not automatically mean safe.
- revenue_growth: observed expansion/maturity and growth dependence. Explain which
  activity needs growth and its structural supports/constraints; high growth is not
  automatically bullish, low growth not weakness.
- operating_margin: operating profitability, scalability, cost sensitivity, pricing,
  operating leverage, and profit resilience; high margin alone proves no moat or
  bullish signal. Example: supported pricing pressure -> core product monetization
  -> lower revenue per customer/transaction -> weaker operating profits.
- debt_to_equity_ratio: capital structure/financing dependence, as a normalized
  multiple (2.0 = approximately 2x equity), interpreted by business and sector.
  High debt is not automatically bad, low debt not automatically safe. Use only
  supported financing mechanisms, e.g.
  weaker operating cash generation -> reduced financial flexibility -> greater
  debt-service/refinancing pressure -> balance-sheet vulnerability. Do not assert
  this chain without evidence or force debt into risks.
- financial_currency: monetary interpretation metadata only, not currency exposure.
- last_fiscal_year_end and most_recent_quarter: supplied fiscal boundary and recency
  metadata only, never economic signals, drivers, or risks. Do not assume all metrics
  share a common reporting period.

## CAUSAL DRIVERS AND RISKS

Explain WHY each effect exists in THIS company: grounded premises and causal
chains, not positive/negative labels.

DRIVER -> COMPANY-SPECIFIC ECONOMIC ENGINE OR DEPENDENCY
-> TRANSMISSION MECHANISM -> ECONOMIC CONSEQUENCE.
A driver is a durable/recurring support for revenue, profitability, growth,
retention, pricing power, or competitive position visible in the business model.
Bad: "Strong network effects drive growth."
Better: "A larger two-sided payment network increases cardholder acceptance and
merchant utility, reinforcing transaction activity and recurring processing revenue."

STRUCTURAL PRESSURE -> COMPANY EXPOSURE -> TRANSMISSION MECHANISM
-> ECONOMIC CONSEQUENCE.
Each risk identifies a persistent vulnerability/dependency or competitive, industry,
regulatory, financial, or substitution pressure; the exposed company business area;
how it propagates; and the resulting economics.
Consequences may concern revenue, growth, margins, pricing, customers/activity,
costs, capital needs, cash resilience, balance-sheet pressure, or competitive position.
"Competition is a risk", "regulation may hurt growth", and "technology could affect
the company" are insufficient: name the exposed engine and causal mechanism.
Example, only with supported exposure: alternative payment rails bypass a card
network -> fewer processed transactions -> pressure on processing fees/pricing power.

### Materiality and market context

Assign materiality by connection to core economics, not severity-sounding language:
- high: directly affects a major revenue engine, core dependency, profitability
  structure, or durable competitive position.
- medium: meaningful but secondary, indirect, or subject to meaningful mitigants.
- low: limited connection to core economics or narrow potential impact.

market_context is STRUCTURAL: industry structure, durable demand, regulation,
recurring economic sensitivities, and competitive dynamics. No current price
action, sentiment, latest earnings, or recent-news commentary.

### Valuation boundary

No intrinsic/fair value, DCF, cheap/expensive conclusions, price targets, or
P/E, P/S, EV/EBITDA-based valuation analysis: explain economics, not stock worth.
No buy/sell/hold recommendations or guaranteed predictions.

## OUTPUT CONTRACT

Return ONLY valid JSON: no markdown, code fences, external commentary, or internal
reasoning. Copy asset, asset_type, and data_scope exactly:
"{asset}", "{asset_type}", "{data_scope}". Do not replace asset_type with "Company",
"Equity", or an industry. Materiality must be "low", "medium", or "high".

- summary: 4-6 concise sentences on economic identity and defining structural
  characteristics, not an investment conclusion.
- business_or_asset_profile: engines, customer/user relationships, supported
  monetization/economic role; integrate financials only to clarify the business model.
- market_context and peer_landscape: follow the contracts above.
- structural_drivers and structural_risks: 3-6 each if supported, never manufactured
  to meet a count. Each explanation must satisfy its causal contract.
- related_entities: supplied peer tickers/names materially participating in or
  illustrating this specific risk mechanism, supported by evidence or permitted stable
  knowledge. Not necessarily competitors; never list entities merely because they
  appear in peer_landscape. Use [] when none has a defensible connection.
  A stable-knowledge company mentioned in prose is not eligible unless it is also
  a supplied peer. Use supplied tickers (or supplied names when ticker is absent),
  not product aliases or combined "Name (TICKER)" labels.

## REQUIRED JSON SCHEMA

{{
  "asset": "{asset}",
  "asset_type": "{asset_type}",
  "summary": "string",
  "business_or_asset_profile": "string",
  "market_context": "string",
  "peer_landscape": [
    {{
      "ticker": "string or None",
      "name": "string",
      "peer_type": "direct_competitor | indirect_competitor | comparable | unclear",
      "relationship_area": "string",
      "why_relevant": "string explaining the relationship and its economic significance"
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
      "related_entities": ["string"]
    }}
  ],
  "data_scope": "{data_scope}"
}}

## FINAL INTERNAL CHECK

Verify specific economics, grounded causal drivers/risks, complete qualified peers,
contextual financial interpretation, no invented facts or news/thesis/valuation,
and exact schema/metadata. Output conclusions/explanations, not this internal review.
"""
