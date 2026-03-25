"""
Unit tests for Loki tool.

Tests cover log searches, error handling, timeouts, and edge cases like empty results.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from api.tools.loki import LogEntry, ToolExecutionError, _search_logs


class TestLokiSearch:
    """Tests for Loki log search function."""

    @pytest.mark.asyncio
    async def test_search_happy_path(self) -> None:
        """Verify search returns parsed LogEntry list on success."""
        mock_response = {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {
                            "level": "error",
                            "service": "backend",
                            "job": "api",
                        },
                        "values": [
                            ["1711234567000000000", "Database connection failed"],
                            ["1711234568000000000", "Retrying connection..."],
                        ],
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await _search_logs('{service="backend"} |= "error"')

            assert len(result) == 2
            assert all(isinstance(entry, LogEntry) for entry in result)
            assert result[0].level == "error"
            assert result[0].service == "backend"
            assert result[0].message == "Database connection failed"
            assert result[1].message == "Retrying connection..."

    @pytest.mark.asyncio
    async def test_search_with_custom_offset(self) -> None:
        """Verify search accepts custom start_offset parameter."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await _search_logs('{level="info"}', start_offset="30m")

            # Verify params include start/end timestamps
            call_kwargs = mock_get.call_args.kwargs
            assert "params" in call_kwargs
            assert "start" in call_kwargs["params"]
            assert "end" in call_kwargs["params"]

    @pytest.mark.asyncio
    async def test_search_with_custom_limit(self) -> None:
        """Verify search respects limit parameter."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await _search_logs('{service="backend"}', limit=50)

            # Verify limit parameter was passed
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["params"]["limit"] == "50"

    @pytest.mark.asyncio
    async def test_search_empty_result(self) -> None:
        """Verify search handles empty result gracefully without raising."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await _search_logs('{service="nonexistent"}')

            assert result == []

    @pytest.mark.asyncio
    async def test_search_extracts_service_from_job_label(self) -> None:
        """Verify search falls back to 'job' label when 'service' is missing."""
        mock_response = {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {"job": "celery-worker", "level": "info"},
                        "values": [["1711234567000000000", "Task completed"]],
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await _search_logs('{job="celery-worker"}')

            assert len(result) == 1
            assert result[0].service == "celery-worker"

    @pytest.mark.asyncio
    async def test_search_timeout(self) -> None:
        """Verify search raises ToolExecutionError on timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await _search_logs('{level="error"}')

            assert "timeout after 30.0s" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_search_http_error(self) -> None:
        """Verify search raises ToolExecutionError on non-200 HTTP status."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=503, text="Service Unavailable")
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await _search_logs('{service="backend"}')

            assert "503" in str(exc_info.value)
            assert "Service Unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_loki_error_response(self) -> None:
        """Verify search raises ToolExecutionError when Loki returns error status."""
        mock_response = {
            "status": "error",
            "errorType": "bad_data",
            "error": "invalid LogQL syntax",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await _search_logs("{invalid")

            assert "bad_data" in str(exc_info.value)
            assert "invalid LogQL syntax" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_network_error(self) -> None:
        """Verify search raises ToolExecutionError on network failure."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await _search_logs('{service="backend"}')

            assert "HTTP request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_uses_loki_url_env(self) -> None:
        """Verify search uses LOKI_URL environment variable."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "streams", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with patch.dict("os.environ", {"LOKI_URL": "http://custom-loki:3100"}):
                await _search_logs('{level="info"}')

            # Verify custom URL was used
            call_args = mock_get.call_args.args
            assert call_args[0] == "http://custom-loki:3100/loki/api/v1/query_range"

    @pytest.mark.asyncio
    async def test_search_parses_timestamps_correctly(self) -> None:
        """Verify search converts nanosecond timestamps to ISO 8601."""
        mock_response = {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {"level": "info"},
                        "values": [["1711234567000000000", "Test message"]],
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await _search_logs('{level="info"}')

            assert len(result) == 1
            # Timestamp should be ISO 8601 format
            assert "T" in result[0].timestamp
            assert result[0].timestamp.endswith("+00:00") or result[0].timestamp.endswith("Z")


class TestLokiModels:
    """Tests for Pydantic models."""

    def test_log_entry_with_all_fields(self) -> None:
        """Verify LogEntry accepts all fields."""
        entry = LogEntry(
            timestamp="2024-03-24T10:00:00+00:00",
            level="error",
            service="backend",
            message="Test error message",
            labels={"pod": "backend-1", "namespace": "production"},
        )

        assert entry.timestamp == "2024-03-24T10:00:00+00:00"
        assert entry.level == "error"
        assert entry.service == "backend"
        assert entry.message == "Test error message"
        assert entry.labels["pod"] == "backend-1"

    def test_log_entry_with_minimal_fields(self) -> None:
        """Verify LogEntry works with only required fields."""
        entry = LogEntry(
            timestamp="2024-03-24T10:00:00+00:00",
            message="Minimal log entry",
        )

        assert entry.timestamp == "2024-03-24T10:00:00+00:00"
        assert entry.message == "Minimal log entry"
        assert entry.level is None
        assert entry.service is None
        assert entry.labels == {}
