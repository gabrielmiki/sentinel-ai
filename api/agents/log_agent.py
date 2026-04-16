"""
Log agent node for LangGraph.

Searches Loki for error and warning logs related to the incident.
"""

import asyncio
import time
from typing import Any

from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.agents.metrics_agent import extract_service_name
from api.metrics import agent_duration_seconds, agent_invocations_total
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
    start_time = time.monotonic()
    try:
        service = extract_service_name(state["trigger"])

        # Build LogQL queries for error and warning logs
        # Note: Promtail adds 'service' label from Docker Compose service name
        # The service label will be "backend", "celery-worker", etc.
        # For now, query all backend services (may include backend-1, backend-2, backend-3)
        error_query = '{service=~"backend.*", level="error"}'
        warning_query = '{service=~"backend.*", level="warning"}'

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

        result = {
            "log_data": log_messages,
            "attempted_agents": ["log_agent"],
            "messages": [
                AIMessage(
                    content=f"LogAgent found {len(unique_logs)} relevant log entries for service '{service}'"
                )
            ],
        }

        agent_invocations_total.labels(agent_name="log_agent", status="success").inc()
        return result

    except ToolExecutionError as e:
        agent_invocations_total.labels(agent_name="log_agent", status="error").inc()
        return {
            "log_data": [],
            "attempted_agents": ["log_agent"],
            "error": str(e),
            "messages": [AIMessage(content=f"LogAgent failed to retrieve logs: {str(e)}")],
        }

    except Exception:
        agent_invocations_total.labels(agent_name="log_agent", status="error").inc()
        raise

    finally:
        agent_duration_seconds.labels(agent_name="log_agent").observe(time.monotonic() - start_time)
