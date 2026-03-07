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
- **Celery healthcheck**: Use lightweight `pgrep` instead of `inspect ping` to avoid broker overhead
- **Bind mounts in Swarm**: Only work on single-node or with shared storage
- **Vector search**: Must run `CREATE INDEX` after inserting embeddings for performance
- **Redis auth**: Build connection URLs from secrets at runtime via entrypoint script, never hardcode

## Development Issues
### Docker Compose Security Audit (2026-03-07)
During infrastructure review, identified and fixed 7 critical issues in `docker-compose.yml`:

1. **Hardcoded Redis passwords in environment variables** — Passwords were visible in `docker inspect`. Fixed by removing hardcoded URLs; secrets now injected via entrypoint script at runtime.

2. **Redis healthcheck shell substitution bug** — CMD-form array `["CMD", ...]` doesn't expand `$(cat ...)`. Changed to `CMD-SHELL` form for proper secret interpolation.

3. **Missing vectordb_password secret** — Backend and Celery declared dependency on vectordb but couldn't authenticate. Added `vectordb_password` to both services' secrets lists.

4. **Prometheus/Grafana exposed ports** — Ports 9090 and 3000 bypassed nginx entirely. Prometheus has no built-in auth. Removed `ports` blocks; services now accessible only via nginx reverse proxy with authentication.

5. **No logging rotation** — Default `json-file` driver has no limits, risking disk exhaustion. Added `max-size: 10m` and `max-file: 3` to all services.

6. **Unpinned image tags** — `latest` tags are mutable and risk breaking changes. Pinned all images to specific versions (nginx:1.25-alpine, postgres:16.2-alpine, redis:7.2-alpine, prometheus:v2.51.0, grafana:10.4.1).

7. **Expensive Celery healthcheck** — `celery inspect ping` creates full broker connections every 30s. Replaced with lightweight `pgrep -f 'celery.*worker'` process check.

**Action Required**: Create entrypoint scripts for backend and celery-worker to build `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and `VECTORDB_URL` from secrets at container startup.

### UV + Hatchling Configuration Fixes (2026-03-07)
Fixed 4 issues preventing `uv sync` and Docker builds:

1. **UV deprecation warning** — `[tool.uv.dev-dependencies]` is deprecated. Migrated to `[dependency-groups]` format as per UV's new standard.

2. **Missing README.md** — Hatchling build failed because `pyproject.toml` referenced `readme = "README.md"` but file didn't exist. Created basic README with project overview and architecture.

3. **Hatchling package discovery** — Build failed with "Unable to determine which files to ship inside the wheel." Project uses `api/` and `ingestion/` directories, not `sentinel_ai/`. Added `[tool.hatch.build.targets.wheel]` with `packages = ["api", "ingestion"]`.

4. **Docker build failures** — Both Dockerfiles failed to build:
   - Missing `README.md` and `uv.lock` in COPY commands (required for `uv sync --frozen`)
   - Redundant `uv pip install celery[redis] flower` in Dockerfile.celery (dependencies already in pyproject.toml)
   - Fixed by copying `pyproject.toml README.md uv.lock` in builder stage and removing duplicate install

### Docker Swarm Deployment Fixes (2026-03-07)
Fixed 6 compatibility issues preventing `docker stack deploy`:

1. **Extended depends_on syntax unsupported** — `docker stack deploy` failed with "depends_on must be a list." Docker Swarm doesn't support the extended `depends_on` syntax with conditions (e.g., `condition: service_healthy`). Converted all `depends_on` blocks from extended syntax to simple lists. Note: Swarm ignores `depends_on` entirely and relies on healthchecks for startup ordering, but simple lists allow the compose file to work with both `docker compose` (local dev) and `docker stack deploy` (Swarm).

2. **Missing image tags for built services** — `docker stack deploy` failed with "image reference must be provided." Swarm doesn't support the `build` directive alone. Added `image` tags to `backend` (sentinel-ai-backend:latest) and `celery-worker` (sentinel-ai-celery-worker:latest). The `build` directive is used by `docker compose build` to create images, while the `image` tag tells Swarm which image to deploy. Workflow: run `docker compose build` first, then `docker stack deploy`.

3. **Nginx startup-time DNS resolution failure** — Nginx failed with "host not found in upstream 'backend:8000'" because `upstream` blocks resolve DNS at startup time, before backend service exists in Swarm. Removed `upstream backend_servers` block and replaced all `proxy_pass http://backend_servers` with variable-based `proxy_pass $backend_upstream` (where `set $backend_upstream http://backend:8000`). Variables force nginx to use the resolver directive at request time instead of startup time, allowing it to start even when backend doesn't exist yet. Also created minimal bootstrap files (`api/main.py`, `api/tasks/celery_app.py`, package `__init__.py` files) to prevent import errors.

4. **Prometheus missing configuration file** — Prometheus service failed with "bind source path does not exist: prometheus.yml". Bind mounts require files to exist on the host before deployment. Created minimal `monitoring/prometheus/prometheus.yml` with basic scrape configs for self-monitoring and backend API metrics endpoint.

5. **Grafana missing directories** — Grafana service failed with "bind source path does not exist: grafana/dashboards". Created `monitoring/grafana/dashboards/` and `monitoring/grafana/datasources/` directories with provisioning configs. Added `datasources/prometheus.yml` to configure Prometheus as default datasource and `dashboards/dashboards.yml` for dashboard provisioning.

6. **Celery-worker insufficient resources** — Both Celery worker replicas failed with "no suitable node (insufficient resources on 1 node)". Initial resource requests (2 replicas × 1 CPU + 1GB reserved = 2 CPU + 2GB total) exceeded local development machine capacity. Reduced resource reservations from `cpus: '1'` / `memory: 1G` to `cpus: '0.25'` / `memory: 256M` per replica, and limits from `cpus: '2'` / `memory: 2G` to `cpus: '1'` / `memory: 1G` per replica. New totals: 0.5 CPU + 512MB reserved, 2 CPU + 2GB limit.

## Post-Implementation Checklist
- [ ] Green CI (all 4 stages)  
- [ ] Coverage > 80%  
- [ ] No file > 300 LOC  
- [ ] Security checklist per commit  

