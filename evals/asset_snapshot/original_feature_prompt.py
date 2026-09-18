# Eval-only verbose reference rebased to the peer-landscape v3 contract.
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


## HOW TO USE PEER CONTEXT

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
Avoid vague risks that do not identify the exposed business area and transmission
mechanism.
Every structural risk must explain the company exposure or dependency and how the
pressure reaches an economic consequence.


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
Asset Snapshot must not use P/E, P/S, EV/EBITDA, DCF, or price targets to reach a
valuation conclusion.
Likewise, high debt is not automatically bad and low debt is not automatically safe.


## QUALITY CHECK BEFORE OUTPUT

Before returning the JSON, verify internally:

- Did I identify the actual business model rather than repeat sector labels?
- Are drivers tied to specific economic engines?
- Does every structural risk contain a real transmission mechanism?
- Are financial metrics interpreted in context rather than as automatic signals?
- Are peer relationship claims supported by provider evidence or permitted stable
  knowledge, without inventing current, numerical or uncertain facts?
- Did I avoid filling missing provider fields with assumptions?
- Did I avoid temporary news/catalyst/thesis content?
- Did I avoid valuation conclusions?
- Is every material claim grounded in supplied evidence or permitted secondary
  stable knowledge?


# OUTPUT RULES

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


## FIELD REQUIREMENTS

"asset"
- Must be exactly "{asset}".

"asset_type"
- Must be exactly "{asset_type}". Do not replace it with a descriptive category
  such as "Company", "Equity", or an industry name.

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

"peer_landscape"
- Acknowledge every distinct identifiable provider-reported peer.
- Classify peer_type and explain supported competition or broader/unclear relevance.
- Missing enrichment is not a reason to drop a peer or invent an impact.
- Do not assume every comparable company is a direct competitor.

"structural_drivers"
- Provide 3-6 when evidence reasonably supports that many.
- Each must contain a company-specific causal mechanism.
- Do not manufacture additional drivers merely to reach a count.

"structural_risks"
- Provide 3-6 when evidence reasonably supports that many.
- Each must identify the exposed business area and causal economic mechanism.
- related_entities must reference supplied peer identities materially connected to
  this specific causal risk mechanism by evidence or permitted stable knowledge.
  They need not be competitors; peer membership alone does not justify a reference.
  A stable-knowledge company mentioned in prose is not eligible unless it is also
  a supplied peer. Use supplied tickers (or supplied names when ticker is absent),
  not product aliases or combined "Name (TICKER)" labels.
- Do not manufacture additional risks merely to reach a count.

"data_scope"
- Must be exactly "{data_scope}".
"""
