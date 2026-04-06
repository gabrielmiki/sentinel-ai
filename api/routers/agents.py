"""
Agents execution router.

Manages LangGraph agent runs: triggering, monitoring, streaming, and cancellation.
"""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

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


def _format_sse(event_type: str, data: dict[str, Any]) -> str:
    """Format data as Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def stream_agent_events(run_id: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    """
    Stream agent execution events via Server-Sent Events.

    Streams real-time LangGraph execution events from astream_events().

    Args:
        run_id: Agent run ID to stream
        db: Database session

    Yields:
        SSE-formatted event strings
    """
    from api.agents.graph import GraphState, build_graph
    from api.models.agent_run import AgentRun

    try:
        # Look up run to get incident_id and thread_id
        query = select(AgentRun).where(AgentRun.id == run_id)
        result = await db.execute(query)
        run = result.scalar_one_or_none()

        if not run:
            yield _format_sse(
                "error",
                {
                    "event_type": "error",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": "Run not found",
                },
            )
            return

        if not run.thread_id:
            yield _format_sse(
                "error",
                {
                    "event_type": "error",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": "Run has no thread_id",
                },
            )
            return

        # Build initial state from run's input_data
        if not run.input_data:
            yield _format_sse(
                "error",
                {
                    "event_type": "error",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": "Run has no input_data",
                },
            )
            return

        initial_state: GraphState = {
            "incident_id": run.input_data.get("incident_id", ""),
            "trigger": run.input_data.get("trigger", ""),
            "metrics_data": run.input_data.get("metrics_data", {}),
            "log_data": run.input_data.get("log_data", []),
            "runbook_hits": run.input_data.get("runbook_hits", []),
            "final_report": run.input_data.get("final_report", ""),
            "error": run.input_data.get("error"),
            "messages": run.input_data.get("messages", []),
        }

        # Build graph with database session
        graph = await build_graph(db)

        # Stream events from LangGraph
        config = {"configurable": {"thread_id": run.thread_id}}

        async for event in graph.astream_events(initial_state, config, version="v2"):
            event_type = event.get("event")

            # Filter to relevant event types
            if event_type in ["on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end"]:
                # Build filtered event payload
                filtered_event = {"event": event_type, "name": event.get("name", ""), "data": {}}

                # Include input or output data
                event_data = event.get("data", {})
                if "input" in event_data:
                    filtered_event["data"]["input"] = event_data["input"]
                if "output" in event_data:
                    filtered_event["data"]["output"] = event_data["output"]

                yield _format_sse(event_type, filtered_event)

            # Check for graph completion (on_chain_end for the full graph)
            if event_type == "on_chain_end" and event.get("name") == "LangGraph":
                output = event.get("data", {}).get("output", {})
                final_report = output.get("final_report", "")

                if final_report:
                    yield _format_sse(
                        "complete",
                        {
                            "event_type": "complete",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "final_report": final_report,
                        },
                    )

    except Exception as e:
        yield _format_sse(
            "error",
            {
                "event_type": "error",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            },
        )


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
    thread_id = f"incident-{incident_id}-run-{run_id}"

    create_query = text(
        """
        INSERT INTO sentinel.agent_runs
        (id, incident_id, thread_id, status, input_data, current_node, completed_nodes)
        VALUES (:id, :incident_id, :thread_id, 'pending', :input_data, NULL, '[]'::jsonb)
        RETURNING id, incident_id, thread_id, status, current_node, completed_nodes,
                  input_data, output_data, error_message,
                  started_at, completed_at, duration_ms
        """
    )

    input_data: dict[str, Any] = {
        "incident_id": incident_id,
        "trigger": f"{incident.title}: {incident.description or ''}",
        "metrics_data": {},
        "log_data": [],
        "runbook_hits": [],
        "final_report": "",
        "error": None,
        "messages": [],
    }

    result = await db.execute(
        create_query,
        {
            "id": run_id,
            "incident_id": incident_id,
            "thread_id": thread_id,
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
)
async def stream_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Stream agent execution events via Server-Sent Events.

    Yields real-time LangGraph events as the graph executes:
    - on_chain_start: When a node/chain begins execution
    - on_chain_end: When a node/chain completes
    - on_tool_start: When a tool is invoked
    - on_tool_end: When a tool completes
    - complete: When the entire graph finishes with final report
    - error: On any exception

    Args:
        run_id: Agent run ID
        db: Database session

    Returns:
        SSE event stream with Cache-Control and X-Accel-Buffering headers
    """
    from fastapi.responses import StreamingResponse

    # Verify run exists first
    await get_run_or_404(run_id, db)

    return StreamingResponse(
        stream_agent_events(run_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
