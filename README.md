# spider-ai

spider-ai — an asset market research copilot for structured asset and market analysis.

## Product Roadmap
```mermaid
flowchart TB
 subgraph V1_FEATURES["v1 Features"]
    direction LR
        S1["Asset Snapshot"]
        T1["Thesis Mode"]
        F1["Introducing Front End for Spider AI"]
        S1A["Short / Long Snapshot"]
        S1B["Stable / Semi-Stable Asset Profile"]
        T1A["Bull / Bear / Risk Thesis"]
        T1B["Dynamic Research View"]
        F1A["Basic UI for Created Features"]
  end
 subgraph V2_FEATURES["v2 Features"]
    direction LR
        W1["What Changed Mode"]
        E1["Evidence View"]
        F2["Enhanced Front End for Spider AI"]
        W1A["Previous Analysis Comparison"]
        W1B["Selected Time Window"]
        E1A["Answer Explanation"]
        E1B["Evidence Strength"]
        F2A["Interactive Dashboards"]
  end
 subgraph V3_FEATURES["v3 Features"]
    direction LR
        M1["Multi Agent Debate Mode"]
        M1A["Bull Agent"]
        M1B["Bear Agent"]
        M1C["Risk Agent"]
        M1D["Deep Research & Reasoning"]
        M1E["Evidence-Backed Results"]
  end
    A["Spider AI Product Roadmap"] --> V1["v1"]
    V1 --> V1_FEATURES
    S1 --> S1A
    S1A --> S1B
    T1 --> T1A
    T1A --> T1B
    F1 --> F1A
    V1_FEATURES --> V2["v2"]
    V2 --> V2_FEATURES
    W1 --> W1A
    W1A --> W1B
    E1 --> E1A
    E1A --> E1B
    F2 --> F2A
    V2_FEATURES --> V3["v3"]
    V3 --> V3_FEATURES
    M1 --> M1A & M1B & M1C & M1D & M1E
```
## Current Status

This project is a FastAPI backend for structured asset research workflows. The
main implemented workflow is Asset Snapshot: it resolves an asset input,
retrieves normalized provider context through capability tools, and asks a
local Ollama LLM to synthesize a schema-validated structural snapshot.
The workflow is routed through `AssetSnapshotRouterGraph`; only the stock
subgraph is implemented today.

### Implemented

- FastAPI backend
- Local LLM integration through Ollama
- LangChain `ChatOllama` client
- LangGraph Asset Snapshot workflow
- Asset Snapshot router graph with implemented stock subgraph
- Optional ambiguous asset resolver before tool execution
- yfinance-backed company profile provider for stocks
- Optional FMP integration for profile fallback and peers
- In-memory TTL caches for provider contexts
- Structured `StockAssetSnapshot` output with profile, drivers, and risks
- Rich terminal debug logs for workflow and LLM tracing
- Basic chat endpoint
- Health endpoint
- LangSmith observability integration
- Production-minded project structure

## Run Locally

1. Install [Ollama](https://ollama.com)

2. Pull model:

   ```bash
   ollama pull llama3.1
   ```

3. Create `.env` from `.env.example`:

   ```bash
   cp .env.example .env
   ```

4. Install dependencies:

   ```bash
   uv sync
   ```

5. Run API:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

6. Open interactive docs: http://localhost:8000/docs

## Local Debug Logs

Pretty terminal logs are enabled by default in local debug mode.

Use these `.env` flags to control workflow tracing:

```bash
APP_PRETTY_LOGS=true
APP_LOG_FLOW_STEPS=true
APP_LOG_LLM_PROMPTS=false
APP_LOG_LLM_OUTPUTS=false
APP_LOG_PREVIEW_CHARS=600
```

Turn on `APP_LOG_LLM_PROMPTS=true` or `APP_LOG_LLM_OUTPUTS=true` when you need
to inspect the exact prompt/output preview that went through Ollama. Keep them
off for normal local runs if the payload may contain sensitive user input.

## Market Data Providers

yfinance is the default free company profile provider. FMP is optional and the
project runs without it.

To enable FMP peer context and profile fallback:

```bash
FMP_ENABLED=true
FMP_API_KEY=your_fmp_api_key
FMP_BASE_URL=https://financialmodelingprep.com/stable
FMP_CACHE_TTL_SECONDS=86400
```

When FMP is disabled, missing, rate-limited, or incomplete, Asset Snapshot still
runs. The graph continues with empty peers and optional yfinance financial
fundamentals. Static hardcoded peer and sector mappings are not used as production
data sources.

Asset Snapshot v1 intentionally stays business-model-first:

- Core: company name, sector, industry, business summary, and country.
- Optional enrichment: peers and yfinance revenue, revenue growth, operating
  margin, and normalized debt-to-equity ratio.
- Financial metadata: reporting currency, latest fiscal-year end, and most
  recent quarter when supplied by yfinance.
- Not collected for v1: gross margin, net margin, or return on equity.

A usable company profile is sufficient for a provider-grounded snapshot.
Missing financial signals do not fail or downgrade the workflow; only a missing
profile activates `model_static_knowledge_fallback`.

Asset Snapshot fundamentals provide quantitative context for understanding
business economics and structural drivers/risks. They are interpreted together
with the company profile; they do not estimate fair value or determine whether
a stock is cheap, expensive, bullish, or bearish. Market capitalization and
valuation multiples are intentionally outside this Snapshot context.

`debt_to_equity_ratio` is a normalized multiple: `2.0` means debt is
approximately 2x shareholders' equity. The yfinance adapter converts Yahoo's
percentage-style `debtToEquity` value before creating the domain context; for
example, Yahoo `200` becomes Spider-AI `2.0`.

The financial fields do not share an asserted global period. Revenue, growth,
margin, and leverage may have different provider-defined temporal semantics;
the supplied fiscal-year and quarter dates are reference metadata, not proof
that every metric belongs to the same reporting period.

## Run with Docker Compose

```bash
docker compose up --build
```

> If Ollama is running on the host machine (not in Docker), set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in your `.env`.

## Run Tests

```bash
uv run pytest
```

Live LLM resolver tests are opt-in because they call the configured Ollama
model:

```bash
RUN_LIVE_LLM_RESOLVER_TESTS=true uv run pytest tests/test_asset_resolver_live.py -m live_llm -vv
```

## Asset Snapshot Evals

The local Stock Asset Snapshot eval harness reuses the production router,
subgraph, tools, prompt builder, and response schema while replacing market-data
providers with frozen fixtures. Its synthetic v1 dataset is intentionally marked
`pending_manual_review` and is excluded from default runs until a reviewer
approves individual cases.

```bash
# Validate dataset structure and review metadata without calling an LLM
uv run python -m evals.asset_snapshot.run --validate-only

# Run approved cases only (the default)
uv run python -m evals.asset_snapshot.run --dataset stock_snapshot_v1

# Explicit non-baseline exploration of pending cases
uv run python -m evals.asset_snapshot.run \
  --dataset stock_snapshot_v1 \
  --include-pending
```

See [`evals/README.md`](evals/README.md) and
[`evals/datasets/stock_snapshot_v1_review.md`](evals/datasets/stock_snapshot_v1_review.md)
for grader behavior, approval steps, and the manual-review checklist. Semantic
evals use a separately configurable judge model and are never run implicitly by
the test suite.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/health` | Health check |
| `POST` | `/api/v1/chat` | Open-ended asset research chat |
| `POST` | `/api/v1/asset/snapshot` | Generate a short or long structured asset profile |

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

## Get Asset Snapshot

```bash
curl -X POST http://localhost:8000/api/v1/asset/snapshot \
  -H "Content-Type: application/json" \
  -d '{
    "asset": "NVDA",
    "asset_type": "stock"
  }'
```

The Asset Snapshot workflow currently supports `stock` assets through
`StockSnapshotSubgraph`. yfinance provides the default company profile and any
available supporting financial fundamentals. FMP can provide company peers and
profile fallback. ETF, commodity, and crypto subgraphs are planned extension
points but are not implemented yet; unsupported asset types return a controlled
client error instead of falling through to stock logic.

## Test Chat

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Give me a research-style overview of NVIDIA.",
    "asset": "NVDA"
  }'
```

## Project Structure

```
app/
  main.py               # FastAPI app factory
  api/v1/               # HTTP layer — routers and endpoints
  agents/               # Agent packages, including Asset Snapshot graphs/tools
  core/                 # Config, logging, exceptions
  domain/schemas/       # Pydantic request/response models
  llm/                  # LLM provider abstractions
  market_data/          # yfinance/FMP providers and caches
  services/             # Business logic
  agents/.../tools/     # Workflow-facing Asset Snapshot tools

tests/                            # pytest suite (25 tests)
  test_health.py
  test_chat.py
  test_asset_snapshot_service.py
  test_prompt_builder.py

scripts/
  pre-push                        # Git pre-push hook (cross-platform sh)
  setup-hooks.py                  # Installs the hook into .git/hooks/
  README.md                       # Developer tooling guide
```

## Code Quality

This project uses [`ruff`](https://docs.astral.sh/ruff/) for formatting and linting.

```bash
# Format
uv run ruff format app/ tests/

# Check without changes
uv run ruff format --check app/ tests/

# Lint and auto-fix
uv run ruff check --fix app/ tests/
```

A pre-push git hook runs the format check automatically before every push. To install it:

```bash
python scripts/setup-hooks.py
```

## Roadmap

- Broader market data coverage
- Better ambiguous asset resolution
- Evidence-aware answers
- Evaluation
- Additional workflow-level observability

---

> **Disclaimer:** This tool is not financial advice.
