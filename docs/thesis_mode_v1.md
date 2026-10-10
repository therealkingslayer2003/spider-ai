# Thesis Mode v1 skeleton

`POST /api/v1/asset/thesis` accepts `AssetThesisRequest` and declares
`StockAssetThesis` as its eventual response. The current implementation always
returns **501** for valid requests: `Asset thesis research is not implemented yet.`
Invalid requests return 422. Future execution failures use the existing
`ServiceError` / 502 boundary, separately from research uncertainty.

```json
{"asset": " nvda ", "asset_type": "stock"}
```

The asset is stripped and uppercased, with Snapshot's 1–32 character limit.
Only `stock` is accepted. Company eligibility cannot be verified until research
execution exists. `snapshot_context` optionally accepts a same-asset
`StockAssetSnapshot`; it is background, never a prerequisite or primary evidence.
It does not alter the response contract. The request has no DCF assumption
field: the workflow will derive forecast assumptions from prepared financials
under versioned rules and select policy parameters from versioned configuration.
This skeleton supplies no financial defaults or configuration.

## Mapping to Snapshot

| Snapshot | Thesis |
| --- | --- |
| `app/domain/schemas/asset_snapshot.py` / `StockAssetSnapshot` | `app/domain/schemas/asset_thesis.py` / `StockAssetThesis` |
| `AssetSnapshotRequest` | `AssetThesisRequest` |
| `app/api/v1/endpoints/asset_snapshot.py` / module `router` | `app/api/v1/endpoints/asset_thesis.py` / module `router` |
| `AssetSnapshotService.get_snapshot` | `AssetThesisService.get_thesis` |
| `AssetSnapshotGraphRunner` | `AssetThesisGraphRunner` |
| `AssetSnapshotRouterGraph` | `AssetThesisGraph` shell |
| `get_asset_snapshot_service` in `app/api/dependencies.py` | `get_asset_thesis_service` in the same composition root |
| `/asset/snapshot` in the v1 router | `/asset/thesis` in the same route family |

The asynchronous service now delegates to an injected `AssetThesisGraphRunner`,
matching Snapshot's service/runner dependency chain. `AssetThesisGraph` now
compiles the parent topology. Its child graph boundaries and remaining analysis
nodes still raise `AssetThesisNotImplementedError`, which only the endpoint
translates to HTTP.
Importing/registering the endpoint and resolving its dependency do not construct
external clients. Existing application startup still initializes the shared
local SQLite database. An SEC EDGAR client and reusable filing storage adapters
(raw HTML, SQL metadata, and Chroma vectors) exist but are not wired into Thesis
execution. Filing parsing, embeddings, ingestion coordination, retrieval, and
Thesis artifact persistence remain future work.

## Response contract

The six required sections are `short_thesis_overview`, `asset_overview`,
`valuation`, `current_catalysts`, `thesis_risks_and_invalidation`, and
`sources_and_evidence`. The envelope carries stock identity, optional SEC CIK,
a timezone-aware research timestamp, and coverage of each corpus component.
The 90-day filing window is relative to that research timestamp. Coverage records
actual completeness and missing-data explanations, not execution progress.

Claims refer to unique, stable evidence IDs; validation rejects duplicate IDs and
dangling references throughout the response. Filing evidence retains accession,
form, filing date, document/exhibit URL and passage/chunk locator. Company Facts
evidence retains accession, filing date, taxonomy, concept, unit, period and value.
Price evidence identifies the provider and quote timestamp. Each record has a
retrieval timestamp. Source identity/locator determines the eventual stable ID;
ID generation and retrieval are not implemented here. Inference/uncertainty can
have no citation; factual claims should cite the corpus.

Valuation separates dated, sourced historical inputs from explicit assumptions
and Python-calculated outputs. Rates and ratios are decimals (`0.10` is 10%);
amounts are unscaled USD, share counts are shares, and per-share values are USD
per share. Positive capex and incremental working capital consume cash. Forecast
assumptions are ordered years 1–5, followed by terminal growth below the explicit
annual discount rate (WACC). Assumption provenance records the policy version
that produced them. WACC and terminal growth require configured values; an LLM
does not invent assumptions or calculate the DCF.

Every missing numeric value must be `null` with a nonblank `unavailable_reason`;
zero is an actual value. The same applies to unavailable forecasts, terminal
value, enterprise/equity value, per-share value, upside and sensitivity cells.
Missing assumption sets also require an explanation. Historical inputs carry
their own periods; limitations explain incomplete history or omitted sensitivity.
Unknown event dates are nullable, catalysts may be empty, and risk reassessment
signals need no invented numeric thresholds. `uncertain` is a completed research
judgment, including material unresolved conflicts with DCF assumptions; it must
never stand in for unimplemented execution or a failed run.

## Future scope and orchestration

V1 targets US nonfinancial companies reporting under US GAAP in USD, with
positive, reasonably stable cash flows and simple capital structures. Banks,
insurers, REITs, loss-making businesses and complex turnarounds are excluded.

The corpus is the latest SEC 10-K, the latest 10-Q if filed after that 10-K,
relevant 8-Ks and available HTML exhibits from the last 90 days, SEC Company Facts
for three complete financial years plus required balance-sheet inputs, and one
market-price source. Catalysts come only from disclosed events in that corpus.
There is no separate news provider, peer universe, analyst estimates, macro feed,
or universal IR/PDF crawler.

1. Prepare and index the shared research data.
2. Independently produce Asset Overview, Catalysts, and deterministic two-stage
   FCFF DCF results (five forecast years plus terminal value).
3. Produce combined Thesis Risks & Invalidation using those outputs and targeted
   retrieval.
4. Generate Short Thesis Overview, assemble sources, and validate the response.

Python will calculate valuation/sensitivity; LLMs will explain evidence and
uncertainties. There is no separate Risk Discovery stage or mandatory
reconciliation/recalculation loop. Ingestion, retrieval, embeddings, prompts,
DCF calculation, Thesis artifact persistence, checkpointing and an executable
LangGraph workflow are intentionally unimplemented. Filing-storage migration
`002` exists independently of those workflow stages.
