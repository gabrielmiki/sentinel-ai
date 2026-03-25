"""
Prometheus HTTP API client for querying metrics.

Provides async functions to query Prometheus using PromQL for both instant
queries and time-series range queries.
"""

import os
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ToolExecutionError(Exception):
    """Raised when a tool execution fails (timeout, HTTP error, or Prometheus error)."""

    pass


class PrometheusMetric(BaseModel):
    """A single Prometheus metric with labels."""

    __pydantic_config__ = {"extra": "allow"}  # Allow arbitrary labels

    def __init__(self, **data: Any) -> None:
        """Accept any key-value pairs as metric labels."""
        super().__init__(**data)


class PrometheusResultItem(BaseModel):
    """A single result item from Prometheus query response."""

    metric: dict[str, str] = Field(
        default_factory=dict, description="Metric labels as key-value pairs"
    )
    value: tuple[float, str] = Field(description="Timestamp and value as [timestamp, value_string]")


class PrometheusData(BaseModel):
    """Data section of Prometheus response."""

    model_config = {"populate_by_name": True}

    result_type: str = Field(
        alias="resultType", description="Type of result (vector, matrix, scalar, string)"
    )
    result: list[PrometheusResultItem] = Field(
        default_factory=list, description="List of metric results"
    )


class PrometheusResult(BaseModel):
    """Complete Prometheus API response."""

    model_config = {"populate_by_name": True}

    status: str = Field(description="Response status (success or error)")
    data: PrometheusData | None = Field(
        default=None, description="Query result data (None if error)"
    )
    error: str | None = Field(default=None, description="Error message if status is error")
    error_type: str | None = Field(
        alias="errorType", default=None, description="Error type if status is error"
    )


async def _query_prometheus(
    promql: str,
    time: str | None = None,
    timeout: float = 10.0,
) -> PrometheusResult:
    """
    Internal function to execute an instant Prometheus query.

    Args:
        promql: PromQL query string
        time: Optional RFC3339 or Unix timestamp (defaults to current time)
        timeout: Request timeout in seconds

    Returns:
        PrometheusResult with query response

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Prometheus error
    """
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    url = f"{prometheus_url}/api/v1/query"

    params: dict[str, str] = {"query": promql}
    if time:
        params["time"] = time

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)

            # Check HTTP status
            if response.status_code != 200:
                raise ToolExecutionError(
                    f"Prometheus HTTP error {response.status_code}: {response.text}"
                )

            # Parse JSON response
            data = response.json()
            result = PrometheusResult(**data)

            # Check Prometheus status
            if result.status != "success":
                error_msg = result.error or "Unknown error"
                error_type = result.error_type or "unknown"
                raise ToolExecutionError(f"Prometheus query failed ({error_type}): {error_msg}")

            return result

    except httpx.TimeoutException as e:
        raise ToolExecutionError(f"Prometheus query timeout after {timeout}s") from e
    except httpx.HTTPError as e:
        raise ToolExecutionError(f"Prometheus HTTP request failed: {e}") from e


async def _query_range_prometheus(
    promql: str,
    start: str,
    end: str,
    step: str = "15s",
    timeout: float = 30.0,
) -> PrometheusResult:
    """
    Internal function to execute a Prometheus range query for time-series data.

    Args:
        promql: PromQL query string
        start: Start time (RFC3339 or Unix timestamp)
        end: End time (RFC3339 or Unix timestamp)
        step: Query resolution step (e.g., "15s", "1m", "5m")
        timeout: Request timeout in seconds

    Returns:
        PrometheusResult with time-series data

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Prometheus error
    """
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    url = f"{prometheus_url}/api/v1/query_range"

    params = {
        "query": promql,
        "start": start,
        "end": end,
        "step": step,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)

            # Check HTTP status
            if response.status_code != 200:
                raise ToolExecutionError(
                    f"Prometheus HTTP error {response.status_code}: {response.text}"
                )

            # Parse JSON response
            data = response.json()
            result = PrometheusResult(**data)

            # Check Prometheus status
            if result.status != "success":
                error_msg = result.error or "Unknown error"
                error_type = result.error_type or "unknown"
                raise ToolExecutionError(f"Prometheus query failed ({error_type}): {error_msg}")

            return result

    except httpx.TimeoutException as e:
        raise ToolExecutionError(f"Prometheus range query timeout after {timeout}s") from e
    except httpx.HTTPError as e:
        raise ToolExecutionError(f"Prometheus HTTP request failed: {e}") from e


@tool
async def query(
    promql: str,
    time: str | None = None,
    timeout: float = 10.0,
) -> PrometheusResult:
    """
    Query Prometheus metrics using PromQL.

    This tool queries the Prometheus monitoring system to retrieve current metric values
    using PromQL (Prometheus Query Language). Useful for checking system health,
    resource usage, and application metrics during incident investigation.

    Args:
        promql: PromQL query string (e.g., 'up{job="api"}', 'rate(http_requests_total[5m])')
        time: Optional RFC3339 or Unix timestamp (defaults to current time)
        timeout: Request timeout in seconds (default 10.0)

    Returns:
        PrometheusResult with query response containing metric data

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Prometheus error

    Examples:
        - query('up{job="backend"}')
        - query('rate(http_requests_total[5m])', time="2024-03-24T10:00:00Z")
    """
    return await _query_prometheus(promql, time, timeout)


@tool
async def query_range(
    promql: str,
    start: str,
    end: str,
    step: str = "15s",
    timeout: float = 30.0,
) -> PrometheusResult:
    """
    Query Prometheus metrics over a time range.

    This tool queries the Prometheus monitoring system to retrieve metric values over
    a specified time range, returning time-series data. Useful for analyzing trends,
    identifying patterns, and understanding system behavior over time.

    Args:
        promql: PromQL query string (e.g., 'rate(http_requests_total[5m])')
        start: Start time (RFC3339 or Unix timestamp, e.g., "2024-03-24T10:00:00Z")
        end: End time (RFC3339 or Unix timestamp)
        step: Query resolution step (e.g., "15s", "1m", "5m", default "15s")
        timeout: Request timeout in seconds (default 30.0)

    Returns:
        PrometheusResult with time-series data

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Prometheus error

    Examples:
        - query_range('up{job="backend"}', start="2024-03-24T10:00:00Z", end="2024-03-24T11:00:00Z")
        - query_range('rate(http_requests_total[5m])', start="2024-03-24T10:00:00Z", end="2024-03-24T11:00:00Z", step="1m")
    """
    return await _query_range_prometheus(promql, start, end, step, timeout)
