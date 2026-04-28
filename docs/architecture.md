# Architecture

This document describes spider-ai — an asset market research copilot.

## Overview
The project is a FastAPI application that delegates LLM calls to a local Ollama service. The codebase follows a layered structure and is containerized via Docker Compose.

### Request flow (high-level)

```
Client -> HTTP -> FastAPI endpoints (app/api/v1/endpoints)
                             -> Services (app/services)
                             -> LLM client (app/llm) -> Ollama (container)
```

## Main components

- **API (service)**: `app/main.py` mounts the v1 router (`/api/v1`) defined at [app/api/v1/router.py](app/api/v1/router.py). Endpoints live under [app/api/v1/endpoints](app/api/v1/endpoints).
- **Schemas**: Pydantic models in `app/domain/schemas/` (request/response shapes).
- **Services**: Business logic lives in `app/services/` (e.g. `chat_service.py`). Services call LLM clients and other helpers.
- **LLM clients**: Adapter layer in `app/llm/` (e.g. `ollama_client.py`) — wraps `langchain-ollama`/`ChatOllama`.
- **Core**: `app/core/` contains configuration, logging, and shared utilities.

## API surface (important endpoints)

- `GET /api/v1/health` — health check, returns `{status: "ok", service: "<name>"}`.
- `POST /api/v1/chat` — main chat endpoint. Expected JSON shape:

```json
{ "message": "<user question>", "asset": "<optional asset id>" }
```

Response model: `{ "answer": "<text>", "model": "<model-name>" }`.

Note: `/chat` without the `/api/v1` prefix will return 404. The chat endpoint expects `POST`, not `GET`.

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
- `OLLAMA_BASE_URL` — base URL used by the API to reach Ollama. When running via Docker Compose set this to `http://ollama:11434` so the `api` container reaches the `ollama` container on the compose network (using `http://localhost:11434` from inside `api` will not reach the `ollama` container).
- `OLLAMA_CHAT_MODEL` — model name expected by the code (e.g. `llama3.1:8b`).
- `OLLAMA_TEMPERATURE` — sampling temperature.
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

curl -X POST http://localhost:8000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"Hello","asset":null}'
```

## Troubleshooting notes

- 404 responses when calling `/chat` are usually due to missing the `/api/v1` prefix or using `GET` instead of `POST`.
- `uvicorn: executable file not found` at container start usually meant the virtualenv's `bin` directory was not on `PATH`; the `Dockerfile` ensures `/app/.venv/bin` is included in `PATH`.
- `All connection attempts failed` / `httpx.ConnectError` indicates the API cannot reach the configured `OLLAMA_BASE_URL`; ensure the env var points at the compose service hostname `ollama` when using Docker Compose.
- `model '<name>' not found (404)` means the Ollama service is running but the requested model is not loaded — pull it into the `ollama` container using `ollama pull`.

## File layout (quick)

- `app/main.py` — application factory and entrypoint
- `app/api/v1/router.py` — API router mounting
- `app/api/v1/endpoints/*.py` — endpoints (health, chat)
- `app/services/*.py` — service layer (business logic)
- `app/llm/*.py` — LLM client adapters (Ollama client)
- `pyproject.toml`, `uv.lock` — dependency declaration and lockfile
- `Dockerfile`, `docker-compose.yml` — container build & orchestration

---
