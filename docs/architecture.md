# Architecture

This document describes spider-ai — an asset market research copilot.

## Overview
The project is a FastAPI application that delegates LLM calls to a local Ollama
service. The codebase follows a layered structure, uses LangGraph for the Asset
Snapshot workflow, and is containerized via Docker Compose.

### Request flow (high-level)

```
Client -> HTTP -> FastAPI endpoints (app/api/v1/endpoints)
                             -> Services (app/services)
                             -> LangGraph workflow (app/agents)
                             -> Tools / market data providers
                             -> LLM client (app/llm) -> Ollama
```

## Main components

- **API (service)**: `app/main.py` mounts the v1 router (`/api/v1`) defined at [app/api/v1/router.py](app/api/v1/router.py). Endpoints live under [app/api/v1/endpoints](app/api/v1/endpoints).
- **Schemas**: Pydantic models in `app/domain/schemas/` (request/response shapes).
- **Services**: Business logic lives in `app/services/`. `AssetSnapshotService` delegates to the graph runner, while `ChatService` calls the LLM client directly.
- **Asset Snapshot agent**: `app/agents/asset_snapshot/` contains LangGraph state, graph wiring, resolver helpers, and nodes.
- **Tools**: `app/tools/asset_snapshot/` exposes normalized provider data to the workflow.
- **Market data**: `app/market_data/` contains the provider protocol, in-memory TTL cache, and yfinance provider.
- **LLM clients**: Adapter layer in `app/llm/` (e.g. `ollama_client.py`) — wraps `langchain-ollama`/`ChatOllama`.
- **Prompts**: `app/llm/prompts/` contains Asset Snapshot prompt construction and system prompts.
- **Core**: `app/core/` contains configuration, rich terminal logging, and shared utilities.

## API surface (important endpoints)

- `GET /api/v1/health` — health check, returns `{status: "ok", service: "<name>"}`.
- `POST /api/v1/asset/snapshot` — runs the Asset Snapshot workflow. Expected JSON shape:

```json
{ "asset": "NVDA", "asset_type": "stock" }
```

Response model: `AssetSnapshot`, containing `summary`, `business_or_asset_profile`,
`market_context`, `structural_drivers`, `structural_risks`, and
`data_scope`.

- `POST /api/v1/chat` — main chat endpoint. Expected JSON shape:

```json
{ "message": "<user question>", "asset": "<optional asset id>" }
```

Response model: `{ "answer": "<text>", "model": "<model-name>" }`.

Note: `/chat` without the `/api/v1` prefix will return 404. The chat endpoint expects `POST`, not `GET`.

## Asset Snapshot workflow

The Asset Snapshot workflow is compiled in `app/agents/asset_snapshot/graph.py`.
Current node order:

```
request
  -> ambiguous_asset_resolution
  -> planner
  -> asset_profile_tool
  -> generate_snapshot
  -> validate_snapshot
```

State is intentionally serializable and contains values such as the request,
optional `resolved_asset`, selected tool name, normalized
`AssetProfileContext`, generated prompt, raw LLM output, validated output, and
errors.

Important behavior:

- Ticker-like inputs skip the LLM resolver.
- Ambiguous stock/ETF inputs may call the LLM resolver before tool execution.
- Resolver output is parsed as JSON, validated with Pydantic, and sanity-checked
  before use.
- The tool call still happens after resolution attempts; the LLM resolver never
  replaces market-data grounding.
- The final LLM output is parsed defensively to tolerate fenced JSON, then
  validated as `AssetSnapshot`.

## Market data

The workflow uses `StableAssetProfileSearchTool`, which depends on a
`MarketDataProvider` protocol. The current concrete provider is
`YFinanceMarketDataProvider`.

Provider responsibilities:

- call `yfinance.Ticker(asset).info` in a worker thread because yfinance is
  synchronous
- normalize raw yfinance data into `AssetProfileContext`
- avoid exposing raw yfinance responses outside the provider
- return `None` when no useful profile context is available

Supported yfinance-backed asset types are currently `stock` and `etf`.

`InMemoryTTLAssetProfileCache` caches successful profile contexts by
`asset + asset_type`. The default TTL is 24 hours and is configurable via
`ASSET_PROFILE_CACHE_TTL_SECONDS`.

## Prompting and validation

`AssetSnapshotPromptBuilder` builds the final generation prompt from:

- base system prompt
- Asset Snapshot task prompt
- normalized provider context when available
- explicit fallback context when provider data is unavailable

The LLM is never given raw yfinance JSON. It receives a clean provider context
block with provider name, fetch time, company/profile fields, exchange,
currency, country, and a truncated business summary.

Final output must validate against `AssetSnapshot`.

## Docker / Runtime

- `docker-compose.yml` defines two services:
    - `api` (built from the repo) — container_name `spider-ai`, exposes `8000:8000`, uses `.env` via `env_file` and depends on `ollama`.
    - `ollama` — image `ollama/ollama:latest`, exposes `11434:11434`, stores models in a Docker volume `ollama-data`.

- `Dockerfile` (API image) key points:
    - Base: `python:3.12-slim`.
    - Copies `uv`/`uvx` wrappers from `ghcr.io/astral-sh/uv` into `/usr/local/bin/`.
    - Copies `pyproject.toml` and `uv.lock`, then runs `uv sync --no-dev` which creates a `.venv` inside `/app` and installs pinned dependencies there.
    - Adds `ENV PATH="/app/.venv/bin:$PATH"` so installed console scripts (e.g. `uvicorn`) are available at runtime.
    - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## Dependency / lockfile

- This project uses the `uv` tool (Astral) for deterministic installs. The repo contains `pyproject.toml` and `uv.lock`.
- Build flow (image): `COPY pyproject.toml uv.lock .` then `RUN uv sync --no-dev` -> installs into `.venv`.

## Ollama / model management

- The `ollama` service runs a local model server. The API uses `langchain-ollama` and `ollama` client libraries to stream chat completions to the model.
- By default the project expects a model configured in `.env` via `OLLAMA_CHAT_MODEL` (example `llama3.1:8b`). If the model is not present the API will return an error like `model 'llama3.1:8b' not found (status code: 404)`.

To list available models inside the running `ollama` container:

```bash
docker compose exec ollama ollama list
```

To pull a model into the `ollama` service (can be large/slow):

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

## Environment / configuration

Key environment variables (in `.env`):

- `APP_NAME`, `APP_ENV`, `APP_DEBUG`
- `APP_PRETTY_LOGS` — enables Rich-powered terminal logs.
- `APP_LOG_FLOW_STEPS` — logs workflow breadcrumbs such as resolver, planner,
  tool, LLM, and validation steps.
- `APP_LOG_LLM_PROMPTS`, `APP_LOG_LLM_OUTPUTS` — opt-in prompt/output preview
  logging. Keep disabled when payloads may contain sensitive input.
- `APP_LOG_PREVIEW_CHARS` — max preview length for prompt/output logs.
- `OLLAMA_BASE_URL` — base URL used by the API to reach Ollama. When running via Docker Compose set this to `http://ollama:11434` so the `api` container reaches the `ollama` container on the compose network (using `http://localhost:11434` from inside `api` will not reach the `ollama` container).
- `OLLAMA_CHAT_MODEL` — model name expected by the code (e.g. `llama3.1:8b`).
- `OLLAMA_TEMPERATURE` — sampling temperature.
- `ASSET_PROFILE_CACHE_TTL_SECONDS` — TTL for cached market profile context.
- `API_V1_PREFIX` — currently `/api/v1`.

## Local development & common commands

- Generate/update the lockfile locally (requires the `uv` image/tool):

```bash
# run from repo root (host)
docker run --rm -v "${PWD}:/work" -w /work ghcr.io/astral-sh/uv:latest uv lock
```

- Build and run with docker-compose:

```bash
docker compose up --build
```

- Pull/load an Ollama model (if API reports model not found):

```bash
docker compose exec ollama ollama pull <model-name>
```

- Test endpoints (host):

```bash
curl http://localhost:8000/api/v1/health

curl -X POST http://localhost:8000/api/v1/asset/snapshot \
    -H "Content-Type: application/json" \
    -d '{"asset":"NVDA","asset_type":"stock"}'

curl -X POST http://localhost:8000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"Hello","asset":null}'
```

## Tests

Run the normal test suite:

```bash
uv run pytest
```

The test suite disables LangSmith tracing through `tests/conftest.py` so unit
tests do not emit traces or require network access.

Live resolver accuracy tests are opt-in. They call the configured Ollama server
and skip when Ollama or the configured model is unavailable:

```bash
RUN_LIVE_LLM_RESOLVER_TESTS=true uv run pytest tests/test_asset_resolver_live.py -m live_llm -vv
```

## Troubleshooting notes

- 404 responses when calling `/chat` are usually due to missing the `/api/v1` prefix or using `GET` instead of `POST`.
- `uvicorn: executable file not found` at container start usually meant the virtualenv's `bin` directory was not on `PATH`; the `Dockerfile` ensures `/app/.venv/bin` is included in `PATH`.
- `All connection attempts failed` / `httpx.ConnectError` indicates the API cannot reach the configured `OLLAMA_BASE_URL`; ensure the env var points at the compose service hostname `ollama` when using Docker Compose.
- `model '<name>' not found (404)` means the Ollama service is running but the requested model is not loaded — pull it into the `ollama` container using `ollama pull`.
- Asset resolver outputs can be imperfect because the resolver is an LLM
  pre-check. The workflow keeps provider/tool calls mandatory and validates
  resolver output before using it.

## File layout (quick)

- `app/main.py` — application factory and entrypoint
- `app/api/v1/router.py` — API router mounting
- `app/api/v1/endpoints/*.py` — endpoints (health, chat, asset snapshot)
- `app/agents/asset_snapshot/*.py` — LangGraph workflow and resolver
- `app/services/*.py` — service layer (business logic)
- `app/llm/*.py` — LLM client adapters (Ollama client)
- `app/market_data/*.py` — yfinance provider and cache
- `app/tools/asset_snapshot/*.py` — workflow-facing asset profile tool
- `tests/test_asset_resolver_live.py` — opt-in live LLM resolver tests
- `pyproject.toml`, `uv.lock` — dependency declaration and lockfile
- `Dockerfile`, `docker-compose.yml` — container build & orchestration

---
