# SentinelAI

Autonomous monitoring system with LangGraph agents that query Prometheus, search runbooks via RAG, and produce incident reports.

## Overview

SentinelAI is an intelligent monitoring system that combines LangGraph agents with Prometheus metrics and vector-based runbook search to automate incident detection and response.

## Architecture

- **Nginx** - Load balances requests across FastAPI backend replicas
- **FastAPI** - REST API + SSE for streaming responses
- **Celery** - Asynchronous LangGraph agent task execution
- **LangGraph** - Orchestrates supervisor and specialist agents
- **Prometheus** - Metrics collection and PromQL queries
- **pgvector** - RAG-based runbook search with embeddings
- **PostgreSQL** - Application data storage
- **Redis** - Session state, Celery broker, and results backend
- **Docker Swarm** - Container orchestration with health checks

## Requirements

- Python 3.11+
- Docker Swarm
- PostgreSQL 16 with pgvector extension
- Redis 7
- Prometheus

## Development

Install dependencies:
```bash
uv sync
```

Run tests:
```bash
uv run pytest
```

Lint and format:
```bash
uv run ruff check .
uv run ruff format .
```

## Deployment

Generate secrets:
```bash
./scripts/generate-secrets.sh
```

Deploy to Swarm:
```bash
./scripts/deploy-swarm.sh
```

## License

MIT
