"""
SentinelAI FastAPI Application.

Autonomous monitoring system with LangGraph agents that query Prometheus,
search runbooks via RAG, and produce incident reports.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from api.database import close_db_connections
from api.routers import agents, health, incidents, runbooks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown tasks:
    - Startup: Initialize Prometheus metrics instrumentation
    - Shutdown: Close database connections gracefully
    """
    # Startup: Initialize Prometheus instrumentation
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/health/ready", "/metrics"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )
    instrumentator.instrument(app)

    yield

    # Shutdown: Close database connections
    await close_db_connections()


app = FastAPI(
    title="SentinelAI",
    description="Autonomous monitoring system with LangGraph agents",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(health.router)
app.include_router(incidents.router)
app.include_router(agents.router)
app.include_router(runbooks.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "SentinelAI API", "version": "0.1.0", "status": "running"}
