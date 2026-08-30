ASSET_SNAPSHOT_PROMPT = """
Your task is to generate a structured Stock Asset Snapshot.

## PRODUCT PURPOSE

Asset Snapshot is a structural economic analysis of a company.

Its purpose is to help a market researcher or investor understand:

- what the company economically is;
- how it makes money;
- which parts of its business are economically important;
- what durable characteristics support its business;
- what structural dependencies can weaken it;
- which competitors and industry forces materially affect its economics.

This is NOT:
- a current investment thesis;
- a valuation analysis;
- a news analysis;
- a price forecast;
- a trading recommendation.

The analysis should focus on relatively persistent business characteristics rather
than temporary events.

Asset:
{asset}

Asset type:
{asset_type}

Required data_scope:
{data_scope}


## RESEARCH MINDSET

Act as a careful professional equity researcher.

Do not merely summarize the supplied provider data.

Use the data to build a causal economic understanding of the company.

Internally reason in this order:

1. Understand the business model.
2. Identify the company's major economic engines and dependencies.
3. Use financial fundamentals to characterize the economics of those engines.
4. Use peer information to understand relevant competitive pressure.
5. Derive structural drivers and structural risks from that combined understanding.
6. For every important conclusion, ensure that it is supported by supplied evidence
   or, only when explicitly allowed below, stable model knowledge.

A good Asset Snapshot should answer:

"What structurally makes this business economically strong, weak, scalable,
dependent, exposed, or difficult to compete with, and through what mechanism?"


## EVIDENCE HIERARCHY

Use information in this priority order:

1. Supplied company profile
2. Supplied competitive context
3. Supplied financial fundamentals
4. Stable model knowledge ONLY as a fallback when provider company-profile
   information is entirely unavailable

Provider evidence takes precedence over model knowledge.

### Missing data rules

If an individual field is missing:
- do NOT guess its value;
- do NOT infer a company characteristic that requires that missing value;
- continue using the evidence that is available.

Examples:
- no operating margin -> do not claim high or low profitability from financial data;
- no debt-to-equity ratio -> do not infer strong or weak leverage;
- no peers -> do not invent a competitive landscape from weak assumptions;
- no revenue growth -> do not classify the company as fast-growing or declining
  based on that metric.

Missing data is absence of evidence, not negative evidence.

If the company profile itself is completely unavailable and
data_scope is "model_static_knowledge_fallback":
- use only high-confidence, stable, general knowledge about the company;
- avoid precise financial figures unless supplied;
- avoid recent developments;
- avoid obscure competitors or uncertain claims;
- keep conclusions conservative.


## HOW TO USE COMPANY PROFILE DATA

The COMPANY PROFILE is the primary source for understanding the business.

### Name
Use only for company identification.

### Sector
Use as broad economic context.
Do not derive company-specific risks merely from generic sector stereotypes.

BAD:
"Technology companies face innovation risk."

GOOD:
Use sector information together with the company's actual business model to
identify which technological change could affect a specific revenue engine,
product category, cost structure, or competitive advantage.

### Industry
Use to understand the company's more specific economic environment, typical
competitive structure, and durable industry pressures.

Do not assume every company in the same industry has identical economics.

### Exchange
Use only as identification/listing context when relevant.
Do not derive structural business conclusions from the exchange alone.

### Currency
This is trading/listing context.
Do not treat it as evidence of the company's revenue exposure or financial
reporting currency.

### Country
Use only when it creates a defensible structural connection to the business,
for example:
- regulatory exposure;
- geographic concentration;
- production dependency;
- jurisdiction-specific constraints.

Do not invent geopolitical or regulatory risks merely because a country is listed.

### Business summary
This is the most important profile field.

Use it to determine:
- what products/services the company provides;
- who its customers/users/merchants are;
- how value is created;
- how the company likely monetizes its activity when explicitly supported;
- which business activities are central;
- which dependencies or competitive advantages are visible.

Do not simply paraphrase the summary.
Translate it into an economic model of the business.


## HOW TO USE COMPETITIVE CONTEXT

Peer data is supporting evidence for understanding competition.

For every supplied peer consider:

### competition_area
Identify the specific market, product, customer base, distribution channel,
technology, or economic activity in which competition occurs.

### why_competitor
Use this to determine whether the peer is economically relevant rather than merely
similar by sector classification.

### why_it_matters
Use this to identify the transmission mechanism through which the competitor could
affect the company.

Possible mechanisms include:
- pricing pressure;
- customer switching;
- lower market share;
- reduced transaction volume;
- weaker distribution;
- higher acquisition costs;
- faster required R&D investment;
- weaker differentiation;
- substitution of the company's product or infrastructure.

Do NOT assume that every peer is a direct competitor.

When supplied peer context is absent, do not invent obscure competitors.

competitive_landscape should primarily reflect supplied peer evidence.


## HOW TO USE FINANCIAL FUNDAMENTALS

Financial fundamentals are quantitative supporting evidence.

They do NOT independently define whether the company is good, bad, bullish,
bearish, cheap, or expensive.

Always interpret them together with the business model.

### revenue

Use revenue primarily to understand business scale.

Revenue alone does NOT indicate:
- quality;
- profitability;
- growth;
- valuation attractiveness.

Use it as scale context for the company described by the profile.


### revenue_growth

Use revenue growth to characterize the observed growth profile when available.

It may help identify:
- expanding business activity;
- maturity;
- sensitivity of the business to sustained growth.

Do NOT assume:
"high growth = bullish"
or
"low growth = structurally weak".

Answer instead:
"What part of this company's economic model makes sustained growth important,
and what could structurally support or constrain it?"


### operating_margin

Use operating margin as evidence about operating profitability and the economic
structure of the business.

Together with the business model it may help reason about:
- scalability;
- cost sensitivity;
- pricing economics;
- operating leverage;
- resilience of operating profits to structural pressure.

Do NOT automatically interpret a high margin as a moat or bullish signal.

A structural risk should explain HOW a pressure could affect the economics
behind the margin.

Example reasoning pattern:

competitive pricing pressure
-> affects monetization of a core product
-> lower revenue per customer or transaction
-> operating profitability may weaken


### debt_to_equity ratio

Use debt-to-equity only as supporting evidence about capital structure and
financing dependence.

Its meaning is sector- and business-model-dependent.

Do NOT assume:
"high debt-to-equity = bad company"
or
"low debt-to-equity = safe company".

When relevant, connect leverage to an actual mechanism such as:

weaker operating cash generation
-> less financial flexibility
-> greater difficulty servicing/refinancing obligations
-> increased balance-sheet vulnerability

If such a mechanism cannot be justified from the supplied context, do not force
debt into the structural risks.


### financial_currency

Use this only to correctly interpret monetary financial values.

Do not derive currency exposure from financial_currency alone.


### last_fiscal_year_end

Use this as temporal metadata indicating the latest supplied fiscal-year boundary.

Do not treat it as an economic signal.


### most_recent_quarter

Use this as temporal metadata about the recency of supplied company financial data.

Do not treat the date itself as a driver or risk.


## STRUCTURAL DRIVER REASONING

A structural driver is a durable characteristic or recurring economic force that
can support the company's ability to generate revenue, maintain profitability,
grow, retain customers, preserve pricing power, or sustain competitive position.

Do not merely name positive characteristics.

Every structural driver should explain a causal mechanism:

DRIVER
-> COMPANY-SPECIFIC ECONOMIC ENGINE OR DEPENDENCY
-> TRANSMISSION MECHANISM
-> ECONOMIC CONSEQUENCE

Example:

BAD:
"Strong network effects are a growth driver."

BETTER:
"A larger two-sided payment network increases acceptance for cardholders and
utility for merchants, reinforcing transaction activity on the network and
supporting recurring processing revenue."

Prefer drivers that are visible from the supplied business model and evidence.


## STRUCTURAL RISK REASONING

A structural risk is a persistent vulnerability, dependency, competitive force,
industry constraint, regulatory exposure, financial characteristic, or substitution
threat that can materially weaken the economics of the business.

Do NOT stop after identifying the risk category.

Every structural risk MUST explain:

1. What structural pressure or dependency exists.
2. Which specific part of THIS company's business is exposed.
3. How the pressure propagates through that business area.
4. Which economic consequence can result.

Use this pattern:

STRUCTURAL PRESSURE
-> COMPANY EXPOSURE
-> TRANSMISSION MECHANISM
-> ECONOMIC CONSEQUENCE

Economic consequences may include:
- revenue pressure;
- slower growth;
- margin pressure;
- weaker pricing power;
- customer loss;
- lower transaction/activity volume;
- higher operating costs;
- higher capital requirements;
- weaker cash-generation resilience;
- balance-sheet pressure;
- erosion of competitive position.

Avoid generic endings such as:
- "this could negatively affect the company";
- "this could hurt growth";
- "competition is a risk";
- "regulation could impact operations".

The explanation must show WHY.


## MATERIALITY

Assign materiality based on how strongly the factor is connected to the company's
core economic engine, not on how dramatic the risk or driver sounds.

High:
- directly affects a major revenue engine, core dependency, profitability structure,
  or durable competitive position.

Medium:
- economically relevant but affects a secondary business area, has indirect impact,
  or has meaningful mitigants.

Low:
- limited connection to core economics or relatively narrow potential impact.

Do not assign "high" simply because a risk sounds severe.


## MARKET CONTEXT

market_context means STRUCTURAL market context, not current market commentary.

It may include:
- industry structure;
- durable demand characteristics;
- regulatory structure;
- recurring economic sensitivities;
- relevant competitive dynamics.

It must NOT include unsupported claims about:
- current stock-price movements;
- today's market sentiment;
- latest earnings;
- recent news;
- current valuation multiples.


## VALUATION BOUNDARY

Do NOT:
- estimate intrinsic value;
- perform DCF;
- calculate fair value;
- determine whether the stock is cheap or expensive;
- introduce P/E, P/S, EV/EBITDA or price targets unless another feature explicitly
  requests them.

Asset Snapshot describes the economics of the business.
It does not decide what that business should currently be worth.


## QUALITY CHECK BEFORE OUTPUT

Before returning the JSON, verify internally:

- Did I identify the actual business model rather than repeat sector labels?
- Are drivers tied to specific economic engines?
- Does every structural risk contain a real transmission mechanism?
- Are financial metrics interpreted in context rather than as automatic signals?
- Are competitor claims supported by supplied peer evidence?
- Did I avoid filling missing provider fields with assumptions?
- Did I avoid temporary news/catalyst/thesis content?
- Did I avoid valuation conclusions?
- Is every material claim grounded in supplied evidence or explicitly allowed
  stable fallback knowledge?


## OUTPUT RULES

- Return ONLY valid JSON.
- Do not include markdown.
- Do not include code fences.
- Do not expose internal reasoning.
- Do not include explanations outside the JSON.
- data_scope must be exactly "{data_scope}".
- Every structural driver and structural risk must use materiality:
  "low", "medium", or "high".


## REQUIRED JSON SCHEMA

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


## FIELD REQUIREMENTS

"asset"
- Must exactly represent the requested asset.

"asset_type"
- Must match the supplied asset type.

"summary"
- 4-6 concise sentences.
- Explain what the company economically is and the main structural characteristics
  that define it.
- Do not turn the summary into an investment conclusion.

"business_or_asset_profile"
- Explain how the company operates economically.
- Describe major business engines, customer/user relationships, monetization or
  economic role when supported.
- Integrate relevant financial characteristics only when they improve understanding
  of the business model.

"market_context"
- Describe only durable industry, regulatory, demand, and competitive context.
- No current-news or valuation commentary.

"competitive_landscape"
- Prefer supplied peers.
- Explain the actual area and mechanism of competition.
- Do not assume every comparable company is a direct competitor.

"structural_drivers"
- Provide 3-6 when evidence reasonably supports that many.
- Each must contain a company-specific causal mechanism.
- Do not manufacture additional drivers merely to reach a count.

"structural_risks"
- Provide 3-6 when evidence reasonably supports that many.
- Each must identify the exposed business area and causal economic mechanism.
- related_competitors should contain only competitors actually relevant to that
  risk and supported by context.
- Do not manufacture additional risks merely to reach a count.

"data_scope"
- Must be exactly "{data_scope}".
"""