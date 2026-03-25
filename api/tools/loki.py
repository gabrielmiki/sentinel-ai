"""
Loki HTTP API client for querying logs.

Provides async functions to search Loki logs using LogQL queries.
"""

import os
from datetime import UTC, datetime, timedelta

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from api.tools.prometheus import ToolExecutionError


class LogEntry(BaseModel):
    """A single log entry from Loki."""

    timestamp: str = Field(description="ISO 8601 timestamp")
    level: str | None = Field(default=None, description="Log level (info, error, etc.)")
    service: str | None = Field(default=None, description="Service name")
    message: str = Field(description="Log message content")
    labels: dict[str, str] = Field(
        default_factory=dict, description="Additional labels from stream"
    )


class LokiStream(BaseModel):
    """A single log stream from Loki response."""

    stream: dict[str, str] = Field(default_factory=dict, description="Stream labels")
    values: list[tuple[str, str]] = Field(
        default_factory=list, description="List of [timestamp_nanos, message] tuples"
    )


class LokiData(BaseModel):
    """Data section of Loki response."""

    result_type: str = Field(alias="resultType", description="Type of result (streams)")
    result: list[LokiStream] = Field(default_factory=list, description="List of log streams")

    model_config = {"populate_by_name": True}


class LokiResult(BaseModel):
    """Complete Loki API response."""

    status: str = Field(description="Response status (success or error)")
    data: LokiData | None = Field(default=None, description="Query result data (None if error)")
    error: str | None = Field(default=None, description="Error message if status is error")
    error_type: str | None = Field(
        alias="errorType", default=None, description="Error type if status is error"
    )

    model_config = {"populate_by_name": True}


def _parse_timestamp_nanos(timestamp_nanos: str) -> str:
    """
    Convert Loki nanosecond timestamp to ISO 8601 string.

    Args:
        timestamp_nanos: Timestamp in nanoseconds as string

    Returns:
        ISO 8601 formatted timestamp string
    """
    # Convert nanoseconds to seconds
    timestamp_seconds = int(timestamp_nanos) / 1_000_000_000
    dt = datetime.fromtimestamp(timestamp_seconds, tz=UTC)
    return dt.isoformat()


def _flatten_streams_to_entries(loki_result: LokiResult) -> list[LogEntry]:
    """
    Flatten Loki streams into a list of LogEntry objects.

    Args:
        loki_result: Parsed Loki API response

    Returns:
        List of LogEntry objects
    """
    if not loki_result.data or not loki_result.data.result:
        return []

    entries: list[LogEntry] = []
    for stream in loki_result.data.result:
        # Extract common labels from stream
        stream_labels = stream.stream
        level = stream_labels.get("level")
        service = stream_labels.get("service") or stream_labels.get("job")

        # Create LogEntry for each value in the stream
        for timestamp_nanos, message in stream.values:
            entry = LogEntry(
                timestamp=_parse_timestamp_nanos(timestamp_nanos),
                level=level,
                service=service,
                message=message,
                labels=stream_labels,
            )
            entries.append(entry)

    return entries


async def _search_logs(logql: str, start_offset: str = "1h", limit: int = 100) -> list[LogEntry]:
    """
    Internal function to search Loki logs using LogQL query.

    Args:
        logql: LogQL query string (e.g., '{service="backend"} |= "error"')
        start_offset: How far back to search (e.g., "1h", "30m", "24h")
        limit: Maximum number of log entries to return (default 100)

    Returns:
        List of LogEntry objects with timestamp, level, service, message, and labels

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Loki error
    """
    loki_url = os.getenv("LOKI_URL", "http://loki:3100")
    url = f"{loki_url}/loki/api/v1/query_range"

    # Calculate time range
    end_time = datetime.now(UTC)
    # Parse start_offset (simple implementation for common cases)
    if start_offset.endswith("h"):
        hours = int(start_offset[:-1])
        start_time = end_time - timedelta(hours=hours)
    elif start_offset.endswith("m"):
        minutes = int(start_offset[:-1])
        start_time = end_time - timedelta(minutes=minutes)
    elif start_offset.endswith("d"):
        days = int(start_offset[:-1])
        start_time = end_time - timedelta(days=days)
    else:
        # Default to 1 hour if invalid format
        start_time = end_time - timedelta(hours=1)

    # Loki expects timestamps in nanoseconds
    start_ns = int(start_time.timestamp() * 1_000_000_000)
    end_ns = int(end_time.timestamp() * 1_000_000_000)

    params = {
        "query": logql,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(limit),
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

            # Check HTTP status
            if response.status_code != 200:
                raise ToolExecutionError(f"Loki HTTP error {response.status_code}: {response.text}")

            # Parse JSON response
            data = response.json()
            result = LokiResult(**data)

            # Check Loki status
            if result.status != "success":
                error_msg = result.error or "Unknown error"
                error_type = result.error_type or "unknown"
                raise ToolExecutionError(f"Loki query failed ({error_type}): {error_msg}")

            # Flatten streams into log entries
            return _flatten_streams_to_entries(result)

    except httpx.TimeoutException as e:
        raise ToolExecutionError("Loki query timeout after 30.0s") from e
    except httpx.HTTPError as e:
        raise ToolExecutionError(f"Loki HTTP request failed: {e}") from e


@tool
async def search(logql: str, start_offset: str = "1h", limit: int = 100) -> list[LogEntry]:
    """
    Search Loki logs using LogQL query.

    This tool queries the Loki log aggregation system to retrieve log entries
    matching the specified LogQL query. Useful for investigating incidents,
    debugging issues, and correlating logs with metrics.

    Args:
        logql: LogQL query string (e.g., '{service="backend"} |= "error"')
        start_offset: How far back to search (e.g., "1h", "30m", "24h")
        limit: Maximum number of log entries to return (default 100)

    Returns:
        List of LogEntry objects with timestamp, level, service, message, and labels

    Raises:
        ToolExecutionError: On timeout, HTTP error, or Loki error

    Examples:
        - search('{service="backend"} |= "error"', start_offset="1h")
        - search('{level="error"}', start_offset="30m", limit=50)
    """
    return await _search_logs(logql, start_offset, limit)
