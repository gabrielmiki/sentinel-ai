"""
Unit tests for runbook agent node.

Tests query building, semantic search, result conversion,
and error handling.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.runbook_agent import _build_search_query, runbook_agent
from api.tools.runbooks import Document


class TestBuildSearchQuery:
    """Tests for search query building from state."""

    def test_builds_query_from_trigger_only(self) -> None:
        """Verify query built from trigger when no logs or metrics."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "High CPU usage detected",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        query = _build_search_query(state)
        assert query == "High CPU usage detected"

    def test_includes_top_3_error_messages(self) -> None:
        """Verify top 3 log messages are included in query."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Database errors",
            "metrics_data": {},
            "log_data": [
                "Connection timeout",
                "Database pool exhausted",
                "Query failed",
                "Retry attempt 1",  # Should not be included (only top 3)
            ],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        query = _build_search_query(state)
        assert "Database errors" in query
        assert "Connection timeout" in query
        assert "Database pool exhausted" in query
        assert "Query failed" in query
        assert "Retry attempt 1" not in query

    def test_includes_metric_names_with_results(self) -> None:
        """Verify metric names with data are included in query."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Service degradation",
            "metrics_data": {
                "request_rate": {
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [123, "100"]}]},
                },
                "error_rate": {
                    "status": "success",
                    "data": {"result": []},  # Empty results, should not include
                },
                "cpu_usage": {
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [123, "90"]}]},
                },
            },
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        query = _build_search_query(state)
        assert "Service degradation" in query
        assert "request_rate" in query
        assert "cpu_usage" in query
        assert "error_rate" not in query  # Empty results

    def test_combines_all_context_elements(self) -> None:
        """Verify trigger, logs, and metrics are all combined."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "API timeout",
            "metrics_data": {
                "p99_latency": {
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [123, "500"]}]},
                }
            },
            "log_data": ["Connection refused", "Timeout after 30s"],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        query = _build_search_query(state)
        assert "API timeout" in query
        assert "Connection refused" in query
        assert "Timeout after 30s" in query
        assert "p99_latency" in query


class TestRunbookAgent:
    """Tests for runbook agent node."""

    @pytest.mark.asyncio
    async def test_finds_relevant_runbooks(self) -> None:
        """Verify agent returns runbooks with correct structure."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "High error rate for service: backend",
            "metrics_data": {},
            "log_data": ["Database connection failed"],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_documents = [
            Document(
                page_content="Steps to debug database connection issues...",
                metadata={"title": "Database Troubleshooting", "score": 0.92},
            ),
            Document(
                page_content="How to scale backend services...",
                metadata={"title": "Backend Scaling Guide", "score": 0.85},
            ),
        ]

        with patch("api.agents.runbook_agent._search_runbooks", return_value=mock_documents):
            result = await runbook_agent(state)

            assert "runbook_hits" in result
            assert len(result["runbook_hits"]) == 2

            # Verify first runbook structure
            runbook1 = result["runbook_hits"][0]
            assert runbook1["title"] == "Database Troubleshooting"
            assert "database connection issues" in runbook1["content"]
            assert runbook1["score"] == 0.92

            # Verify message
            assert len(result["messages"]) == 1
            assert isinstance(result["messages"][0], AIMessage)
            assert "2 relevant runbooks" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_empty_results(self) -> None:
        """Verify agent handles no matching runbooks gracefully."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Unknown error",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        with patch("api.agents.runbook_agent._search_runbooks", return_value=[]):
            result = await runbook_agent(state)

            assert result["runbook_hits"] == []
            assert "error" not in result  # Empty results are not errors
            assert "no relevant runbooks" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_search_tool_failure(self) -> None:
        """Verify agent handles search tool failures."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Service down",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_search_fails(query: str, k: int = 3) -> list[Document]:
            raise Exception("Vector database unavailable")

        with patch("api.agents.runbook_agent._search_runbooks", side_effect=mock_search_fails):
            result = await runbook_agent(state)

            assert result["runbook_hits"] == []
            assert "error" in result
            assert "Vector database unavailable" in result["error"]
            assert "search failed" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_missing_metadata_fields(self) -> None:
        """Verify agent handles documents with missing metadata."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_documents = [
            Document(
                page_content="Content without metadata",
                metadata={},  # Missing title and score
            ),
        ]

        with patch("api.agents.runbook_agent._search_runbooks", return_value=mock_documents):
            result = await runbook_agent(state)

            assert len(result["runbook_hits"]) == 1
            assert result["runbook_hits"][0]["title"] == "Untitled"
            assert result["runbook_hits"][0]["score"] == 0.0
            assert result["runbook_hits"][0]["content"] == "Content without metadata"

    @pytest.mark.asyncio
    async def test_limits_to_k_results(self) -> None:
        """Verify agent requests exactly k=3 results."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Test",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        with patch("api.agents.runbook_agent._search_runbooks", return_value=[]) as mock_search:
            await runbook_agent(state)

            # Verify k=3 was passed
            mock_search.assert_called_once()
            assert mock_search.call_args.kwargs["k"] == 3

    @pytest.mark.asyncio
    async def test_builds_query_from_full_context(self) -> None:
        """Verify agent uses all available context for search."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "API latency",
            "metrics_data": {
                "p99_latency": {
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [123, "800"]}]},
                }
            },
            "log_data": ["Slow query detected", "Database timeout"],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        with patch("api.agents.runbook_agent._search_runbooks", return_value=[]) as mock_search:
            await runbook_agent(state)

            # Verify query contains all context
            called_query = mock_search.call_args.args[0]
            assert "API latency" in called_query
            assert "Slow query detected" in called_query
            assert "Database timeout" in called_query
            assert "p99_latency" in called_query
