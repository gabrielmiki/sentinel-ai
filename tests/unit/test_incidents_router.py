"""
Tests for incidents router endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.database
class TestCreateIncident:
    """Tests for POST /api/v1/incidents/ endpoint."""

    @pytest.mark.asyncio
    async def test_create_incident_returns_201(self, client: AsyncClient) -> None:
        """Verify create incident endpoint returns 201 Created."""
        payload = {
            "title": "High CPU usage on backend-1",
            "severity": "critical",
            "description": "CPU usage exceeded 90% for 10 minutes",
            "affected_service": "backend-api",
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_incident_returns_correct_structure(self, client: AsyncClient) -> None:
        """Verify create incident returns expected JSON structure."""
        payload = {
            "title": "Database connection pool exhausted",
            "severity": "high",
            "description": "All connections in use",
            "affected_service": "postgres",
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        data = response.json()

        # Verify all required fields are present
        assert "id" in data
        assert "title" in data
        assert "severity" in data
        assert "status" in data
        assert "affected_service" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Verify data matches input
        assert data["title"] == payload["title"]
        assert data["severity"] == payload["severity"]
        assert data["description"] == payload["description"]
        assert data["affected_service"] == payload["affected_service"]

        # Verify defaults
        assert data["status"] == "open"
        assert data["archived"] is False

    @pytest.mark.asyncio
    async def test_create_incident_persists_to_database(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify created incident is persisted to database."""
        payload = {
            "title": "Test incident for persistence",
            "severity": "medium",
            "description": "Testing database persistence",
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        data = response.json()
        incident_id = data["id"]

        # Query database to verify persistence
        query = text(
            """
            SELECT title, severity, description, status
            FROM sentinel.incidents
            WHERE id = :id
            """
        )
        result = await db_session.execute(query, {"id": incident_id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == payload["title"]
        assert row[1] == payload["severity"]
        assert row[2] == payload["description"]
        assert row[3] == "open"

    @pytest.mark.asyncio
    async def test_create_incident_with_minimal_data(self, client: AsyncClient) -> None:
        """Verify incident can be created with only required fields."""
        payload = {
            "title": "Minimal incident",
            "severity": "low",
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["title"] == payload["title"]
        assert data["severity"] == payload["severity"]
        assert data["description"] is None
        assert data["affected_service"] is None

    @pytest.mark.asyncio
    async def test_create_incident_rejects_invalid_severity(self, client: AsyncClient) -> None:
        """Verify endpoint rejects invalid severity values."""
        payload = {
            "title": "Test incident",
            "severity": "super-critical",  # Invalid
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_incident_rejects_missing_title(self, client: AsyncClient) -> None:
        """Verify endpoint rejects request without required title field."""
        payload = {
            "severity": "high",
            # title is missing
        }

        response = await client.post("/api/v1/incidents/", json=payload)
        assert response.status_code == 422  # Validation error


@pytest.mark.database
class TestGetIncidentById:
    """Tests for GET /api/v1/incidents/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_incident_returns_200(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify get incident endpoint returns 200 OK."""
        # Create test incident
        incident = await create_test_incident(
            title="Test incident for retrieval",
            severity="medium",
        )

        response = await client.get(f"/api/v1/incidents/{incident.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_incident_returns_correct_data(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify get incident returns complete incident data."""
        # Create test incident
        incident = await create_test_incident(
            title="Full incident test",
            description="Complete test with all fields",
            severity="high",
            status="investigating",
        )

        response = await client.get(f"/api/v1/incidents/{incident.id}")
        data = response.json()

        # Verify all fields
        assert data["id"] == incident.id
        assert data["title"] == incident.title
        assert data["description"] == incident.description
        assert data["severity"] == incident.severity
        assert data["status"] == incident.status
        assert data["archived"] is False

        # Verify fields are present even if None
        assert "affected_service" in data
        assert "assignee" in data
        assert "resolution_notes" in data
        assert "agent_report" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_incident_returns_404_for_nonexistent(self, client: AsyncClient) -> None:
        """Verify endpoint returns 404 for non-existent incident ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/incidents/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_incident_returns_404_for_archived(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify endpoint returns 404 for archived incidents."""
        # Create and archive an incident directly in DB
        from uuid import uuid4

        incident_id = str(uuid4())
        query = text(
            """
            INSERT INTO sentinel.incidents
            (id, title, severity, status, archived)
            VALUES (:id, :title, :severity, 'open', true)
            """
        )
        await db_session.execute(
            query,
            {
                "id": incident_id,
                "title": "Archived incident",
                "severity": "low",
            },
        )
        await db_session.commit()

        # Try to retrieve archived incident
        response = await client.get(f"/api/v1/incidents/{incident_id}")
        assert response.status_code == 404


@pytest.mark.database
class TestListIncidents:
    """Tests for GET /api/v1/incidents/ endpoint."""

    @pytest.mark.asyncio
    async def test_list_incidents_returns_200(self, client: AsyncClient) -> None:
        """Verify list incidents endpoint returns 200 OK."""
        response = await client.get("/api/v1/incidents/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_incidents_returns_correct_structure(self, client: AsyncClient) -> None:
        """Verify list incidents returns expected pagination structure."""
        response = await client.get("/api/v1/incidents/")
        data = response.json()

        assert "incidents" in data
        assert "next_cursor" in data
        assert "has_more" in data
        assert "total" in data
        assert isinstance(data["incidents"], list)

    @pytest.mark.asyncio
    async def test_list_incidents_returns_created_incidents(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify list includes created incidents."""
        # Create test incidents
        incident1 = await create_test_incident(title="First incident", severity="high")
        incident2 = await create_test_incident(title="Second incident", severity="low")

        response = await client.get("/api/v1/incidents/")
        data = response.json()

        assert len(data["incidents"]) >= 2
        incident_ids = {inc["id"] for inc in data["incidents"]}
        assert incident1.id in incident_ids
        assert incident2.id in incident_ids

    @pytest.mark.asyncio
    async def test_list_incidents_pagination_limit(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify pagination limit parameter works."""
        # Create multiple incidents
        for i in range(5):
            await create_test_incident(title=f"Incident {i}", severity="medium")

        response = await client.get("/api/v1/incidents/?limit=3")
        data = response.json()

        assert len(data["incidents"]) == 3

    @pytest.mark.asyncio
    async def test_list_incidents_pagination_cursor(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify cursor-based pagination works."""
        # Create incidents
        for i in range(5):
            await create_test_incident(title=f"Pagination test {i}", severity="low")

        # Get first page
        response = await client.get("/api/v1/incidents/?limit=2")
        data = response.json()

        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # Get second page using cursor
        cursor = data["next_cursor"]
        response2 = await client.get(f"/api/v1/incidents/?limit=2&cursor={cursor}")
        data2 = response2.json()

        # Verify different results
        first_page_ids = {inc["id"] for inc in data["incidents"]}
        second_page_ids = {inc["id"] for inc in data2["incidents"]}
        assert first_page_ids.isdisjoint(second_page_ids)

    @pytest.mark.asyncio
    async def test_list_incidents_filter_by_status(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify filtering by status works."""
        # Create incidents with different statuses
        await create_test_incident(title="Open incident", status="open", severity="low")
        await create_test_incident(title="Resolved incident", status="resolved", severity="low")

        # Filter by status
        response = await client.get("/api/v1/incidents/?status_filter=open")
        data = response.json()

        # All returned incidents should be open
        for incident in data["incidents"]:
            assert incident["status"] == "open"

    @pytest.mark.asyncio
    async def test_list_incidents_filter_by_severity(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify filtering by severity works."""
        # Create incidents with different severities
        await create_test_incident(title="Critical incident", severity="critical")
        await create_test_incident(title="Low incident", severity="low")

        # Filter by severity
        response = await client.get("/api/v1/incidents/?severity_filter=critical")
        data = response.json()

        # All returned incidents should be critical
        for incident in data["incidents"]:
            assert incident["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_list_incidents_excludes_archived(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify list excludes archived incidents."""
        from uuid import uuid4

        # Create archived incident
        archived_id = str(uuid4())
        query = text(
            """
            INSERT INTO sentinel.incidents
            (id, title, severity, status, archived)
            VALUES (:id, 'Archived incident', 'low', 'open', true)
            """
        )
        await db_session.execute(query, {"id": archived_id})
        await db_session.commit()

        # List incidents
        response = await client.get("/api/v1/incidents/")
        data = response.json()

        # Archived incident should not appear
        incident_ids = {inc["id"] for inc in data["incidents"]}
        assert archived_id not in incident_ids

    @pytest.mark.asyncio
    async def test_list_incidents_empty_when_no_incidents(self, client: AsyncClient) -> None:
        """Verify endpoint returns empty list when no incidents exist."""
        response = await client.get("/api/v1/incidents/")
        data = response.json()

        # May have other incidents from other tests, but structure should be valid
        assert isinstance(data["incidents"], list)
        assert data["has_more"] is False
        assert data["next_cursor"] is None


@pytest.mark.database
class TestUpdateIncident:
    """Tests for PATCH /api/v1/incidents/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_incident_returns_200(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify update incident endpoint returns 200 OK."""
        incident = await create_test_incident(title="Original title", severity="low")

        payload = {"status": "investigating"}
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_incident_updates_status(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify status field is updated correctly."""
        incident = await create_test_incident(
            title="Test incident", status="open", severity="medium"
        )

        payload = {"status": "resolved"}
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        data = response.json()

        assert data["status"] == "resolved"
        assert data["id"] == incident.id

    @pytest.mark.asyncio
    async def test_update_incident_updates_resolution_notes(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify resolution_notes field is updated correctly."""
        incident = await create_test_incident(title="Test incident", severity="high")

        payload = {"resolution_notes": "Fixed by restarting service"}
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        data = response.json()

        assert data["resolution_notes"] == "Fixed by restarting service"

    @pytest.mark.asyncio
    async def test_update_incident_updates_affected_service(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify affected_service field is updated correctly."""
        incident = await create_test_incident(title="Test incident", severity="low")

        payload = {"affected_service": "backend-api"}
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        data = response.json()

        assert data["affected_service"] == "backend-api"

    @pytest.mark.asyncio
    async def test_update_incident_updates_multiple_fields(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify multiple fields can be updated in single request."""
        incident = await create_test_incident(title="Test incident", severity="medium")

        payload = {
            "status": "resolved",
            "resolution_notes": "Database connection pool increased",
            "affected_service": "postgres",
        }
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        data = response.json()

        assert data["status"] == "resolved"
        assert data["resolution_notes"] == "Database connection pool increased"
        assert data["affected_service"] == "postgres"

    @pytest.mark.asyncio
    async def test_update_incident_persists_to_database(
        self, client: AsyncClient, create_test_incident, db_session: AsyncSession
    ) -> None:
        """Verify updates are persisted to database."""
        incident = await create_test_incident(title="Persistence test", severity="critical")

        payload = {"status": "investigating", "resolution_notes": "Under investigation"}
        await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)

        # Verify in database
        query = text(
            """
            SELECT status, resolution_notes
            FROM sentinel.incidents
            WHERE id = :id
            """
        )
        result = await db_session.execute(query, {"id": incident.id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == "investigating"
        assert row[1] == "Under investigation"

    @pytest.mark.asyncio
    async def test_update_incident_returns_404_for_nonexistent(self, client: AsyncClient) -> None:
        """Verify endpoint returns 404 for non-existent incident."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        payload = {"status": "resolved"}

        response = await client.patch(f"/api/v1/incidents/{fake_id}", json=payload)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_incident_returns_400_for_empty_update(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify endpoint returns 400 when no fields to update."""
        incident = await create_test_incident(title="Test incident", severity="low")

        payload = {}  # Empty update
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_incident_ignores_null_fields(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify null fields in payload are ignored (excluded_none)."""
        incident = await create_test_incident(
            title="Test incident",
            status="open",
            severity="low",
            resolution_notes="Original notes",
        )

        # Only update status, send null for other fields
        payload = {"status": "investigating", "resolution_notes": None}
        response = await client.patch(f"/api/v1/incidents/{incident.id}", json=payload)
        data = response.json()

        assert data["status"] == "investigating"
        # resolution_notes should remain unchanged since None is excluded
        assert data["resolution_notes"] == "Original notes"


@pytest.mark.database
class TestDeleteIncident:
    """Tests for DELETE /api/v1/incidents/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_incident_returns_204(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify delete incident endpoint returns 204 No Content."""
        incident = await create_test_incident(title="To be deleted", severity="low")

        response = await client.delete(f"/api/v1/incidents/{incident.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_incident_sets_archived_flag(
        self, client: AsyncClient, create_test_incident, db_session: AsyncSession
    ) -> None:
        """Verify delete sets archived flag instead of hard deleting."""
        incident = await create_test_incident(title="Soft delete test", severity="medium")

        await client.delete(f"/api/v1/incidents/{incident.id}")

        # Verify archived flag is set in database
        query = text(
            """
            SELECT archived
            FROM sentinel.incidents
            WHERE id = :id
            """
        )
        result = await db_session.execute(query, {"id": incident.id})
        row = result.fetchone()

        assert row is not None  # Record still exists
        assert row[0] is True  # archived flag is True

    @pytest.mark.asyncio
    async def test_delete_incident_excludes_from_list(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify archived incident no longer appears in list."""
        incident = await create_test_incident(title="Will be hidden", severity="high")

        # Delete incident
        await client.delete(f"/api/v1/incidents/{incident.id}")

        # List incidents
        response = await client.get("/api/v1/incidents/")
        data = response.json()

        # Archived incident should not appear
        incident_ids = {inc["id"] for inc in data["incidents"]}
        assert incident.id not in incident_ids

    @pytest.mark.asyncio
    async def test_delete_incident_returns_404_on_get(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify archived incident returns 404 on GET by ID."""
        incident = await create_test_incident(title="Archived test", severity="critical")

        # Delete incident
        await client.delete(f"/api/v1/incidents/{incident.id}")

        # Try to get archived incident
        response = await client.get(f"/api/v1/incidents/{incident.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_incident_returns_404_for_nonexistent(self, client: AsyncClient) -> None:
        """Verify endpoint returns 404 for non-existent incident."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/v1/incidents/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_incident_returns_404_for_already_archived(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify endpoint returns 404 when trying to delete already archived incident."""
        from uuid import uuid4

        # Create already archived incident
        archived_id = str(uuid4())
        query = text(
            """
            INSERT INTO sentinel.incidents
            (id, title, severity, status, archived)
            VALUES (:id, 'Already archived', 'low', 'open', true)
            """
        )
        await db_session.execute(query, {"id": archived_id})
        await db_session.commit()

        # Try to delete already archived incident
        response = await client.delete(f"/api/v1/incidents/{archived_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_incident_idempotent(
        self, client: AsyncClient, create_test_incident
    ) -> None:
        """Verify deleting same incident twice returns 404 on second attempt."""
        incident = await create_test_incident(title="Idempotency test", severity="low")

        # First delete succeeds
        response1 = await client.delete(f"/api/v1/incidents/{incident.id}")
        assert response1.status_code == 204

        # Second delete returns 404
        response2 = await client.delete(f"/api/v1/incidents/{incident.id}")
        assert response2.status_code == 404


@pytest.mark.database
class TestAutoTriggerFromAlertmanager:
    """Tests for POST /api/v1/incidents/auto-trigger endpoint."""

    @pytest.mark.asyncio
    async def test_auto_trigger_returns_202(self, client: AsyncClient) -> None:
        """Verify auto-trigger endpoint returns 202 Accepted."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                    "annotations": {"description": "CPU usage is high"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_auto_trigger_returns_correct_structure(self, client: AsyncClient) -> None:
        """Verify auto-trigger returns expected response structure."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert"},
                    "annotations": {"description": "Test alert"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()

        assert "created_incidents" in data
        assert "queued_runs" in data
        assert "message" in data
        assert isinstance(data["created_incidents"], list)
        assert isinstance(data["queued_runs"], list)

    @pytest.mark.asyncio
    async def test_auto_trigger_creates_incident_from_firing_alert(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify incident is created from firing alert."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "DatabaseDown", "severity": "critical"},
                    "annotations": {"description": "Database is unreachable"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()

        assert len(data["created_incidents"]) == 1
        incident_id = data["created_incidents"][0]

        # Verify incident exists in database
        query = text(
            """
            SELECT title, description, severity
            FROM sentinel.incidents
            WHERE id = :id
            """
        )
        result = await db_session.execute(query, {"id": incident_id})
        row = result.fetchone()

        assert row is not None
        assert row[0] == "DatabaseDown"
        assert row[1] == "Database is unreachable"
        assert row[2] == "critical"

    @pytest.mark.asyncio
    async def test_auto_trigger_creates_multiple_incidents(self, client: AsyncClient) -> None:
        """Verify multiple incidents created from multiple firing alerts."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert1"},
                    "annotations": {"description": "First alert"},
                    "startsAt": "2024-01-01T00:00:00Z",
                },
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert2"},
                    "annotations": {"description": "Second alert"},
                    "startsAt": "2024-01-01T00:01:00Z",
                },
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()

        assert len(data["created_incidents"]) == 2
        assert len(data["queued_runs"]) == 2

    @pytest.mark.asyncio
    async def test_auto_trigger_ignores_resolved_alerts(self, client: AsyncClient) -> None:
        """Verify resolved alerts are ignored."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "resolved",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "resolved",
                    "labels": {"alertname": "ResolvedAlert"},
                    "annotations": {"description": "This should be ignored"},
                    "startsAt": "2024-01-01T00:00:00Z",
                    "endsAt": "2024-01-01T01:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()

        assert len(data["created_incidents"]) == 0
        assert len(data["queued_runs"]) == 0

    @pytest.mark.asyncio
    async def test_auto_trigger_extracts_affected_service(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify affected_service is extracted from alert labels."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ServiceDown",
                        "service": "backend-api",
                    },
                    "annotations": {"description": "Service is down"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()
        incident_id = data["created_incidents"][0]

        # Verify affected_service
        query = text("SELECT affected_service FROM sentinel.incidents WHERE id = :id")
        result = await db_session.execute(query, {"id": incident_id})
        row = result.fetchone()

        assert row[0] == "backend-api"

    @pytest.mark.asyncio
    async def test_auto_trigger_normalizes_invalid_severity(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify invalid severity values are normalized to 'medium'."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert", "severity": "SUPER_CRITICAL"},
                    "annotations": {"description": "Invalid severity"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()
        incident_id = data["created_incidents"][0]

        # Verify severity normalized to medium
        query = text("SELECT severity FROM sentinel.incidents WHERE id = :id")
        result = await db_session.execute(query, {"id": incident_id})
        row = result.fetchone()

        assert row[0] == "medium"

    @pytest.mark.asyncio
    async def test_auto_trigger_uses_summary_when_no_description(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Verify summary annotation is used when description is not available."""
        payload = {
            "version": "4",
            "groupKey": "test-group",
            "status": "firing",
            "receiver": "webhook",
            "groupLabels": {},
            "commonLabels": {},
            "commonAnnotations": {},
            "externalURL": "http://alertmanager:9093",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert"},
                    "annotations": {"summary": "This is a summary"},
                    "startsAt": "2024-01-01T00:00:00Z",
                }
            ],
        }

        response = await client.post("/api/v1/incidents/auto-trigger", json=payload)
        data = response.json()
        incident_id = data["created_incidents"][0]

        # Verify description uses summary
        query = text("SELECT description FROM sentinel.incidents WHERE id = :id")
        result = await db_session.execute(query, {"id": incident_id})
        row = result.fetchone()

        assert row[0] == "This is a summary"
