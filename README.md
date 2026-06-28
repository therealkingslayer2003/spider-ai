# spider-ai

spider-ai — an asset market research copilot for structured asset and market analysis.

## Current Status

This project is currently at the backend skeleton stage.

### Implemented

- FastAPI backend
- Local LLM integration through Ollama
- LangChain `ChatOllama` client
- LangGraph agent pipeline (planner → profile tool → LLM generation → validation)
- Asset snapshot endpoint — structured `AssetSnapshot` output with profile, drivers, and risks (mocked data for now)
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
   pip install -e .
   ```

5. Run API:

   ```bash
   uvicorn app.main:app --reload
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
pytest
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
  core/                 # Config, logging, exceptions
  domain/schemas/       # Pydantic request/response models
  llm/                  # LLM provider abstractions
  services/             # Business logic
  tools/                # Future: tool abstractions
  retrieval/            # Future: RAG
  workflows/            # Future: workflow orchestration

tests/                  # pytest test suite
```

## Roadmap

- Structured outputs
- Market data tools
- RAG
- Evidence-aware answers
- Evaluation
- Observability
- Workflow orchestration
- Agent layer

---

> **Disclaimer:** This tool is not financial advice.
