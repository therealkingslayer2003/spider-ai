# Spider-AI

## Product and scope

Spider-AI is a local-first asset market research copilot. Snapshot explains business structure, peers, drivers, and risks; Thesis adds valuation, catalysts, and invalidation. Users provide asset name/type; research assumptions belong to the workflow.

## Architecture

Use vertical feature packages with shared infrastructure. HTTP endpoints call services, services invoke graph runners, and runners expose typed results. Graph routers have subgraphs; their nodes coordinate capability tools and LLM generation. The service then persists validated output and evidence. Chat calls the LLM through its service directly.

| Location | Responsibility |
| --- | --- |
| `app/api/v1/` | Routes, HTTP contracts, exception-to-status mapping. |
| `app/api/dependencies.py` | Composition root: construct and inject services, graphs, tools, providers, and persistence. |
| `app/services/` | Application use cases and persistence transaction orchestration. |
| `app/agents/<feature>/` | Runner, graphs, state, nodes, and feature helpers. Snapshot separates `router/` from `stock/`. |
| `app/agents/asset_snapshot/tools/` | Capability interfaces for nodes; provider fallback, enrichment, and normalized-result caching. |
| `app/market_data/` | Provider protocols, vendor I/O, and normalization into domain contexts. |
| `app/domain/schemas/` | Pydantic requests, responses, evidence, and normalized context contracts. |
| `app/llm/`, `app/llm/prompts/` | Model-client abstraction/adapters; prompt templates, builders, and projections. |
| `app/infrastructure/db/` | Async SQLAlchemy/SQLite, ORM models, focused DAOs, and numbered SQL migrations. |
| `app/core/` | Settings, logging, and shared exceptions. |

- Follow existing naming and constructor injection. Nodes depend on capabilities; vendor selection belongs in tools/providers. Avoid vendor clients or SQL in endpoints and graph nodes.
- Keep graph wiring separate from node behavior. Keep router state minimal and feature-specific context inside subgraphs.
- Reuse `BaseChatModelClient` and prompt builders. Structured generation returns Pydantic objects; avoid unnecessary JSON round-trips.
- Preserve shared tool lifetimes and tool-owned caches; do not add duplicate provider caches. Keep blocking vendor calls off the async event loop.
- Put runtime tuning (including RAG splitter and embedding limits) in `app/core/config.py` and `.env.example`, then inject it at composition roots. Avoid hidden tuning defaults in feature constructors or CLIs; validate related limits and version processing changes.
- Put config values of llm/embedding/tokenizer/integration services into .env under it's own category divided by comments, never hardcode config values in specific code places

## Contracts and evidence

- Preserve normalized units, periods, provenance, and `data_scope`. Distinguish source facts, analytical inferences, and missing-data fallback. Financial calculations belong in code.
- Keep request/workflow-owned metadata authoritative. Preserve explicit unsupported-type errors and documented optional-data fallbacks.

## Working rules

Read `docs/architecture.md` for boundaries, `docs/product definition.md` for product intent, and relevant feature docs such as `docs/thesis_mode_v1.md` or `evals/README.md`. Treat implementation as evidence of current behavior and plans as intended work.

Complete the requested scope; reuse existing paths before introducing abstractions. Update affected docs/contracts and report changes, checks actually run, and remaining gaps. Keep this file focused on repository-wide rules; detailed feature plans belong in their own documents.
After an implementation finished provide a clear design overview to a user so it's easy to understand what was done and why.
