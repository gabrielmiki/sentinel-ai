"""
Runbook agent node for LangGraph.

Performs semantic search on runbook vector database to find relevant documentation.
"""

from typing import Any

from langchain_core.messages import AIMessage

from api.agents.graph import GraphState
from api.tools.runbooks import _search_runbooks


def _build_search_query(state: GraphState) -> str:
    """
    Build semantic search query from incident context.

    Combines:
    - Trigger string
    - Top 3 error messages from logs
    - Metric names with anomalies (values > 0)

    Args:
        state: Current graph state

    Returns:
        Combined search query string
    """
    query_parts = [state["trigger"]]

    # Add top 3 error messages from logs
    if state.get("log_data"):
        top_errors = state["log_data"][:3]
        query_parts.extend(top_errors)

    # Add metric names that show anomalies
    if state.get("metrics_data"):
        for metric_name, metric_data in state["metrics_data"].items():
            # Check if metric shows anomaly (has data with non-zero values)
            if "status" in metric_data and "data" in metric_data:
                data = metric_data["data"]
                if data and "result" in data and len(data["result"]) > 0:
                    # Has results, add metric name to query
                    query_parts.append(metric_name)

    return " ".join(query_parts)


async def runbook_agent(state: GraphState) -> dict[str, Any]:
    """
    Runbook agent node - searches vector DB for relevant runbooks.

    Builds semantic search query from incident context and searches
    runbook embeddings for relevant documentation.

    Args:
        state: Current graph state with incident details, logs, and metrics

    Returns:
        Updated state with runbook_hits and messages
    """
    # Build search query from context
    search_query = _build_search_query(state)

    try:
        # Search runbooks
        documents = await _search_runbooks(search_query, k=3)

        # Convert documents to dicts
        runbook_hits = []
        for doc in documents:
            runbook_hits.append(
                {
                    "title": doc.metadata.get("title", "Untitled"),
                    "content": doc.page_content,
                    "score": doc.metadata.get("score", 0.0),
                }
            )

        if runbook_hits:
            message_content = f"RunbookAgent found {len(runbook_hits)} relevant runbooks"
        else:
            message_content = "RunbookAgent found no relevant runbooks"

        return {
            "runbook_hits": runbook_hits,
            "messages": [AIMessage(content=message_content)],
        }

    except Exception as e:
        # Empty results are not failures, but tool errors are
        return {
            "runbook_hits": [],
            "error": str(e),
            "messages": [AIMessage(content=f"RunbookAgent search failed: {str(e)}")],
        }
