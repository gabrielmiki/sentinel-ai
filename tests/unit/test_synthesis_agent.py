"""
Unit tests for synthesis agent node.

Tests LLM-based report generation, retry logic, formatting,
and error handling.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.agents.graph import GraphState
from api.agents.synthesis_agent import (
    _build_user_message,
    _format_logs,
    _format_metrics,
    _format_runbooks,
    synthesis_agent,
)


class TestFormatMetrics:
    """Tests for metrics formatting function."""

    def test_formats_successful_metrics(self) -> None:
        """Verify metrics with data are formatted."""
        metrics_data = {
            "request_rate": {
                "status": "success",
                "data": {"result": [{"metric": {}, "value": [123, "100"]}]},
            },
            "cpu_usage": {
                "status": "success",
                "data": {"result": [{"metric": {}, "value": [123, "90"]}]},
            },
        }

        result = _format_metrics(metrics_data)

        assert "request_rate: 1 data points" in result
        assert "cpu_usage: 1 data points" in result

    def test_formats_error_metrics(self) -> None:
        """Verify failed metrics show error message."""
        metrics_data = {
            "p99_latency": {"error": "Prometheus timeout"},
        }

        result = _format_metrics(metrics_data)

        assert "p99_latency: Error - Prometheus timeout" in result

    def test_handles_empty_metrics(self) -> None:
        """Verify empty metrics show appropriate message."""
        result = _format_metrics({})

        assert "No metrics data available" in result


class TestFormatLogs:
    """Tests for log formatting function."""

    def test_formats_first_10_logs(self) -> None:
        """Verify first 10 logs are formatted with numbers."""
        logs = [f"Log entry {i}" for i in range(15)]

        result = _format_logs(logs)

        # Should include first 10
        for i in range(10):
            assert f"{i + 1}. Log entry {i}" in result

        # Should not include 11th entry
        assert "Log entry 10" not in result

    def test_handles_empty_logs(self) -> None:
        """Verify empty logs show appropriate message."""
        result = _format_logs([])

        assert "No log data available" in result


class TestFormatRunbooks:
    """Tests for runbook formatting function."""

    def test_formats_runbook_titles_and_previews(self) -> None:
        """Verify runbooks show title and first 200 chars."""
        runbooks = [
            {
                "title": "Database Guide",
                "content": "A" * 250,  # Longer than 200 chars
                "score": 0.9,
            },
            {
                "title": "API Guide",
                "content": "Short content",
                "score": 0.8,
            },
        ]

        result = _format_runbooks(runbooks)

        assert "1. Database Guide" in result
        assert ("A" * 200) + "..." in result  # Truncated
        assert "2. API Guide" in result
        assert "Short content" in result  # Not truncated

    def test_handles_empty_runbooks(self) -> None:
        """Verify empty runbooks show appropriate message."""
        result = _format_runbooks([])

        assert "No runbooks found" in result


class TestBuildUserMessage:
    """Tests for user message building function."""

    def test_includes_all_context(self) -> None:
        """Verify user message includes trigger, metrics, logs, and runbooks."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "High CPU alert",
            "metrics_data": {
                "cpu_usage": {
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [123, "95"]}]},
                }
            },
            "log_data": ["Error 1", "Error 2"],
            "runbook_hits": [
                {"title": "CPU Troubleshooting", "content": "Steps to debug CPU issues"}
            ],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        message = _build_user_message(state)

        assert "High CPU alert" in message
        assert "cpu_usage" in message
        assert "Error 1" in message
        assert "Error 2" in message
        assert "CPU Troubleshooting" in message


class TestSynthesisAgent:
    """Tests for synthesis agent node."""

    @pytest.mark.asyncio
    async def test_generates_valid_report(self) -> None:
        """Verify agent generates valid JSON report from LLM response."""
        state: GraphState = {
            "incident_id": "test-123",
            "trigger": "Service degradation",
            "metrics_data": {},
            "log_data": ["Error log"],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        mock_report = {
            "summary": "Service experiencing high latency due to database issues.",
            "root_cause_hypothesis": "Database connection pool exhaustion",
            "affected_components": ["backend", "database"],
            "recommended_actions": [
                "Increase connection pool size",
                "Review slow queries",
            ],
            "severity_assessment": "high",
        }

        mock_response = AsyncMock()
        mock_response.content = json.dumps(mock_report)

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("api.agents.synthesis_agent.ChatGoogleGenerativeAI") as mock_llm_class,
        ):
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = mock_response
            mock_llm_class.return_value = mock_llm

            result = await synthesis_agent(state)

            assert "final_report" in result
            parsed_report = json.loads(result["final_report"])
            assert parsed_report == mock_report
            assert "generated incident report" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_retries_on_invalid_json(self) -> None:
        """Verify agent retries when first response is invalid JSON."""
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

        valid_report = {
            "summary": "Fixed report",
            "root_cause_hypothesis": "Test",
            "affected_components": ["test"],
            "recommended_actions": ["action"],
            "severity_assessment": "low",
        }

        # First response is invalid JSON, second is valid
        mock_response1 = AsyncMock()
        mock_response1.content = "```json\n{invalid json}\n```"

        mock_response2 = AsyncMock()
        mock_response2.content = json.dumps(valid_report)

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("api.agents.synthesis_agent.ChatGoogleGenerativeAI") as mock_llm_class,
        ):
            mock_llm = AsyncMock()
            mock_llm.ainvoke.side_effect = [mock_response1, mock_response2]
            mock_llm_class.return_value = mock_llm

            result = await synthesis_agent(state)

            # Should succeed on retry
            assert "final_report" in result
            parsed_report = json.loads(result["final_report"])
            assert parsed_report == valid_report
            assert "retry" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_fallback_on_double_parse_failure(self) -> None:
        """Verify agent returns fallback report when both attempts fail."""
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

        # Both responses are invalid JSON
        mock_response1 = AsyncMock()
        mock_response1.content = "Not JSON at all"

        mock_response2 = AsyncMock()
        mock_response2.content = "Still not JSON"

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("api.agents.synthesis_agent.ChatGoogleGenerativeAI") as mock_llm_class,
        ):
            mock_llm = AsyncMock()
            mock_llm.ainvoke.side_effect = [mock_response1, mock_response2]
            mock_llm_class.return_value = mock_llm

            result = await synthesis_agent(state)

            # Should return fallback report
            assert "final_report" in result
            parsed_report = json.loads(result["final_report"])
            assert parsed_report["summary"] == "Analysis failed"
            assert parsed_report["root_cause_hypothesis"] == "LLM parsing error"
            assert "Still not JSON" in parsed_report["recommended_actions"][0]
            assert "fallback report" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_missing_api_key(self) -> None:
        """Verify agent returns fallback when API key not configured."""
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

        with patch.dict("os.environ", {}, clear=True):
            result = await synthesis_agent(state)

            assert "final_report" in result
            parsed_report = json.loads(result["final_report"])
            assert "OpenAI API key not configured" in parsed_report["summary"]
            assert "no API key" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_handles_unexpected_llm_error(self) -> None:
        """Verify agent handles unexpected LLM errors gracefully."""
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

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("api.agents.synthesis_agent.ChatGoogleGenerativeAI") as mock_llm_class,
        ):
            mock_llm = AsyncMock()
            mock_llm.ainvoke.side_effect = Exception("Network error")
            mock_llm_class.return_value = mock_llm

            result = await synthesis_agent(state)

            assert "final_report" in result
            assert "error" in result
            assert "Network error" in result["error"]
            parsed_report = json.loads(result["final_report"])
            assert "Unexpected error" in parsed_report["root_cause_hypothesis"]

    @pytest.mark.asyncio
    async def test_uses_correct_llm_config(self) -> None:
        """Verify agent uses gpt-4o-mini with temperature 0."""
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

        mock_response = AsyncMock()
        mock_response.content = json.dumps(
            {
                "summary": "Test",
                "root_cause_hypothesis": "Test",
                "affected_components": [],
                "recommended_actions": [],
                "severity_assessment": "low",
            }
        )

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch("api.agents.synthesis_agent.ChatGoogleGenerativeAI") as mock_llm_class,
        ):
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = mock_response
            mock_llm_class.return_value = mock_llm

            await synthesis_agent(state)

            # Verify LLM was initialized with correct params
            mock_llm_class.assert_called_once_with(model="gpt-4o-mini", temperature=0)
