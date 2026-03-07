# SentinelAI — Living Memory of the Project

## Overview
Autonomous monitoring system with LangGraph agents that query Prometheus, search runbooks via RAG, and produce incident reports.
CI pipeline: Ruff → pip-audit → Bandit/Semgrep → pytest. Green CI = law.

## Architecture
- **Nginx** load balances requests across 3 FastAPI backend replicas
- **FastAPI** exposes REST API + SSE for streaming responses
- **Celery** workers (2 replicas) execute LangGraph agent tasks asynchronously
- **LangGraph** orchestrates a graph of 4 agents (supervisor → specialists → synthesis)
- **Prometheus** is both the data source AND the tool agents call via PromQL
- **pgvector** (PostgreSQL) stores runbook embeddings for RAG with IVFFlat indexing
- **PostgreSQL** stores application data (users, incidents, runbooks, agent_runs)
- **Redis** serves triple duty: session state (db 0), Celery broker (db 1), Celery results (db 2)
- **Docker Swarm** orchestrates deployment with health checks and rolling updates

## Technology Stack
- Python 3.11, UV package manager
- FastAPI, Uvicorn, SQLAlchemy async
- Celery + Flower for task queue
- LangGraph, LangChain tools
- PostgreSQL 16 + pgvector extension
- Redis 7 with persistence
- Nginx (load balancer, rate limiting)
- Prometheus + Grafana
- Docker Swarm with overlay networking
- GitHub Actions → GHCR → Swarm deployment

## Infrastructure Setup Completed
- ✅ Docker Compose file for Swarm with 8 services (nginx, backend×3, celery×2, postgres, vectordb, redis, prometheus, grafana)
- ✅ All services use healthchecks for dependency management
- ✅ Docker secrets for all sensitive credentials (db, redis, API keys, JWT)
- ✅ Bind mounts for development hot-reload (api/ and ingestion/)
- ✅ Nginx configured with rate limiting, SSL-ready, SSE streaming support
- ✅ Deployment scripts: generate-secrets.sh, deploy-swarm.sh, remove-swarm.sh, update-swarm.sh
- ✅ Database init scripts with schema, indexes, and triggers
- ✅ Vector DB with similarity search function and IVFFlat indexes

## Service Separation
- Routers do NOT contain business logic — only input/output validation
- Tools (tools/) are pure functions testable in isolation
- Agents do NOT know HTTP details
- Celery tasks handle long-running LangGraph executions
- Backend enqueues tasks, Celery workers execute them

## Design Patterns
- Repository pattern for data access
- Dependency injection via FastAPI Depends()
- Explicit state machine in LangGraph (TypedDict)
- Task queue pattern for async agent execution
- Secrets management via Docker Swarm secrets

## Required Environment Variables
- OPENAI_API_KEY / ANTHROPIC_API_KEY
- DATABASE_URL (postgresql+asyncpg://...)
- VECTORDB_URL (postgresql+asyncpg://...)
- REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
- PROMETHEUS_URL
- JWT_SECRET_KEY

## Directory Structure
```
api/               # FastAPI application
  ├── agents/      # LangGraph agent definitions
  ├── models/      # SQLAlchemy models
  ├── routers/     # API route handlers
  └── tools/       # LangChain tools for agents
ingestion/         # Data ingestion pipelines
monitoring/
  ├── nginx/       # Nginx config + load balancer rules
  ├── postgres/    # DB init scripts
  ├── prometheus/  # Prometheus config
  └── grafana/     # Dashboards (to be added)
scripts/           # Deployment automation
secrets/           # Docker secrets (gitignored)
tests/             # Unit and integration tests
  ├── unit/
  └── integration/
```

## Common Hurdles
- **UV + Docker**: Dockerfile uses multi-stage build with UV in builder stage
- **Secrets in Swarm**: Use `docker secret create`, not environment variables
- **Celery healthcheck**: Requires `inspect ping` command, 60s start period
- **Bind mounts in Swarm**: Only work on single-node or with shared storage
- **Vector search**: Must run `CREATE INDEX` after inserting embeddings for performance
- **Redis auth**: Use `redis://:<password>@host:port/db` format in connection string

## Post-Implementation Checklist
- [ ] Green CI (all 4 stages)  
- [ ] Coverage > 80%  
- [ ] No file > 300 LOC  
- [ ] Security checklist per commit  

