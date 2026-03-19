"""
Health check and monitoring endpoints.

Provides:
- Liveness probe (basic status)
- Readiness probe (dependency checks)
- Prometheus metrics
"""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, get_vectordb

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Basic health status response."""

    status: str
    service: str


class DependencyStatus(BaseModel):
    """Health status for a single dependency."""

    name: str
    status: str
    latency_ms: float | None = None
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Detailed readiness check response."""

    status: str
    dependencies: list[DependencyStatus]


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """
    Liveness probe endpoint.

    Returns basic status indicating the service is running.
    Used by Kubernetes/Docker Swarm to determine if container should be restarted.

    Returns:
        200 OK: Service is alive
    """
    return {"status": "healthy", "service": "sentinel-ai"}


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        503: {
            "description": "Service not ready - one or more dependencies unavailable",
            "model": ReadinessResponse,
        }
    },
)
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    vectordb: AsyncSession = Depends(get_vectordb),
) -> dict[str, Any]:
    """
    Readiness probe endpoint.

    Performs deep connectivity checks against all critical dependencies:
    - PostgreSQL (application database)
    - pgvector (vector database)
    - Redis (via connection pool check)
    - Prometheus (via HTTP health endpoint)

    Used by load balancers to determine if traffic should be routed to this instance.

    Returns:
        200 OK: All dependencies healthy
        503 Service Unavailable: One or more dependencies failed
    """
    import os
    import time

    import httpx
    import redis.asyncio as aioredis

    dependencies: list[DependencyStatus] = []
    overall_healthy = True

    # Check PostgreSQL
    try:
        start = time.perf_counter()
        await db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        dependencies.append(
            DependencyStatus(
                name="postgresql",
                status="healthy",
                latency_ms=round(latency, 2),
            )
        )
    except Exception as e:
        overall_healthy = False
        dependencies.append(
            DependencyStatus(
                name="postgresql",
                status="unhealthy",
                error=str(e),
            )
        )

    # Check pgvector
    try:
        start = time.perf_counter()
        await vectordb.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        dependencies.append(
            DependencyStatus(
                name="pgvector",
                status="healthy",
                latency_ms=round(latency, 2),
            )
        )
    except Exception as e:
        overall_healthy = False
        dependencies.append(
            DependencyStatus(
                name="pgvector",
                status="unhealthy",
                error=str(e),
            )
        )

    # Check Redis
    try:
        start = time.perf_counter()
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        latency = (time.perf_counter() - start) * 1000
        await redis_client.close()
        dependencies.append(
            DependencyStatus(
                name="redis",
                status="healthy",
                latency_ms=round(latency, 2),
            )
        )
    except Exception as e:
        overall_healthy = False
        dependencies.append(
            DependencyStatus(
                name="redis",
                status="unhealthy",
                error=str(e),
            )
        )

    # Check Prometheus
    try:
        import os

        prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            prom_response = await client.get(f"{prometheus_url}/-/healthy")
            prom_response.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        dependencies.append(
            DependencyStatus(
                name="prometheus",
                status="healthy",
                latency_ms=round(latency, 2),
            )
        )
    except Exception as e:
        # Prometheus is not critical for app startup, just log
        dependencies.append(
            DependencyStatus(
                name="prometheus",
                status="degraded",
                error=str(e),
            )
        )

    # Set response status code
    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if overall_healthy else "not_ready",
        "dependencies": dependencies,
    }


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Exposes application metrics in Prometheus exposition format.
    Includes default metrics (requests, latency, in-progress) plus custom metrics.

    Note: This endpoint is auto-instrumented via prometheus-fastapi-instrumentator
    in the main app startup. This handler just returns the latest metrics snapshot.

    Returns:
        Prometheus-formatted metrics text
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
