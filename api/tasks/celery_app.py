"""
SentinelAI Celery Application - Minimal Bootstrap
"""
import os
from celery import Celery

# Get broker and backend URLs from environment (set by docker-entrypoint.sh)
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "sentinel-ai",
    broker=broker_url,
    backend=result_backend
)

# Basic configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)


@celery_app.task(name="sentinel.health_check")
def health_check_task():
    """Simple health check task to verify Celery is working."""
    return {"status": "healthy", "service": "celery-worker"}
