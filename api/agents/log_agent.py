"""
Log agent node for LangGraph.

Searches Loki for error and warning logs related to the incident.
"""

import asyncio
from typing import Any

from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.metrics_agent import extract_service_name
from api.tools.loki import LogEntry, _search_logs
from api.tools.prometheus import ToolExecutionError


async def log_agent(state: GraphState) -> dict[str, Any]:
    """
    Log agent node - searches Loki for relevant logs.

    Searches for both error and warning level logs for the affected service.
    Combines, deduplicates, and sorts results.

    Args:
        state: Current graph state with incident details

    Returns:
        Updated state with log_data and messages
    """
    service = extract_service_name(state["trigger"])

    try:
        # Build LogQL queries for error and warning logs
        error_query = f'{{service="{service}", level="error"}}'
        warning_query = f'{{service="{service}", level="warning"}}'

        # Execute queries concurrently
        error_logs_task = _search_logs(error_query, start_offset="60m", limit=50)
        warning_logs_task = _search_logs(warning_query, start_offset="60m", limit=20)

        error_logs, warning_logs = await asyncio.gather(error_logs_task, warning_logs_task)

        # Combine results
        combined_logs = error_logs + warning_logs

        # Deduplicate by timestamp + message
        seen: set[tuple[str, str]] = set()
        unique_logs: list[LogEntry] = []
        for entry in combined_logs:
            key = (entry.timestamp, entry.message)
            if key not in seen:
                seen.add(key)
                unique_logs.append(entry)

        # Sort by timestamp descending (most recent first)
        unique_logs.sort(key=lambda x: x.timestamp, reverse=True)

        # Extract messages
        log_messages = [entry.message for entry in unique_logs]

        return {
            "log_data": log_messages,
            "messages": [
                AIMessage(
                    content=f"LogAgent found {len(unique_logs)} relevant log entries for service '{service}'"
                )
            ],
        }

    except ToolExecutionError as e:
        return {
            "log_data": [],
            "error": str(e),
            "messages": [AIMessage(content=f"LogAgent failed to retrieve logs: {str(e)}")],
        }
