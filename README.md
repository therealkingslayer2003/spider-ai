# spider-ai

spider-ai — an asset market research copilot for structured asset and market analysis.

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

6. Open docs: http://localhost:8000/docs

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
signals. Static hardcoded peer and sector mappings are not used as production
data sources.

Asset Snapshot v1 intentionally stays business-model-first:

- Core: company name, sector, industry, business summary, and country.
- Optional enrichment: peers, market cap, operating margin, and debt-to-equity.
- Nice-to-have when already returned by yfinance: revenue and revenue growth.
- Not collected for v1: gross margin, net margin, or return on equity.

A usable company profile is sufficient for a provider-grounded snapshot.
Missing financial signals do not fail or downgrade the workflow; only a missing
profile activates `model_static_knowledge_fallback`.

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

## Check Health

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
available optional financial signals. FMP can provide company peers and profile
fallback. ETF, commodity, and crypto subgraphs are planned extension points but
are not implemented yet; unsupported asset types return a controlled client
error instead of falling through to stock logic.

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

tests/                  # pytest test suite
```

## Roadmap

- Broader market data coverage
- Better ambiguous asset resolution
- Evidence-aware answers
- Evaluation
- Additional workflow-level observability

---

> **Disclaimer:** This tool is not financial advice.
