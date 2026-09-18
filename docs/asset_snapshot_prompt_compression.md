# Asset Snapshot Static Prompt Compression

## Current Revision

The 2026-09-16 audit and pilot below are historical. The subsequent
[peer-landscape change](peer_landscape.md) intentionally changes both the output
schema and stable-knowledge policy. The production prompt is
[`feature_snapshot_prompt.py`](../app/llm/prompts/feature_snapshot_prompt.py).
The verbose eval reference in
[`original_feature_prompt.py`](../evals/asset_snapshot/original_feature_prompt.py)
is now rebased to that same new contract, not an untouched historical baseline.
Production never imports it. With the merged `why_relevant` and clarified risk
reference boundary, feature sizes are 19,823 verbose and 14,102 compact characters
(28.9% reduction); the previous 40.1% figure is not the current
contract's measurement. No model-quality conclusion follows from these sizes.

The exact original competitor-centric prompt remains recoverable from Git:
`git show 906aef9f1e274e33682d79b54fea56a7ab3ce42b:app/llm/prompts/feature_snapshot_prompt.py`.
Current A/B runs hold the new schema, knowledge policy and five-sentence peer
projection constant. The following audit describes the earlier distillation only;
its fallback-only knowledge rule has deliberately been superseded.

## Historical Size and Scope

| Measurement | Original | Compressed | Reduction |
|---|---:|---:|---:|
| Static feature template, characters | 18,708 | 11,213 | 40.1% |
| AMZN pilot total rendered prompt, characters | 20,783 | 13,282 | 36.1% |
| AMZN pilot dynamic context, characters | 1,205 | 1,205 | 0% |

Template counts include placeholders and whitespace. Rendered totals also include
the unchanged system prompt and dynamic provider context. No tokenizer dependency
was added; these are character measurements, not token estimates. Dynamic-context
reduction from the separate peer-projection change is not credited here.

The only production wiring addition is a `feature_prompt` constructor argument on
[`StockSnapshotPromptBuilder`](../app/llm/prompts/feature_snapshot_prompt_builder.py),
defaulting to the compressed prompt. Evals inject the original through the same
builder. Providers, enrichment, projection, cache, graph, model selection,
`num_ctx`, persistence, and API behavior are not changed by this compression.
The output-schema example is byte-identical; the Pydantic response schema is
unchanged. There is no runtime compressor or extra production inference call.

## Historical Semantic Coverage Audit

This table audits instructions, not proof that an LLM will obey them. Shape and
types are validated through the existing structured-output/Pydantic path. Semantic
grounding, causal quality, completeness, and materiality still need evaluation.

| Requirement | Original location | Compressed location | Preserved |
|---|---|---|---|
| A. Persistent company economics, not thesis/news/trading/prediction | Product Purpose; Output Rules | Task and Scope; Valuation Boundary | Yes |
| B. Business model -> engines/dependencies -> financial characterization -> competition -> causal drivers/risks | Research Mindset | Research Method | Yes |
| C. Profile > peers > fundamentals > restricted stable fallback; provider evidence over memory | Evidence Hierarchy | Grounding and Missing Data | Yes |
| D. Partial evidence is usable; absent metrics imply no characteristic; absent peers cannot be invented | Missing Data Rules; domain sections | Grounding and Missing Data; Provider-Reported Peers | Yes |
| D. Fallback requires entirely absent profile and explicit fallback scope; no precise unsupplied figures/recent or uncertain claims | Evidence Hierarchy; Field Requirements | Grounding and Missing Data | Yes |
| E. Name identifies; sector is insufficient for firm risk; industry refines economics without making firms identical | Company Profile: Name, Sector, Industry | Company Profile | Yes |
| E. Exchange/currency are listing context, not business conclusions/revenue exposure; country needs a defensible connection | Company Profile: Exchange, Currency, Country | Company Profile | Yes |
| E. Summary becomes an economic model of products, customers, monetization, activities, dependencies and advantages, not a paraphrase | Company Profile: Business Summary | Company Profile; Research Method | Yes |
| F. Acknowledge every distinct identifiable reported peer; retain failed enrichment and supplied identities; ticker-only does not license invented facts | Competitive Context; Field Requirements | Provider-Reported Peers | Yes |
| F. Peer membership is not direct competition; use supplied target/peer facts to distinguish direct, indirect and broader comparability | Competitive Context | Provider-Reported Peers | Yes |
| F. Relationship fields are analytical outputs; explain supported overlap/impact or provider attribution with accurate limits | Competitive Context: field subsections | Provider-Reported Peers: field contracts and qualification example | Yes |
| F. No invented peer facts, market share, dominance or impacts; no bare placeholders or blanket disclaimers when overlap is supported | Competitive Context; Field Requirements | Provider-Reported Peers | Yes |
| F. Missing enrichment affects explanation, not eligibility; a different supplied business is not a missing profile; empty output only with no identifiable peers | Competitive Context; Field Requirements | Provider-Reported Peers | Yes |
| G. Metrics support business-model interpretation, not automatic positive/negative, investment, driver or risk labels | Financial Fundamentals; Field Requirements | Financial Fundamentals invariant | Yes |
| G. Revenue describes scale; growth describes expansion/maturity/dependence; margin informs profitability, scalability, pricing/cost sensitivity and operating leverage | Financial Fundamentals: revenue, growth, margin | Financial Fundamentals: corresponding metric bullets | Yes |
| G. Debt-to-equity is a multiple; financing dependence is business/sector-aware, not high=bad or low=safe; do not force leverage into risks | Financial Fundamentals: debt-to-equity ratio | Financial Fundamentals: ratio bullet and causal example | Yes |
| G. Financial currency and fiscal dates are interpretation metadata, not economic signals; no fabricated common period | Financial Fundamentals: metadata | Financial Fundamentals: metadata bullets | Yes |
| H. Durable driver -> company engine/dependency -> transmission -> consequence, not a positive label | Structural Driver Reasoning; Quality Check; Field Requirements | Causal Drivers and Risks | Yes |
| I. Pressure -> exposed company business -> propagation -> economic consequence; generic competition/regulation/technology claims are insufficient | Structural Risk Reasoning; Quality Check; Field Requirements | Causal Drivers and Risks | Yes |
| J. High=core economics; medium=secondary/indirect/mitigated; low=narrow; alarming wording does not set materiality | Materiality | Materiality and Market Context | Yes |
| K. Structural industry/demand/regulation/sensitivities/competition, not price action, sentiment, latest earnings or news | Market Context; Product Purpose | Materiality and Market Context | Yes |
| L. No DCF, fair value, cheap/expensive, targets, P/E, P/S, EV/EBITDA valuation, buy/sell/hold or guaranteed predictions | Valuation Boundary; Purpose; Market Context; Output Rules | Valuation Boundary | Yes |
| M. Exact asset/type/scope, enums and root/entry fields; JSON only, no Markdown/commentary/internal reasoning | Output Rules; Required JSON Schema | Output Contract; unchanged Required JSON Schema | Yes |
| M. Summary 4-6 sentences; supported 3-6 drivers/risks without manufacturing a quota; risk-related peers only when relevant and supported | Field Requirements | Output Contract | Yes |
| Internal review of specificity, grounding, peers, financial context, scope and schema | Quality Check Before Output | Final Internal Check | Yes |

Repeated grounding/missing-data prohibitions are consolidated into one invariant.
Repeated causal requirements in the quality checklist and field requirements now
refer to the driver/risk contracts. Financial metrics share one interpretation
rule; their distinct meanings remain. Valuation restrictions have one boundary.

Retained behavioral anchors include the technology-sector stereotype counterexample,
payment-network driver chain, alternative-payment-rails risk chain, peer-without-
profile qualification, pricing-pressure mechanism, and financing-pressure chain.
Nuanced peer eligibility versus overlap, restricted fallback, and per-metric
semantics deliberately remain relatively detailed. Further compression of these
rules would risk changing behavior rather than removing repetition.

## Controlled A/B Evaluation

See the [eval guide](../evals/README.md#original-vs-compressed-prompt-evaluation)
for commands and the class flow. Both variants use identical frozen cases, target
and peer formatting, production tools/graphs/schema, model client and settings.
Per-case context hashes detect uncontrolled evidence changes. Generation order
alternates by case; pairwise judgments are blinded to variant names and made in
both candidate orders. Only consistent mapped decisions count as a win or tie.

The report includes the original/compressed template hashes, system/schema hashes,
selected-fixture hash, settings, static/dynamic sizes, generation success and
latency, existing deterministic/semantic metrics, both complete outputs, and
validated literal judge evidence. That compression-only task did not rewrite
expectations or dataset facts. The later peer-landscape contract revision rebases
both templates and explicitly migrates eval expectations; do not compare its scores
with the old-contract pilot as a pure compression experiment.

## Local Pilot: 2026-09-16

Executed one approved frozen case, `amzn_peer_profiles_001`, with compact peer
context, `qwen3:14b` at temperature `0.2`, and `deepseek-r1:14b` at temperature `0`.
The pilot used the then-current two-sentence/420-character peer projection;
subsequent runs use the current five-sentence/1,200-character projection for both
variants. The command used `--compare-prompts --pairwise-only`: two generation calls and
two pairwise judge calls; individual semantic graders were not run. Market-data
providers were frozen and LangSmith tracing was disabled.

| Result | Original | Compressed |
|---|---:|---:|
| Generation success | 1/1 | 1/1 |
| Deterministic checks passed | 6/8 | 8/8 |
| Generation seconds, including tool orchestration | 70.459 | 72.009 |

The original failed the existing competitor identity/coverage checks. Pairwise
judgment preferred original in the first order and returned tie in the reverse
order: `order_disagreement`, no aggregate winner. This does not prove semantic
equivalence or improved quality/latency; deterministic passes are not semantic
fact-checks, and one case with one sample per variant is insufficient.

Local artifacts (ignored by Git):
`evals/reports/prompt_compression_pilot/stock_snapshot_v1_prompt_ab_20260916T204804782321Z.{json,md}`.
`num_ctx` remains the unpinned model/server default, and no sampling seed is set.
Token usage and actual context truncation were not measured. Repeat across the
approved frozen set with individual semantic metrics, fixed model/server settings,
and multiple samples before making a quality/regression claim.
