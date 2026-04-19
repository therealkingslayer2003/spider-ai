# AI Market Research Copilot

Evidence-aware AI research copilot for structured asset and market analysis.

## Current Status

This project is currently at the backend skeleton stage.

### Implemented

- FastAPI backend
- Local LLM integration through Ollama
- LangChain `ChatOllama` client
- Basic chat endpoint
- Health endpoint
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

## Test Chat

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Give me a short research-style overview of NVIDIA.",
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
- Asset snapshot mode
- Market data tools
- RAG
- Evidence-aware answers
- Evaluation
- Observability
- Workflow orchestration
- Agent layer

---

> **Disclaimer:** This tool is not financial advice.
