# Architecture

This document describes spider-ai — an asset market research copilot.

## Overview

The backend is a FastAPI application structured in vertical layers. Each layer has a single responsibility. No layer may skip a layer below it.

```
HTTP Request
    │
    ▼
API Endpoint (app/api/v1/endpoints/)
    │  validates input, delegates to service
    ▼
Service (app/services/)
    │  orchestrates business logic
    ▼
LLM Client (app/llm/)
    │  calls Ollama via LangChain
    ▼
Ollama (local)
```

## Layers

| Layer | Path | Responsibility |
|---|---|---|
| API | `app/api/` | HTTP routing, request/response handling |
| Schemas | `app/domain/schemas/` | Pydantic input/output models |
| Services | `app/services/` | Business logic |
| LLM | `app/llm/` | LLM provider abstraction |
| Core | `app/core/` | Config, logging, shared exceptions |

## Future Layers (not yet implemented)

| Layer | Path | Purpose |
|---|---|---|
| Tools | `app/tools/` | Market data tool interfaces |
| Retrieval | `app/retrieval/` | RAG — document ingestion, chunking, vector search |
| Workflows | `app/workflows/` | Multi-step research workflows |

## LLM Integration

- Provider: [Ollama](https://ollama.com) (local)
- Client library: `langchain-ollama` (`ChatOllama`)
- Abstraction: `BaseChatModelClient` — all LLM clients implement this interface
- Config: driven by `Settings` (Pydantic Settings, `.env`)

## Configuration

All settings live in `app/core/config.py` and are loaded via `pydantic-settings`.  
A `.env` file (copied from `.env.example`) overrides defaults.
