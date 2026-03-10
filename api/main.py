"""
SentinelAI FastAPI Application - Minimal Bootstrap
"""

from fastapi import FastAPI

app = FastAPI(
    title="SentinelAI",
    description="Autonomous monitoring system with LangGraph agents",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "sentinel-ai"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "SentinelAI API", "version": "0.1.0", "status": "running"}
