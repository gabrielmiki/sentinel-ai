"""
Agents execution router.

Manages LangGraph agent runs: triggering, monitoring, streaming, and cancellation.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from api.database import get_db

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


# ==================== Pydantic Schemas ====================


class AgentRunCreate(BaseModel):
    """Schema for triggering agent run."""

    incident_id: str


class AgentRunResponse(BaseModel):
    """Schema for agent run status."""

    id: str
    incident_id: str | None
    status: str
    current_node: str | None
    completed_nodes: list[str] | None
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None

    model_config = {"from_attributes": True}


class AgentStreamEvent(BaseModel):
    """Schema for SSE stream events."""

    event_type: str  # node_start, node_complete, final_report
    timestamp: str
    node_name: str | None = None
    node_output: dict[str, Any] | None = None
    final_report: str | None = None


# ==================== Helper Functions ====================


async def get_run_or_404(run_id: str, db: AsyncSession) -> Any:
    """
    Fetch agent run by ID or raise 404.

    Args:
        run_id: Agent run ID
        db: Database session

    Returns:
        Agent run record

    Raises:
        HTTPException: If run not found
    """
    from api.models.agent_run import AgentRun

    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )

    return run


async def stream_agent_events(
    run_id: str, db: AsyncSession
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream agent execution events via Server-Sent Events.

    Polls the agent_runs table for state changes and yields events.

    Args:
        run_id: Agent run ID to stream
        db: Database session

    Yields:
        SSE events (node_start, node_complete, final_report)
    """
    from api.models.agent_run import AgentRun

    last_node: str | None = None
    completed_nodes_count = 0

    while True:
        # Fetch current run state
        query = select(AgentRun).where(AgentRun.id == run_id)
        result = await db.execute(query)
        run = result.scalar_one_or_none()

        if not run:
            yield {
                "event": "error",
                "data": {
                    "event_type": "error",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": "Run not found",
                },
            }
            break

        # Check if new node started
        if run.current_node and run.current_node != last_node:
            yield {
                "event": "node_start",
                "data": {
                    "event_type": "node_start",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "node_name": run.current_node,
                },
            }
            last_node = run.current_node

        # Check if nodes completed
        if run.completed_nodes and len(run.completed_nodes) > completed_nodes_count:
            new_nodes = run.completed_nodes[completed_nodes_count:]
            for node in new_nodes:
                yield {
                    "event": "node_complete",
                    "data": {
                        "event_type": "node_complete",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "node_name": node,
                        "node_output": run.output_data or {},
                    },
                }
            completed_nodes_count = len(run.completed_nodes)

        # Check if run completed
        if run.status in ["completed", "failed", "cancelled"]:
            if run.status == "completed" and run.output_data:
                yield {
                    "event": "final_report",
                    "data": {
                        "event_type": "final_report",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "final_report": run.output_data.get("final_report", ""),
                    },
                }

            yield {
                "event": "done",
                "data": {
                    "event_type": "done",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": run.status,
                },
            }
            break

        # Poll interval
        await asyncio.sleep(0.5)


# ==================== Endpoints ====================


@router.post(
    "/run/{incident_id}",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger agent run",
)
async def trigger_agent_run(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Manually trigger LangGraph execution for an incident.

    Creates an agent run record and enqueues the Celery task.

    Args:
        incident_id: Incident to analyze
        db: Database session

    Returns:
        Agent run ID and initial status
    """
    from api.models.incident import Incident

    # Verify incident exists
    query = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    # Create agent run
    run_id = str(uuid4())
    create_query = text(
        """
        INSERT INTO sentinel.agent_runs
        (id, incident_id, status, input_data, current_node, completed_nodes)
        VALUES (:id, :incident_id, 'pending', :input_data, NULL, '[]'::jsonb)
        RETURNING id, incident_id, status, current_node, completed_nodes,
                  input_data, output_data, error_message,
                  started_at, completed_at, duration_ms
        """
    )

    input_data = {
        "incident_id": incident_id,
        "incident_title": incident.title,
        "incident_description": incident.description,
        "severity": incident.severity,
    }

    result = await db.execute(
        create_query,
        {
            "id": run_id,
            "incident_id": incident_id,
            "input_data": json.dumps(input_data),
        },
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create agent run",
        )

    # TODO
    # Enqueue Celery task (placeholder - actual implementation in tasks module)
    # from api.tasks.celery_app import celery_app
    # celery_app.send_task("agents.execute_graph", args=[incident_id, run_id])

    return row._asdict()


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunResponse,
    summary="Get agent run status",
)
async def get_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get current state of agent run.

    Returns active node, completed nodes, and partial outputs.

    Args:
        run_id: Agent run ID
        db: Database session

    Returns:
        Current agent run state
    """
    run = await get_run_or_404(run_id, db)
    return run


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream agent execution",
    response_class=EventSourceResponse,
)
async def stream_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """
    Stream agent execution events via Server-Sent Events.

    Yields real-time events as the graph progresses:
    - node_start: When a new node begins execution
    - node_complete: When a node finishes with output
    - final_report: When the entire graph completes
    - done: Stream termination

    Args:
        run_id: Agent run ID
        db: Database session

    Returns:
        SSE event stream
    """
    # Verify run exists first
    await get_run_or_404(run_id, db)

    return EventSourceResponse(stream_agent_events(run_id, db))


@router.post(
    "/runs/{run_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel agent run",
)
async def cancel_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Cancel an in-progress agent run.

    Interrupts execution at the next LangGraph checkpoint.

    Args:
        run_id: Agent run ID
        db: Database session
    """
    from api.models.agent_run import AgentRun

    # Update run status to cancelled
    query = (
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .where(AgentRun.status.in_(["pending", "running"]))
        .values(
            status="cancelled",
            completed_at=datetime.now(),
        )
    )

    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found or already completed",
        )

    # TODO
    # Signal Celery task to cancel (placeholder - actual implementation in tasks)
    # from api.tasks.celery_app import celery_app
    # celery_app.control.revoke(run_id, terminate=True, signal='SIGKILL')
