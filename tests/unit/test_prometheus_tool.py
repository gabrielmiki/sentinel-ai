"""
Unit tests for Prometheus tool.

Tests cover instant queries, range queries, error handling, timeouts,
and edge cases like empty results.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from api.tools.prometheus import (
    PrometheusData,
    PrometheusResult,
    PrometheusResultItem,
    ToolExecutionError,
    query,
    query_range,
)


class TestPrometheusQuery:
    """Tests for instant Prometheus query function."""

    @pytest.mark.asyncio
    async def test_query_happy_path(self) -> None:
        """Verify query returns parsed PrometheusResult on success."""
        mock_response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"job": "api", "instance": "localhost:8000"},
                        "value": [1711234567.89, "42.5"],
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await query("up{job='api'}")

            assert result.status == "success"
            assert result.data is not None
            assert result.data.resultType == "vector"
            assert len(result.data.result) == 1
            assert result.data.result[0].metric["job"] == "api"
            assert result.data.result[0].value[1] == "42.5"

    @pytest.mark.asyncio
    async def test_query_with_time_parameter(self) -> None:
        """Verify query passes time parameter to Prometheus."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await query("up", time="2024-03-24T10:00:00Z")

            # Verify time parameter was passed
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["params"]["time"] == "2024-03-24T10:00:00Z"

    @pytest.mark.asyncio
    async def test_query_empty_result(self) -> None:
        """Verify query handles empty result gracefully without raising."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await query("nonexistent_metric")

            assert result.status == "success"
            assert result.data is not None
            assert result.data.result == []

    @pytest.mark.asyncio
    async def test_query_timeout(self) -> None:
        """Verify query raises ToolExecutionError on timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query("up", timeout=5.0)

            assert "timeout after 5.0s" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_query_http_error(self) -> None:
        """Verify query raises ToolExecutionError on non-200 HTTP status."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=503, text="Service Unavailable")
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query("up")

            assert "503" in str(exc_info.value)
            assert "Service Unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_prometheus_error_response(self) -> None:
        """Verify query raises ToolExecutionError when Prometheus returns error status."""
        mock_response = {
            "status": "error",
            "errorType": "bad_data",
            "error": "invalid PromQL syntax",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query("invalid{")

            assert "bad_data" in str(exc_info.value)
            assert "invalid PromQL syntax" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_network_error(self) -> None:
        """Verify query raises ToolExecutionError on network failure."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query("up")

            assert "HTTP request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_uses_prometheus_url_env(self) -> None:
        """Verify query uses PROMETHEUS_URL environment variable."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with patch.dict("os.environ", {"PROMETHEUS_URL": "http://custom:9090"}):
                await query("up")

            # Verify custom URL was used
            call_args = mock_get.call_args.args
            assert call_args[0] == "http://custom:9090/api/v1/query"


class TestPrometheusQueryRange:
    """Tests for Prometheus range query function."""

    @pytest.mark.asyncio
    async def test_query_range_happy_path(self) -> None:
        """Verify query_range returns time-series data on success."""
        mock_response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "api"},
                        "value": [1711234567.89, "100"],
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await query_range(
                "rate(http_requests_total[5m])",
                start="2024-03-24T10:00:00Z",
                end="2024-03-24T11:00:00Z",
            )

            assert result.status == "success"
            assert result.data is not None
            assert result.data.resultType == "matrix"

    @pytest.mark.asyncio
    async def test_query_range_with_custom_step(self) -> None:
        """Verify query_range passes custom step parameter."""
        mock_response = {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            await query_range(
                "up",
                start="2024-03-24T10:00:00Z",
                end="2024-03-24T11:00:00Z",
                step="1m",
            )

            # Verify step parameter was passed
            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["params"]["step"] == "1m"

    @pytest.mark.asyncio
    async def test_query_range_timeout(self) -> None:
        """Verify query_range raises ToolExecutionError on timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query_range(
                    "up",
                    start="2024-03-24T10:00:00Z",
                    end="2024-03-24T11:00:00Z",
                    timeout=10.0,
                )

            assert "timeout after 10.0s" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_query_range_prometheus_error(self) -> None:
        """Verify query_range raises ToolExecutionError on Prometheus error."""
        mock_response = {
            "status": "error",
            "errorType": "timeout",
            "error": "query timed out in expression evaluation",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                return_value=AsyncMock(status_code=200, json=lambda: mock_response)
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(ToolExecutionError) as exc_info:
                await query_range(
                    "rate(metric[1h])",
                    start="2024-03-24T10:00:00Z",
                    end="2024-03-24T11:00:00Z",
                )

            assert "timeout" in str(exc_info.value)
            assert "expression evaluation" in str(exc_info.value)


class TestPrometheusModels:
    """Tests for Pydantic models."""

    def test_prometheus_result_with_data(self) -> None:
        """Verify PrometheusResult parses successful response."""
        data = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"job": "test"}, "value": [123.45, "99"]}
                ],
            },
        }

        result = PrometheusResult(**data)

        assert result.status == "success"
        assert result.data is not None
        assert result.data.resultType == "vector"
        assert len(result.data.result) == 1

    def test_prometheus_result_with_error(self) -> None:
        """Verify PrometheusResult parses error response."""
        data = {
            "status": "error",
            "errorType": "bad_data",
            "error": "parse error",
        }

        result = PrometheusResult(**data)

        assert result.status == "error"
        assert result.errorType == "bad_data"
        assert result.error == "parse error"
        assert result.data is None

    def test_prometheus_data_empty_result(self) -> None:
        """Verify PrometheusData handles empty result list."""
        data = {"resultType": "vector", "result": []}

        prom_data = PrometheusData(**data)

        assert prom_data.resultType == "vector"
        assert prom_data.result == []
