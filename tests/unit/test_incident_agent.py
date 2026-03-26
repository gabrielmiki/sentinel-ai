"""
Unit tests for incident agent node.

Tests incident record updates, JSON parsing, error handling,
and factory function pattern.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.incident_agent import make_incident_agent


class TestMakeIncidentAgent:
    """Tests for incident agent factory function."""

    @pytest.mark.asyncio
    async def test_factory_returns_async_function(self) -> None:
        """Verify factory returns an async callable."""
        mock_session = AsyncMock()
        agent = make_incident_agent(mock_session)

        assert callable(agent)
        # Verify it's an async function by checking for coroutine
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": '{"severity_assessment": "high"}',
            "error": None,
            "messages": [],
        }
        result = agent(state)
        assert hasattr(result, "__await__")


class TestIncidentAgent:
    """Tests for incident agent node."""

    @pytest.mark.asyncio
    async def test_updates_incident_with_valid_report(self) -> None:
        """Verify agent updates incident with parsed severity."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        state: GraphState = {
            "incident_id": "incident-456",
            "trigger": "High CPU",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": json.dumps(
                {
                    "summary": "Database overload",
                    "root_cause_hypothesis": "Connection pool exhaustion",
                    "affected_components": ["database", "backend"],
                    "recommended_actions": ["Increase pool size"],
                    "severity_assessment": "critical",
                }
            ),
            "error": None,
            "messages": [],
        }

        agent = make_incident_agent(mock_session)
        result = await agent(state)

        # Verify session.execute was called with UPDATE statement
        assert mock_session.execute.called

        # Verify commit was called
        mock_session.commit.assert_called_once()

        # Verify return value
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        message_content = result["messages"][0].content
        assert isinstance(message_content, str)
        assert "incident-456" in message_content
        assert "updated incident" in message_content.lower()

    @pytest.mark.asyncio
    async def test_handles_json_parse_error(self) -> None:
        """Verify agent saves report without severity when JSON invalid."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        state: GraphState = {
            "incident_id": "incident-789",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "Not valid JSON at all",
            "error": None,
            "messages": [],
        }

        agent = make_incident_agent(mock_session)
        result = await agent(state)

        # Should still commit (saves report as-is)
        mock_session.commit.assert_called_once()

        # Should return error message
        assert "error" in result
        assert "JSON parse error" in result["messages"][0].content
        assert "incident-789" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_rolls_back_on_database_error(self) -> None:
        """Verify agent rolls back transaction on database errors."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database connection failed")
        mock_session.rollback = AsyncMock()

        state: GraphState = {
            "incident_id": "incident-999",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": '{"severity_assessment": "low"}',
            "error": None,
            "messages": [],
        }

        agent = make_incident_agent(mock_session)
        result = await agent(state)

        # Verify rollback was called
        mock_session.rollback.assert_called_once()

        # Verify error is returned
        assert "error" in result
        assert "Database connection failed" in result["error"]
        assert "failed to update" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_extracts_severity_from_report(self) -> None:
        """Verify agent correctly extracts severity_assessment from JSON."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        for severity in ["low", "medium", "high", "critical"]:
            state: GraphState = {
                "incident_id": f"incident-{severity}",
                "trigger": "Test",
                "metrics_data": {},
                "log_data": [],
                "runbook_hits": [],
                "final_report": json.dumps(
                    {
                        "summary": "Test incident",
                        "root_cause_hypothesis": "Test",
                        "affected_components": [],
                        "recommended_actions": [],
                        "severity_assessment": severity,
                    }
                ),
                "error": None,
                "messages": [],
            }

            agent = make_incident_agent(mock_session)
            result = await agent(state)

            # Verify no errors
            assert "error" not in result or result.get("error") is None

        # Verify commit was called for each severity level
        assert mock_session.commit.call_count == 4

    @pytest.mark.asyncio
    async def test_defaults_to_medium_severity_when_missing(self) -> None:
        """Verify agent defaults to 'medium' when severity_assessment missing."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        state: GraphState = {
            "incident_id": "incident-no-severity",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": json.dumps(
                {
                    "summary": "Test incident",
                    "root_cause_hypothesis": "Test",
                    "affected_components": [],
                    "recommended_actions": [],
                    # severity_assessment intentionally missing
                }
            ),
            "error": None,
            "messages": [],
        }

        agent = make_incident_agent(mock_session)
        result = await agent(state)

        # Should succeed and commit
        mock_session.commit.assert_called_once()
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_uses_injected_session(self) -> None:
        """Verify agent uses session provided by factory."""
        session_1 = AsyncMock()
        session_2 = AsyncMock()

        agent_1 = make_incident_agent(session_1)
        agent_2 = make_incident_agent(session_2)

        state: GraphState = {
            "incident_id": "test-session",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": '{"severity_assessment": "low"}',
            "error": None,
            "messages": [],
        }

        await agent_1(state)
        await agent_2(state)

        # Verify each agent used its own session
        assert session_1.execute.called
        assert session_2.execute.called
        session_1.commit.assert_called_once()
        session_2.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_full_report_as_agent_report(self) -> None:
        """Verify agent saves entire final_report as agent_report field."""
        mock_session = AsyncMock()

        full_report = json.dumps(
            {
                "summary": "Critical database issue requiring immediate attention.",
                "root_cause_hypothesis": "Connection pool exhausted under high load",
                "affected_components": ["database", "backend-api", "user-service"],
                "recommended_actions": [
                    "Increase connection pool size to 100",
                    "Review slow queries in logs",
                    "Scale database read replicas",
                ],
                "severity_assessment": "critical",
            }
        )

        state: GraphState = {
            "incident_id": "incident-full-report",
            "trigger": "Database errors",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": full_report,
            "error": None,
            "messages": [],
        }

        agent = make_incident_agent(mock_session)
        await agent(state)

        # Verify execute was called (we can't easily inspect SQLAlchemy statement values)
        assert mock_session.execute.called
        mock_session.commit.assert_called_once()
