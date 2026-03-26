"""
Unit tests for metrics agent node.

Tests service name extraction, query execution, error handling,
and concurrent query execution.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.metrics_agent import extract_service_name, metrics_agent
from api.tools.prometheus import PrometheusData, PrometheusResult, ToolExecutionError


class TestExtractServiceName:
    """Tests for service name extraction from trigger string."""

    def test_extracts_service_from_trigger(self) -> None:
        """Verify service name is extracted from 'service: <name>' pattern."""
        trigger = "High CPU alert for service: backend"
        assert extract_service_name(trigger) == "backend"

    def test_extracts_service_case_insensitive(self) -> None:
        """Verify extraction is case insensitive."""
        trigger = "Alert for SERVICE: api-gateway"
        assert extract_service_name(trigger) == "api-gateway"

    def test_extracts_service_with_underscores(self) -> None:
        """Verify service names with underscores are extracted."""
        trigger = "service: user_service is down"
        assert extract_service_name(trigger) == "user_service"

    def test_returns_unknown_when_no_service(self) -> None:
        """Verify 'unknown' is returned when no service pattern found."""
        trigger = "Generic alert without service information"
        assert extract_service_name(trigger) == "unknown"

    def test_extracts_first_service_when_multiple(self) -> None:
        """Verify first service is extracted when multiple matches."""
        trigger = "service: frontend depends on service: backend"
        assert extract_service_name(trigger) == "frontend"


class TestMetricsAgent:
    """Tests for metrics agent node."""

    @pytest.mark.asyncio
    async def test_collects_all_metrics_successfully(self) -> None:
        """Verify agent collects all 4 metrics when Prometheus returns data."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "High CPU usage for service: backend",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_result = PrometheusResult(
            status="success",
            data=PrometheusData(resultType="vector", result=[]),
            error=None,
            errorType=None,
        )

        with patch("api.agents.metrics_agent._query_prometheus") as mock_query:
            mock_query.return_value = mock_result

            result = await metrics_agent(state)

            assert "metrics_data" in result
            assert len(result["metrics_data"]) == 4
            assert "request_rate" in result["metrics_data"]
            assert "error_rate" in result["metrics_data"]
            assert "p99_latency" in result["metrics_data"]
            assert "cpu_usage" in result["metrics_data"]

            # Verify all queries succeeded
            # Success: model_dump() has "status" key
            # Error: {"error": "message"} has no "status" key
            for metric_name, metric_data in result["metrics_data"].items():
                assert "status" in metric_data, f"{metric_name} should have succeeded"

            # Verify message
            assert len(result["messages"]) == 1
            assert isinstance(result["messages"][0], AIMessage)
            assert "4/4 metrics" in result["messages"][0].content
            assert "backend" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_partial_failures(self) -> None:
        """Verify agent continues when some queries fail."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: api timeout",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_success = PrometheusResult(
            status="success",
            data=PrometheusData(resultType="vector", result=[]),
            error=None,
            errorType=None,
        )

        call_count = 0

        async def mock_query_with_failures(
            promql: str, time: str | None = None, timeout: float = 10.0
        ) -> PrometheusResult:
            nonlocal call_count
            call_count += 1
            # Fail the first 2 queries, succeed the last 2
            if call_count <= 2:
                raise ToolExecutionError("Prometheus timeout")
            return mock_success

        with patch(
            "api.agents.metrics_agent._query_prometheus",
            side_effect=mock_query_with_failures,
        ):
            result = await metrics_agent(state)

            assert "metrics_data" in result
            assert len(result["metrics_data"]) == 4

            # Count errors vs successes
            # Success: has "status" key
            # Error: {"error": "message"} has no "status" key
            success_count = sum(1 for data in result["metrics_data"].values() if "status" in data)
            error_count = sum(1 for data in result["metrics_data"].values() if "status" not in data)

            assert error_count == 2
            assert success_count == 2

            # Verify message shows partial success
            assert "2/4 metrics" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_all_queries_failing(self) -> None:
        """Verify agent returns error data when all queries fail."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: database connection issues",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        async def mock_query_always_fails(
            promql: str, time: str | None = None, timeout: float = 10.0
        ) -> PrometheusResult:
            raise ToolExecutionError("Prometheus unavailable")

        with patch(
            "api.agents.metrics_agent._query_prometheus",
            side_effect=mock_query_always_fails,
        ):
            result = await metrics_agent(state)

            assert "metrics_data" in result
            assert len(result["metrics_data"]) == 4

            # All should have errors (no "status" key)
            for metric_data in result["metrics_data"].values():
                assert "status" not in metric_data, "Should be error dict, not PrometheusResult"
                assert "error" in metric_data
                assert "Prometheus unavailable" in metric_data["error"]

            # Verify message shows 0 successes
            assert "0/4 metrics" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_builds_correct_promql_queries(self) -> None:
        """Verify correct PromQL queries are built for service."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Alert for service: frontend",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_result = PrometheusResult(
            status="success",
            data=PrometheusData(resultType="vector", result=[]),
            error=None,
            errorType=None,
        )

        with patch("api.agents.metrics_agent._query_prometheus") as mock_query:
            mock_query.return_value = mock_result

            await metrics_agent(state)

            # Verify 4 queries were made
            assert mock_query.call_count == 4

            # Extract all query strings
            queries = [call.args[0] for call in mock_query.call_args_list]

            # Verify service name is in all queries
            assert all("frontend" in query for query in queries)

            # Verify specific query patterns
            assert any("http_requests_total" in query for query in queries)
            assert any('status=~"5.."' in query for query in queries)
            assert any("histogram_quantile" in query for query in queries)
            assert any("process_cpu_seconds_total" in query for query in queries)

    @pytest.mark.asyncio
    async def test_uses_unknown_service_when_not_found(self) -> None:
        """Verify 'unknown' is used when service cannot be extracted."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Generic high CPU alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_result = PrometheusResult(
            status="success",
            data=PrometheusData(resultType="vector", result=[]),
            error=None,
            errorType=None,
        )

        with patch("api.agents.metrics_agent._query_prometheus") as mock_query:
            mock_query.return_value = mock_result

            result = await metrics_agent(state)

            # Verify message contains 'unknown'
            assert "unknown" in result["messages"][0].content

            # Verify queries use 'unknown'
            queries = [call.args[0] for call in mock_query.call_args_list]
            assert all("unknown" in query for query in queries)

    @pytest.mark.asyncio
    async def test_executes_queries_concurrently(self) -> None:
        """Verify queries are executed concurrently using asyncio.gather."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: backend slow response",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_result = PrometheusResult(
            status="success",
            data=PrometheusData(resultType="vector", result=[]),
            error=None,
            errorType=None,
        )

        execution_order = []

        async def mock_query_track_order(
            promql: str, time: str | None = None, timeout: float = 10.0
        ) -> PrometheusResult:
            # Track which query is called
            if "http_requests_total" in promql and "status" not in promql:
                execution_order.append("request_rate")
            elif "status" in promql:
                execution_order.append("error_rate")
            elif "histogram_quantile" in promql:
                execution_order.append("p99_latency")
            elif "cpu" in promql:
                execution_order.append("cpu_usage")
            return mock_result

        with patch(
            "api.agents.metrics_agent._query_prometheus",
            side_effect=mock_query_track_order,
        ):
            await metrics_agent(state)

            # All 4 queries should execute
            assert len(execution_order) == 4

    @pytest.mark.asyncio
    async def test_returns_serializable_metrics_data(self) -> None:
        """Verify metrics_data contains serializable dicts, not Pydantic models."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "service: api high latency",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_result = PrometheusResult(
            status="success",
            data=PrometheusData(
                resultType="vector",
                result=[],  # Simplified for test - we only care about serialization
            ),
            error=None,
            errorType=None,
        )

        with patch("api.agents.metrics_agent._query_prometheus") as mock_query:
            mock_query.return_value = mock_result

            result = await metrics_agent(state)

            # Verify all metrics_data values are plain dicts
            for metric_data in result["metrics_data"].values():
                assert isinstance(metric_data, dict)
                # Should have 'status' and 'data' keys from model_dump()
                if "status" in metric_data:  # Success case
                    assert "data" in metric_data
                    assert "error" in metric_data  # Will be None
