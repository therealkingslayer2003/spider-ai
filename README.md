# spider-ai

spider-ai — an asset market research copilot for structured asset and market analysis.

## Current Status

This project is a FastAPI backend for structured asset research workflows. The
main implemented workflow is Asset Snapshot: it resolves an asset input,
retrieves normalized profile context from yfinance, and asks a local Ollama LLM
to synthesize a schema-validated structural snapshot.

### Implemented

- FastAPI backend
- Local LLM integration through Ollama
- LangChain `ChatOllama` client
- LangGraph Asset Snapshot workflow
- Optional ambiguous asset resolver before tool execution
- yfinance-backed asset profile provider for stocks and ETFs
- In-memory TTL cache for asset profile context
- Structured `AssetSnapshot` output with profile, drivers, and risks
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

The Asset Snapshot workflow currently supports yfinance profile context for
`stock` and `etf` assets. If no provider profile is found, the graph still asks
the LLM to generate a schema-valid structural snapshot with explicit fallback
context.

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
  agents/               # LangGraph workflow state, graph, and nodes
  core/                 # Config, logging, exceptions
  domain/schemas/       # Pydantic request/response models
  llm/                  # LLM provider abstractions
  market_data/          # yfinance provider and profile cache
  services/             # Business logic
  tools/                # Workflow tools

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
