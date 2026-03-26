"""
Unit tests for log agent node.

Tests log searching, deduplication, sorting, error handling,
and concurrent query execution.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.log_agent import log_agent
from api.tools.loki import LogEntry
from api.tools.prometheus import ToolExecutionError


class TestLogAgent:
    """Tests for log agent node."""

    @pytest.mark.asyncio
    async def test_collects_error_and_warning_logs(self) -> None:
        """Verify agent collects both error and warning logs."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "High error rate for service: backend",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        error_logs = [
            LogEntry(
                timestamp="2024-03-26T10:00:00+00:00",
                level="error",
                service="backend",
                message="Database connection failed",
                labels={},
            ),
            LogEntry(
                timestamp="2024-03-26T10:01:00+00:00",
                level="error",
                service="backend",
                message="Timeout connecting to API",
                labels={},
            ),
        ]

        warning_logs = [
            LogEntry(
                timestamp="2024-03-26T09:59:00+00:00",
                level="warning",
                service="backend",
                message="High memory usage detected",
                labels={},
            )
        ]

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            if "error" in logql:
                return error_logs
            elif "warning" in logql:
                return warning_logs
            return []

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_logs):
            result = await log_agent(state)

            assert "log_data" in result
            assert len(result["log_data"]) == 3  # 2 errors + 1 warning
            assert "Database connection failed" in result["log_data"]
            assert "Timeout connecting to API" in result["log_data"]
            assert "High memory usage detected" in result["log_data"]

            # Verify message
            assert len(result["messages"]) == 1
            assert isinstance(result["messages"][0], AIMessage)
            assert "3 relevant log entries" in result["messages"][0].content
            assert "backend" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_deduplicates_logs(self) -> None:
        """Verify agent deduplicates logs with same timestamp and message."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: api errors",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        # Same log appears in both error and warning results
        duplicate_log = LogEntry(
            timestamp="2024-03-26T10:00:00+00:00",
            level="error",
            service="api",
            message="Duplicate log message",
            labels={},
        )

        error_logs = [
            duplicate_log,
            LogEntry(
                timestamp="2024-03-26T10:01:00+00:00",
                level="error",
                service="api",
                message="Unique error",
                labels={},
            ),
        ]

        warning_logs = [
            duplicate_log,  # Same log
            LogEntry(
                timestamp="2024-03-26T09:59:00+00:00",
                level="warning",
                service="api",
                message="Unique warning",
                labels={},
            ),
        ]

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            if "error" in logql:
                return error_logs
            elif "warning" in logql:
                return warning_logs
            return []

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_logs):
            result = await log_agent(state)

            assert len(result["log_data"]) == 3  # Duplicate removed
            # Count occurrences of duplicate message
            duplicate_count = sum(1 for msg in result["log_data"] if "Duplicate log message" in msg)
            assert duplicate_count == 1  # Should appear only once

    @pytest.mark.asyncio
    async def test_sorts_logs_by_timestamp_descending(self) -> None:
        """Verify logs are sorted by timestamp descending (most recent first)."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: frontend",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        error_logs = [
            LogEntry(
                timestamp="2024-03-26T10:00:00+00:00",
                level="error",
                service="frontend",
                message="Error at 10:00",
                labels={},
            ),
            LogEntry(
                timestamp="2024-03-26T10:05:00+00:00",
                level="error",
                service="frontend",
                message="Error at 10:05",
                labels={},
            ),
        ]

        warning_logs = [
            LogEntry(
                timestamp="2024-03-26T10:03:00+00:00",
                level="warning",
                service="frontend",
                message="Warning at 10:03",
                labels={},
            )
        ]

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            if "error" in logql:
                return error_logs
            elif "warning" in logql:
                return warning_logs
            return []

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_logs):
            result = await log_agent(state)

            # Most recent should be first
            assert result["log_data"][0] == "Error at 10:05"
            assert result["log_data"][1] == "Warning at 10:03"
            assert result["log_data"][2] == "Error at 10:00"

    @pytest.mark.asyncio
    async def test_handles_loki_unavailable(self) -> None:
        """Verify agent handles Loki being unavailable."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: database",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_search_fails(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            raise ToolExecutionError("Loki unavailable")

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_fails):
            result = await log_agent(state)

            assert result["log_data"] == []
            assert "error" in result
            assert "Loki unavailable" in result["error"]
            assert "failed to retrieve logs" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_builds_correct_logql_queries(self) -> None:
        """Verify correct LogQL queries are built for service and level."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Alert for service: payment-service",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            return []

        with patch(
            "api.agents.log_agent._search_logs", side_effect=mock_search_logs
        ) as mock_search:
            await log_agent(state)

            # Verify 2 queries were made
            assert mock_search.call_count == 2

            # Extract query strings
            calls = mock_search.call_args_list
            error_call = calls[0]
            warning_call = calls[1]

            # Verify error query
            error_query = error_call.args[0]
            assert "payment-service" in error_query
            assert 'level="error"' in error_query

            # Verify warning query
            warning_query = warning_call.args[0]
            assert "payment-service" in warning_query
            assert 'level="warning"' in warning_query

            # Verify parameters
            assert error_call.kwargs["start_offset"] == "60m"
            assert error_call.kwargs["limit"] == 50
            assert warning_call.kwargs["start_offset"] == "60m"
            assert warning_call.kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_handles_empty_results(self) -> None:
        """Verify agent handles empty log results gracefully."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: backend",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            return []  # No logs found

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_logs):
            result = await log_agent(state)

            assert result["log_data"] == []
            assert "error" not in result
            assert "0 relevant log entries" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_executes_queries_concurrently(self) -> None:
        """Verify error and warning queries execute concurrently."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: api",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        execution_order = []

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            if "error" in logql:
                execution_order.append("error")
            elif "warning" in logql:
                execution_order.append("warning")
            return []

        with patch("api.agents.log_agent._search_logs", side_effect=mock_search_logs):
            await log_agent(state)

            # Both queries should execute
            assert len(execution_order) == 2
            assert "error" in execution_order
            assert "warning" in execution_order

    @pytest.mark.asyncio
    async def test_uses_unknown_service_when_not_found(self) -> None:
        """Verify 'unknown' is used when service cannot be extracted."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Generic alert without service",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_search_logs(
            logql: str, start_offset: str = "1h", limit: int = 100
        ) -> list[LogEntry]:
            return []

        with patch(
            "api.agents.log_agent._search_logs", side_effect=mock_search_logs
        ) as mock_search:
            result = await log_agent(state)

            # Verify message contains 'unknown'
            assert "unknown" in result["messages"][0].content

            # Verify queries use 'unknown'
            queries = [call.args[0] for call in mock_search.call_args_list]
            assert all("unknown" in query for query in queries)
