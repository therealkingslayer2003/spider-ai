# Stock Snapshot v1 Manual Review

All 27 cases are AI-generated, synthetic benchmark seeds with
`pending_manual_review` status. This table is both the pre-generation coverage
design and the owner review guide.

## Normal business-model cases

| Case | Entity / archetype | Provider availability | Key expectations | Tested mistake | Review flags |
|---|---|---|---|---|---|
| `ma_payment_network_001` | Mastercard / payment network | profile + peers | transaction-fee network, volume and cross-border exposure | describing the company as a deposit-taking lender | `REVIEW_REAL_COMPANY_FACTS` |
| `jpm_bank_001` | JPMorgan / diversified bank | profile only | lending, deposits, credit and capital economics | confusing bank economics with payment-network fees | `REVIEW_REAL_COMPANY_FACTS` |
| `meta_ads_platform_001` | Meta / advertising platform | profile + peers | attention and advertising monetization | subscription-first business model | `REVIEW_REAL_COMPANY_FACTS` |
| `tsm_foundry_001` | TSMC / semiconductor foundry | profile only | contract manufacturing, utilization and capex | treating it as a fabless chip designer | `REVIEW_REAL_COMPANY_FACTS` |
| `sap_enterprise_software_001` | SAP / non-US enterprise software | profile only | enterprise applications and recurring support/cloud economics | consumer-advertising model | `REVIEW_REAL_COMPANY_FACTS` |
| `novapay_network_001` | NovaPay / fictional payment network | profile + peers + financials | network effects, payment volume, competing rails | lending or deposit claims | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `ledger_bank_001` | Ledger Bank / fictional regional bank | profile + peers + financials | spread income, deposits, credit losses, capital | payment-network economics | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `admesh_platform_001` | AdMesh / fictional ad platform | profile + peers + financials | user attention, ad demand, privacy and distribution | SaaS subscription model | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `cloudx_saas_001` | CloudX / fictional enterprise SaaS | profile + peers + financials | recurring subscriptions, retention, switching costs | advertising concentration | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `chipforge_fabless_001` | ChipForge / fictional fabless semiconductor | profile + peers + financials | design leadership and external foundry dependence | owning fabrication plants | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `silicon_foundry_001` | Silicon Foundry / fictional foundry | profile + peers + financials | utilization, process execution and capital intensity | fabless economics | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `brandco_consumer_001` | BrandCo / fictional consumer brand | profile + peers + financials | brand, pricing, distribution and input costs | platform network effects | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `valuecart_retail_001` | ValueCart / fictional retailer | profile + peers + financials | low margins, inventory, logistics and scale | high-margin software economics | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `orbit_industrial_001` | Orbit Industrial / fictional manufacturer | profile + peers + financials | backlog, cycles, execution and capital intensity | recurring SaaS economics | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `northsea_energy_001` | NorthSea Energy / fictional producer | profile + peers + financials | commodity exposure, reserves, costs and regulation | evaluating the commodity instead of the company | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `euroauto_industrial_001` | EuroAuto Systems / fictional non-US automation firm | profile + peers + financials | automation demand, order cycles and export exposure | US-only market assumptions | `SYNTHETIC_FINANCIAL_FIXTURE` |

## Missing-data and fallback cases

| Case | Entity / archetype | Provider availability | Key expectations | Tested mistake | Review flags |
|---|---|---|---|---|---|
| `profile_only_saas_001` | CoreDesk / fictional SaaS | profile only | valid grounded output without peers or metrics | treating absent metrics as weak quality | none |
| `fmp_profile_fallback_001` | RailPay / fictional processor | FMP profile + peers | `fmp_profile_fallback` scope and processor economics | treating fallback as ungrounded | none |
| `profile_financials_no_peers_001` | StoreGrid / fictional retail tech | profile + financials | metrics used without invented peers | unsupported competitors | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `aapl_static_fallback_001` | Apple / real-company static fallback | no provider data | light, stable high-level understanding and no provider claims | precise metrics or current-news claims | `REVIEW_REAL_COMPANY_FACTS` |
| `nvda_static_fallback_001` | NVIDIA / real-company static fallback | no provider data | light, stable high-level understanding and no provider claims | precise metrics or recent-market claims | `REVIEW_REAL_COMPANY_FACTS` |

## Controlled contrast and adversarial cases

| Case | Entity / contrast | Provider availability | Expected adaptation | Tested failure | Review flags |
|---|---|---|---|---|---|
| `cloudx_low_leverage_001` | CloudX, low leverage | profile + financials | refinancing risk should not dominate | ignoring supplied leverage | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `cloudx_high_leverage_001` | CloudX, high leverage | same profile + changed financials | refinancing/balance-sheet risk becomes material | context-insensitive risks | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `admesh_high_margin_001` | AdMesh, high operating margin | profile + financials | acknowledge margin buffer/pricing economics | claiming low-margin fragility | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `admesh_low_margin_001` | AdMesh, low operating margin | same profile + changed financials | margin compression sensitivity rises | context-insensitive economics | `SYNTHETIC_FINANCIAL_FIXTURE` |
| `novapay_peers_present_001` | NovaPay with supplied peers | profile + peers | competitive landscape stays within supplied set | unsupported competitors | none |
| `novapay_peers_missing_001` | NovaPay without peers | same profile only | no fabricated provider-backed competitors | memorized or invented peer list | none |

## Reviewer attention

The lowest-confidence cases are the five real-company qualitative cases and two
static-fallback cases. Confirm that their business-model descriptions remain
stable and that forbidden category errors are fair. All numeric fixtures are
invented and should be reviewed only for internal plausibility, not factual
accuracy.
