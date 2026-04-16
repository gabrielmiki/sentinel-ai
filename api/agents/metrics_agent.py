"""
Metrics agent node for LangGraph.

Queries Prometheus for service metrics related to the incident.
"""

import asyncio
import re
import time
from typing import Any

from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.metrics import agent_duration_seconds, agent_invocations_total
from api.tools.prometheus import ToolExecutionError, _query_prometheus


def extract_service_name(trigger: str) -> str:
    """
    Extract service name from trigger string.

    Looks for pattern "service: <name>" (case insensitive).
    Returns "unknown" if no match found.

    Args:
        trigger: Human-readable alert description

    Returns:
        Extracted service name or "unknown"
    """
    match = re.search(r"service:\s*([\w-]+)", trigger, re.IGNORECASE)
    if match:
        return match.group(1)
    return "unknown"


async def metrics_agent(state: GraphState) -> dict[str, Any]:
    """
    Metrics agent node - queries Prometheus for metrics.

    Builds PromQL queries for request rate, error rate, P99 latency,
    and CPU usage. Executes queries concurrently and returns results.

    Args:
        state: Current graph state with incident details

    Returns:
        Updated state with metrics_data and messages
    """
    start_time = time.monotonic()
    try:
        service = extract_service_name(state["trigger"])

        # Build PromQL queries using available metrics from backend
        # Note: Backend currently only exports basic process metrics
        # TODO: Add HTTP request metrics via prometheus-fastapi-instrumentator
        queries = {
            "cpu_usage": 'rate(process_cpu_seconds_total{job="sentinel-backend"}[5m])',
            "memory_usage": 'process_resident_memory_bytes{job="sentinel-backend"}',
            "open_files": 'process_open_fds{job="sentinel-backend"}',
            "gc_collections": 'rate(python_gc_collections_total{job="sentinel-backend"}[5m])',
        }

        # Execute queries concurrently
        async def query_with_error_handling(name: str, promql: str) -> tuple[str, Any]:
            """Execute a single query and return (name, result_or_error)."""
            try:
                result = await _query_prometheus(promql)
                return (name, result.model_dump())
            except ToolExecutionError as e:
                return (name, {"error": str(e)})

        tasks = [query_with_error_handling(name, promql) for name, promql in queries.items()]
        results = await asyncio.gather(*tasks)

        # Convert results to dict
        metrics_data = dict(results)

        # Count successful queries
        # Success: has "status" key (from PrometheusResult.model_dump())
        # Error: {"error": "message"} has no "status" key
        success_count = sum(1 for _, result in results if "status" in result)

        result = {
            "metrics_data": metrics_data,
            "attempted_agents": ["metrics_agent"],
            "messages": [
                AIMessage(
                    content=f"MetricsAgent collected {success_count}/{len(queries)} metrics for service '{service}'"
                )
            ],
        }

        agent_invocations_total.labels(agent_name="metrics_agent", status="success").inc()
        return result

    except Exception:
        agent_invocations_total.labels(agent_name="metrics_agent", status="error").inc()
        raise

    finally:
        agent_duration_seconds.labels(agent_name="metrics_agent").observe(
            time.monotonic() - start_time
        )
