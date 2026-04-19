# Product Definition Document v1

## Product name

spider-ai — an asset market research copilot

## One-liner

An AI assistant for structured market research that helps users not just “ask about a ticker”, but build, update, and validate a bull/bear/risk thesis across stocks, currencies, commodities, and other assets using data, news, and evidence-backed analysis.

---

# 1. Product positioning

"spider" is not a trading bot, not a portfolio manager, and not just an LLM chat wrapper.

It is a research copilot that:

- collects data about an asset;
- builds a structured thesis;
- shows the bull / bear / risk perspectives;
- explains what has changed since the previous analysis;
- indicates how strongly the conclusions are supported by real data and evidence.

## How the product should be perceived

Not as:

> “a bot that says something about stocks”

But as:

> “a system for research-driven asset analysis with a transparent reasoning pipeline”

---

# 2. Core problem

A typical user who follows the market faces three main problems.

## 1. Information is scattered

The user has to check separately:

- price;
- news;
- fundamentals;
- context;
- macro factors;
- previous events.

## 2. Regular AI bots are too superficial

They often:

- provide generic text;
- do not show the thesis structure;
- do not separate bull and bear cases;
- do not show where the evidence is weak.

## 3. It is hard for the user to understand what actually changed

The problem is not only:

> “Tell me about NVDA”

But also:

- what changed over the last week;
- what new risks appeared;
- whether the bull thesis became stronger;
- whether the bear thesis became weaker.

---

# 3. Product goal

Build an assistant that helps users research assets faster and better, without replacing their own thinking, but enhancing it through:

- structure;
- evidence;
- comparison;
- change detection;
- confidence-aware outputs.

---

# 4. Target audience

## Primary target audience

### Self-directed retail investors / research-oriented market followers

These are people who:

- follow the market themselves;
- read financial news;
- are interested in stocks, ETFs, FX, gold, oil, and other assets;
- do not want a simple “buy/sell” signal, but a clear research summary.

This is the best audience for v1.

Why:

- it is broad enough;
- thesis-based analysis is genuinely useful for them;
- it does not require institutional-level accuracy;
- it works well for a product demo and portfolio project.

## Secondary audience

### Tech-savvy users / developers / finance-curious professionals

People who are interested in:

- AI-assisted research;
- structured market analysis;
- “what changed” mode;
- evidence-backed summaries.

## Potential v2/v3 audience

### Junior analysts / small research teams / finance content creators

But this is not the v1 audience.

At the beginning, the product should not pretend to be built for professional buy-side analysts.

---

# 5. Non-target audience

In v1, the product is not designed for:

- high-frequency traders;
- institutional portfolio managers;
- execution traders;
- people who need a broker or automated trading;
- users expecting personalized investment advice.

Important: the product is a research assistant, not an adviser.

---

# 6. User personas

## Persona 1 — Retail research user

A private investor who follows the market independently but does not want to spend too much time on scattered analysis.

### Their goal

Quickly understand:

- what matters right now for the asset;
- what the main drivers are;
- where the risks are;
- what has changed over the last few days.

## Persona 2 — Thesis builder

A user who is already looking at an asset and wants to build:

- a bull thesis;
- a bear thesis;
- a list of invalidation factors;
- what to monitor next.

## Persona 3 — Watchlist follower

A user who tracks several assets and wants to receive:

- structured updates;
- change summaries;
- prioritized insights.

---

# 7. Core value proposition

The product provides not just “an answer to a question”, but a research framework.

## Main value

The user receives:

- a concise structured overview;
- a bull / bear / risk view;
- evidence-backed conclusions;
- a change summary;
- confidence / weakness indicators.

## Key product differentiator

Not simply:

> “AI knows about the market”

But:

## 1. Thesis mode

The assistant builds a structured thesis for an asset.

## 2. What changed mode

The assistant shows what has changed since the previous analysis.

## 3. Evidence & confidence mode

The assistant shows:

- what the conclusion is based on;
- how fresh the data is;
- where the conclusion is weak;
- where evidence is missing.

---

# 8. Product principles

## 1. Structure over verbosity

A short, structured, useful analysis is better than a long AI-generated text.

## 2. Evidence over confidence

If there is not enough data, the product should clearly show it.

## 3. Research support, not advice

The product helps the user think, but does not make investment decisions for them.

## 4. Workflow over chat

The product should feel like a research workflow engine, not just a chat interface.

## 5. Extensible architecture

The functionality should naturally expand into:

- workflows;
- memory;
- RAG;
- agents;
- multi-agent roles.

---

# 9. Core user jobs

The user wants to:

## 1. Get an asset snapshot

> “What matters right now for this asset?”

## 2. Build a thesis

> “Give me the bull / bear / risk picture for this asset.”

## 3. Compare assets

> “Compare NVDA and AMD / gold and oil / EURUSD and DXY.”

## 4. Understand changes

> “What changed for this asset over the last 7 days / since the previous review?”

## 5. Check the quality of the output

> “How strongly is this actually supported by evidence?”

---

# 10. Core product modes

## Mode 1 — Snapshot

A quick overview of an asset:

- current context;
- key metrics;
- latest catalysts;
- short risk note.

## Mode 2 — Thesis

A full structured analysis:

- bull case;
- bear case;
- key risks;
- invalidation points;
- what to watch next.

## Mode 3 — Compare

Comparison of two assets:

- main drivers;
- risks;
- strengths;
- relative differences.

## Mode 4 — What changed

Changes since the previous analysis:

- new catalysts;
- new risks;
- changed sentiment;
- thesis shift.

## Mode 5 — Evidence view

Shows:

- sources used;
- evidence strength;
- freshness;
- confidence;
- missing data.

---

# 11. v1 scope

## What is included in v1

v1 should be narrow, but strong.

## v1 features

### 1. Ticker / asset analysis

Support at least:

- equities;
- FX;
- commodities.

### 2. Snapshot mode

A concise structured overview.

### 3. Thesis mode

Bull / Bear / Risk analysis.

### 4. What changed mode

At least in a basic version:

- changes over the last 7 days;
- changes since the previous saved analysis.

### 5. Evidence-backed output

The answer should include:

- structured sections;
- source references / citations;
- confidence note;
- missing evidence note.

### 6. Saved analysis state

Store the previous analysis snapshot so it can be compared later.

## Main focus of v1

Not breadth, but strength in three areas:

- thesis quality;
- change detection;
- evidence awareness.

---

# 12. v1 non-goals

In v1, there is no need to build:

- automated trading;
- portfolio optimization;
- broker integration;
- personalized buy/sell recommendations;
- a full multi-agent theater;
- 10 data sources at once;
- a complex UI.

---

# 13. v2 scope

## What to add after a strong v1

## possible v2 features

- watchlist mode;
- scheduled summaries;
- improved historical comparison;
- richer RAG corpus;
- compare mode;
- better evidence scoring;
- more detailed macro context;
- first workflow orchestration layer.

---

# 14. possible v3 scope

## What can naturally grow later

## v3 features

- multi-step research workflows;
- bounded agent orchestration;
- bull analyst / bear analyst / risk analyst roles;
- richer user memory;
- portfolio/watchlist intelligence;
- multi-agent debate mode;
- framework comparison layer.

Possible tech stack growth:

- LangGraph;
- OpenAI Agents SDK;
- PydanticAI;
- agentic RAG;
- advanced observability and evaluation.

---

# 15. Core differentiators

These are the product “special features” that distinguish the project from a regular wrapper.

## Differentiator 1 — Thesis-first design

The product builds a bull / bear / risk thesis instead of just generating text.

## Differentiator 2 — Change intelligence

The product answers an important question:

> “What changed?”

This is stronger than regular Q&A.

## Differentiator 3 — Evidence-aware outputs

The answer includes:

- confidence;
- evidence strength;
- freshness;
- missing-data awareness.

## Differentiator 4 — Extensible to workflows and agents

The product is designed from the beginning to naturally grow into:

- workflows;
- bounded agents;
- multi-role analysis.

---

# 16. User-facing promise

The product does not promise:

> “I will tell you what to buy.”

Instead, it promises:

> “I will help you understand an asset faster and in a more structured way, see the strengths and weaknesses of the thesis, and understand what actually changed.”

---

# 17. Success metrics for v1

## Product success signals

- the user can get a useful structured thesis from one request;
- the “what changed” mode produces meaningful differences;
- answers look grounded, not generic;
- the product can indicate uncertainty;
- outputs are consistently structured.

## Engineering success signals

- stable structured outputs;
- reproducible workflows;
- clear tool architecture;
- retrieval + citations;
- evaluation coverage;
- good README/demo.

---

# 18. Final product verdict

## Best focus for the project

AI Market Research Copilot with three main pillars:

## 1. Thesis mode

Bull / Bear / Risk analysis

## 2. What changed mode

Change detection since the previous analysis / over the last 7 days

## 3. Evidence & confidence mode

Groundedness, freshness, confidence, missing evidence