"""
Metrics agent node for LangGraph.

Queries Prometheus for service metrics related to the incident.
"""

import asyncio
import re
from typing import Any

from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
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
    service = extract_service_name(state["trigger"])

    # Build PromQL queries for the service
    queries = {
        "request_rate": f'rate(http_requests_total{{service="{service}"}}[5m])',
        "error_rate": f'rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])',
        "p99_latency": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))',
        "cpu_usage": f'rate(process_cpu_seconds_total{{service="{service}"}}[5m])',
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

    return {
        "metrics_data": metrics_data,
        "messages": [
            AIMessage(
                content=f"MetricsAgent collected {success_count}/{len(queries)} metrics for service '{service}'"
            )
        ],
    }
