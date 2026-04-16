"""
Integration tests for Prometheus metrics.

Tests that custom metrics are properly exposed on the /metrics endpoint
after running the full LangGraph agent workflow.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.database
@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_all_custom_metrics(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that all custom Prometheus metrics are exposed after a graph run.

    Creates an incident, runs the full agent graph (with mocked LLM),
    and verifies that GET /metrics returns all four custom metric families:
    - sentinelai_agent_invocations_total
    - sentinelai_agent_duration_seconds
    - sentinelai_active_incidents
    - sentinelai_resolution_time_seconds
    """
    # Create an incident
    incident_data = {
        "title": "Test incident for metrics",
        "severity": "high",
        "description": "Testing Prometheus metrics integration",
        "affected_service": "backend",
    }

    response = await client.post("/api/v1/incidents/", json=incident_data)
    assert response.status_code == 201
    incident_id = response.json()["id"]

    # Trigger agent run (this will execute the full graph with mocked LLM)
    run_response = await client.post(f"/api/v1/agents/run/{incident_id}")
    assert run_response.status_code == 202

    # Wait for graph to complete (poll agent run status)
    import asyncio

    run_id = run_response.json()["run_id"]
    max_attempts = 30
    for _ in range(max_attempts):
        status_response = await client.get(f"/api/v1/agents/runs/{run_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        if status_data["status"] in ("completed", "failed"):
            break

        await asyncio.sleep(1)
    else:
        pytest.fail("Agent run did not complete within 30 seconds")

    # Get metrics endpoint
    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"

    metrics_text = metrics_response.text

    # Assert all four custom metric families are present
    assert "sentinelai_agent_invocations_total" in metrics_text, (
        "agent_invocations_total metric not found in /metrics"
    )

    assert "sentinelai_agent_duration_seconds" in metrics_text, (
        "agent_duration_seconds metric not found in /metrics"
    )

    assert "sentinelai_active_incidents" in metrics_text, (
        "active_incidents metric not found in /metrics"
    )

    assert "sentinelai_resolution_time_seconds" in metrics_text, (
        "resolution_time_seconds metric not found in /metrics"
    )

    # Verify agent invocation metrics for each agent
    expected_agents = [
        "metrics_agent",
        "log_agent",
        "runbook_agent",
        "synthesis_agent",
        "incident_agent",
    ]

    for agent_name in expected_agents:
        assert f'agent_name="{agent_name}"' in metrics_text, f"No metrics found for {agent_name}"

    # Verify active_incidents gauge is present
    # Should be 0 after incident is investigated (status changed from 'open' to 'investigated')
    assert (
        "sentinelai_active_incidents 0" in metrics_text
        or "sentinelai_active_incidents{" in metrics_text
    ), "active_incidents gauge value not found"

    # Verify resolution_time_seconds histogram has observations
    assert "sentinelai_resolution_time_seconds_bucket" in metrics_text, (
        "resolution_time_seconds histogram buckets not found"
    )

    assert "sentinelai_resolution_time_seconds_count" in metrics_text, (
        "resolution_time_seconds count not found"
    )

    assert "sentinelai_resolution_time_seconds_sum" in metrics_text, (
        "resolution_time_seconds sum not found"
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_active_incidents_metric_increments_and_decrements(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that active_incidents metric increments and decrements correctly.

    Verifies that creating an incident increments the gauge and updating
    the incident status to 'investigated' decrements it.
    """
    # Get baseline metrics
    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    baseline_text = metrics_response.text

    # Extract current active_incidents value (defaults to 0 if not present)
    import re

    match = re.search(r"sentinelai_active_incidents\s+(\d+)", baseline_text)
    baseline_count = int(match.group(1)) if match else 0

    # Create an incident (should increment)
    incident_data = {
        "title": "Test incident for active_incidents metric",
        "severity": "medium",
        "description": "Testing active_incidents gauge",
        "affected_service": "backend",
    }

    response = await client.post("/api/v1/incidents/", json=incident_data)
    assert response.status_code == 201
    incident_id = response.json()["id"]

    # Check metrics after creation
    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    after_create_text = metrics_response.text

    match = re.search(r"sentinelai_active_incidents\s+(\d+)", after_create_text)
    after_create_count = int(match.group(1)) if match else 0

    assert after_create_count == baseline_count + 1, (
        f"Expected active_incidents to be {baseline_count + 1}, got {after_create_count}"
    )

    # Update incident status to 'investigated' (should decrement)
    update_data = {"status": "investigated"}
    update_response = await client.patch(f"/api/v1/incidents/{incident_id}", json=update_data)
    assert update_response.status_code == 200

    # Check metrics after update
    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    after_update_text = metrics_response.text

    match = re.search(r"sentinelai_active_incidents\s+(\d+)", after_update_text)
    after_update_count = int(match.group(1)) if match else 0

    assert after_update_count == baseline_count, (
        f"Expected active_incidents to return to {baseline_count}, got {after_update_count}"
    )
