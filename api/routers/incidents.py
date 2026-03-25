"""
Incidents management router.

Handles incident lifecycle: creation, updates, listing, and Alertmanager webhook ingestion.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


# ==================== Pydantic Schemas ====================


class IncidentCreate(BaseModel):
    """Schema for creating a new incident."""

    title: str = Field(..., min_length=1, max_length=500)
    severity: Literal["low", "medium", "high", "critical"]
    description: str | None = None
    affected_service: str | None = Field(None, max_length=200)


class IncidentUpdate(BaseModel):
    """Schema for updating an incident (status, resolution, assignee only)."""

    status: str | None = Field(None, max_length=50)
    resolution_notes: str | None = None
    assignee: str | None = None  # User ID
    affected_service: str | None = Field(None, max_length=200)


class IncidentResponse(BaseModel):
    """Schema for incident response."""

    id: str
    title: str
    description: str | None
    severity: str
    status: str
    affected_service: str | None
    assignee: str | None
    resolution_notes: str | None
    agent_report: str | None
    archived: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class PaginatedIncidentsResponse(BaseModel):
    """Schema for paginated incident listing."""

    incidents: list[IncidentResponse]
    next_cursor: str | None
    has_more: bool
    total: int


class AlertmanagerAlert(BaseModel):
    """Schema for a single Alertmanager alert."""

    status: str
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: str = Field(..., alias="startsAt")
    ends_at: str | None = Field(None, alias="endsAt")
    generator_url: str | None = Field(None, alias="generatorURL")

    model_config = {"populate_by_name": True}


class AlertmanagerWebhook(BaseModel):
    """Schema for Alertmanager webhook payload."""

    version: str
    group_key: str = Field(..., alias="groupKey")
    status: str
    receiver: str
    group_labels: dict[str, str] = Field(..., alias="groupLabels")
    common_labels: dict[str, str] = Field(..., alias="commonLabels")
    common_annotations: dict[str, str] = Field(..., alias="commonAnnotations")
    external_url: str = Field(..., alias="externalURL")
    alerts: list[AlertmanagerAlert]

    model_config = {"populate_by_name": True}


class AutoTriggerResponse(BaseModel):
    """Schema for auto-trigger response."""

    created_incidents: list[str]
    queued_runs: list[str]
    message: str


# ==================== Helper Functions ====================


async def trigger_agent_run(incident_id: str) -> str:
    """
    Enqueue LangGraph execution for an incident.

    Args:
        incident_id: The incident to analyze

    Returns:
        run_id: The agent run ID

    Note: This is a placeholder. Actual implementation will use Celery tasks.
    """

    # Placeholder - actual Celery task will be implemented in agents router
    run_id = str(uuid4())
    # TODO
    # celery_app.send_task("agents.execute_graph", args=[incident_id, run_id])
    return run_id


# ==================== Endpoints ====================


@router.post(
    "/",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create incident",
)
async def create_incident(
    incident: IncidentCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Create a new incident.

    Args:
        incident: Incident creation payload
        db: Database session

    Returns:
        Created incident with generated ID
    """
    incident_id = str(uuid4())
    query = text(
        """
        INSERT INTO sentinel.incidents
        (id, title, description, severity, status, affected_service)
        VALUES (:id, :title, :description, :severity, 'open', :affected_service)
        RETURNING id, title, description, severity, status, affected_service,
                  assignee, resolution_notes, agent_report, archived,
                  created_by, created_at, updated_at, resolved_at
        """
    )

    result = await db.execute(
        query,
        {
            "id": incident_id,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "affected_service": incident.affected_service,
        },
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create incident",
        )

    return row._asdict()


@router.get(
    "/",
    response_model=PaginatedIncidentsResponse,
    summary="List incidents",
)
async def list_incidents(
    cursor: str | None = Query(None, description="Pagination cursor (base64 encoded)"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    status_filter: str | None = Query(None, description="Filter by status"),
    severity_filter: str | None = Query(None, description="Filter by severity"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List incidents with cursor-based pagination and optional filters.

    Args:
        cursor: Pagination cursor (base64 encoded timestamp and ID)
        limit: Number of incidents per page
        status_filter: Filter by status (e.g., 'open', 'resolved')
        severity_filter: Filter by severity (e.g., 'critical', 'high')
        db: Database session

    Returns:
        Paginated incident list with next cursor
    """
    import base64
    import json

    from api.models.incident import Incident

    # Build query with filters
    query = select(Incident).where(Incident.archived == False)  # noqa: E712

    if status_filter:
        query = query.where(Incident.status == status_filter)

    if severity_filter:
        query = query.where(Incident.severity == severity_filter)

    # Apply cursor pagination
    if cursor:
        try:
            cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
            cursor_created_at = cursor_data["created_at"]
            cursor_id = cursor_data["id"]
            # For descending order: next page has (created_at < cursor) OR (created_at = cursor AND id > cursor_id)
            query = query.where(
                (Incident.created_at < cursor_created_at)
                | ((Incident.created_at == cursor_created_at) & (Incident.id > cursor_id))
            )
        except Exception:
            # Invalid cursor, ignore it
            pass

    query = query.order_by(Incident.created_at.desc(), Incident.id.asc()).limit(limit + 1)

    result = await db.execute(query)
    incidents = result.scalars().all()

    # Check if there are more results
    has_more = len(incidents) > limit
    if has_more:
        incidents = incidents[:limit]

    # Generate next cursor from last incident (created_at + id for stable pagination)
    next_cursor = None
    if has_more and incidents:
        import base64
        import json

        last_incident = incidents[-1]
        cursor_data = {
            "created_at": last_incident.created_at.isoformat(),
            "id": last_incident.id,
        }
        next_cursor = base64.b64encode(json.dumps(cursor_data).encode("utf-8")).decode("utf-8")

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.archived == False  # noqa: E712
        )
    )
    if status_filter:
        count_query = count_query.where(Incident.status == status_filter)
    if severity_filter:
        count_query = count_query.where(Incident.severity == severity_filter)

    total = await db.scalar(count_query) or 0

    return {
        "incidents": incidents,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
    }


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Get incident",
)
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get incident by ID.

    Args:
        incident_id: Incident ID
        db: Database session

    Returns:
        Full incident detail including agent report
    """
    from api.models.incident import Incident

    query = select(Incident).where(
        and_(Incident.id == incident_id, Incident.archived == False)  # noqa: E712
    )
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident


@router.patch(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Update incident",
)
async def update_incident(
    incident_id: str,
    incident_update: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Update incident metadata.

    Agent report is immutable and cannot be updated via this endpoint.

    Args:
        incident_id: Incident ID
        incident_update: Fields to update
        db: Database session

    Returns:
        Updated incident
    """
    from api.models.incident import Incident

    # Build update dict excluding None values
    update_data = incident_update.model_dump(exclude_unset=True, exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    query = (
        update(Incident)
        .where(and_(Incident.id == incident_id, Incident.archived == False))  # noqa: E712
        .values(**update_data)
        .returning(Incident)
    )

    result = await db.execute(query)
    await db.commit()

    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident


@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete incident",
)
async def delete_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft delete an incident by setting archived flag.

    Args:
        incident_id: Incident ID
        db: Database session
    """
    from api.models.incident import Incident

    query = (
        update(Incident)
        .where(and_(Incident.id == incident_id, Incident.archived == False))  # noqa: E712
        .values(archived=True)
    )

    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )


@router.post(
    "/auto-trigger",
    response_model=AutoTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Alertmanager webhook",
)
async def auto_trigger_from_alertmanager(
    webhook: AlertmanagerWebhook,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Receive Alertmanager webhook and auto-create incidents.

    Creates one incident per active alert, enqueues LangGraph execution
    as a background task, and returns immediately with created IDs.

    Args:
        webhook: Alertmanager webhook payload
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        Created incident IDs and queued run IDs
    """
    created_incidents: list[str] = []
    queued_runs: list[str] = []

    # Only process firing alerts
    active_alerts = [alert for alert in webhook.alerts if alert.status == "firing"]

    for alert in active_alerts:
        incident_id = str(uuid4())

        # Extract title and description from alert
        title = alert.labels.get("alertname", "Unknown Alert")
        description = alert.annotations.get("description") or alert.annotations.get(
            "summary", "No description available"
        )
        severity = alert.labels.get("severity", "medium").lower()
        affected_service = alert.labels.get("service") or alert.labels.get("job")

        # Normalize severity
        if severity not in ["low", "medium", "high", "critical"]:
            severity = "medium"

        # Create incident
        query = text(
            """
            INSERT INTO sentinel.incidents
            (id, title, description, severity, status, affected_service)
            VALUES (:id, :title, :description, :severity, 'open', :affected_service)
            RETURNING id
            """
        )

        await db.execute(
            query,
            {
                "id": incident_id,
                "title": title,
                "description": description,
                "severity": severity,
                "affected_service": affected_service,
            },
        )
        await db.commit()

        created_incidents.append(incident_id)

        # Enqueue agent run as background task
        run_id = await trigger_agent_run(incident_id)
        queued_runs.append(run_id)

    return {
        "created_incidents": created_incidents,
        "queued_runs": queued_runs,
        "message": f"Created {len(created_incidents)} incidents from {len(active_alerts)} firing alerts",
    }
