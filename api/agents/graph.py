"""
LangGraph state graph for SentinelAI incident response.

Orchestrates 4 specialist agents (metrics, logs, runbooks, synthesis)
supervised by a coordinator, then updates the incident with the final report.
"""

import operator
import os
from typing import Annotated, Any, TypedDict
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession


class GraphState(TypedDict):
    """State passed between nodes in the agent graph."""

    incident_id: str
    trigger: str  # Human-readable description of the alert
    metrics_data: dict[str, Any]  # Filled by MetricsAgent
    log_data: list[str]  # Filled by LogAgent
    runbook_hits: list[dict[str, Any]]  # Filled by RunbookAgent
    final_report: str  # Filled by SynthesisAgent
    error: str | None  # Set if any node fails
    messages: Annotated[list[Any], operator.add]  # Accumulates all agent messages


async def supervisor(state: GraphState) -> dict[str, Any]:
    """Supervisor node - coordinates agent execution."""
    return {"messages": [HumanMessage(content="Supervisor coordinating agent execution")]}


def route_supervisor(state: GraphState) -> str:
    """
    Conditional routing function for supervisor node.

    Routes to:
    - metrics_agent if metrics_data is empty
    - log_agent if log_data is empty
    - runbook_agent if runbook_hits is empty
    - synthesis_agent if final_report is empty
    - incident_agent if all data is populated
    - END if incident_agent has completed
    """
    # Check if all specialist data is populated
    has_metrics = bool(state.get("metrics_data"))
    has_logs = bool(state.get("log_data"))
    has_runbooks = bool(state.get("runbook_hits"))
    has_report = bool(state.get("final_report"))

    # If all data collected and report generated, update incident
    if has_metrics and has_logs and has_runbooks and has_report:
        # Check if incident_agent already ran by looking at messages
        messages = state.get("messages", [])
        incident_agent_ran = any(
            "IncidentAgent updated incident" in str(msg.content) for msg in messages
        )

        if incident_agent_ran:
            return END
        return "incident_agent"

    # Route to next missing specialist agent
    if not has_metrics:
        return "metrics_agent"
    if not has_logs:
        return "log_agent"
    if not has_runbooks:
        return "runbook_agent"
    if not has_report:
        return "synthesis_agent"

    # Fallback to END (shouldn't reach here)
    return END


async def build_graph(session: AsyncSession) -> Any:
    """
    Build and compile the LangGraph with Redis checkpointing.

    Args:
        session: AsyncSession for database operations (injected into incident_agent)

    Returns:
        Compiled graph with Redis checkpointer attached
    """
    # Import agent implementations (deferred to avoid circular imports)
    from api.agents.incident_agent import make_incident_agent
    from api.agents.log_agent import log_agent
    from api.agents.metrics_agent import metrics_agent
    from api.agents.runbook_agent import runbook_agent
    from api.agents.synthesis_agent import synthesis_agent

    # Initialize Redis checkpointer
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    checkpointer = AsyncRedisSaver.from_conn_string(redis_url)

    # Create incident_agent with injected session
    incident_agent_node = make_incident_agent(session)

    # Build the workflow
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("metrics_agent", metrics_agent)
    workflow.add_node("log_agent", log_agent)
    workflow.add_node("runbook_agent", runbook_agent)
    workflow.add_node("synthesis_agent", synthesis_agent)
    workflow.add_node("incident_agent", incident_agent_node)  # type: ignore[arg-type]

    # Add edges
    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "metrics_agent": "metrics_agent",
            "log_agent": "log_agent",
            "runbook_agent": "runbook_agent",
            "synthesis_agent": "synthesis_agent",
            "incident_agent": "incident_agent",
            END: END,
        },
    )

    # All agents return to supervisor for coordination
    workflow.add_edge("metrics_agent", "supervisor")
    workflow.add_edge("log_agent", "supervisor")
    workflow.add_edge("runbook_agent", "supervisor")
    workflow.add_edge("synthesis_agent", "supervisor")
    workflow.add_edge("incident_agent", "supervisor")

    # Compile with Redis checkpointer
    return workflow.compile(checkpointer=checkpointer)  # type: ignore[arg-type]


# Module-level graph for tests (uses MemorySaver, not Redis)
def _build_test_graph() -> Any:
    """Build graph with MemorySaver checkpointer for testing."""
    # Import agent implementations (deferred to avoid circular imports)
    from api.agents.incident_agent import make_incident_agent
    from api.agents.log_agent import log_agent
    from api.agents.metrics_agent import metrics_agent
    from api.agents.runbook_agent import runbook_agent
    from api.agents.synthesis_agent import synthesis_agent

    # Create mock session for tests
    mock_session = AsyncMock(spec=AsyncSession)
    incident_agent_node = make_incident_agent(mock_session)

    # Build the workflow
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("metrics_agent", metrics_agent)
    workflow.add_node("log_agent", log_agent)
    workflow.add_node("runbook_agent", runbook_agent)
    workflow.add_node("synthesis_agent", synthesis_agent)
    workflow.add_node("incident_agent", incident_agent_node)  # type: ignore[arg-type]

    # Add edges
    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "metrics_agent": "metrics_agent",
            "log_agent": "log_agent",
            "runbook_agent": "runbook_agent",
            "synthesis_agent": "synthesis_agent",
            "incident_agent": "incident_agent",
            END: END,
        },
    )

    # All agents return to supervisor for coordination
    workflow.add_edge("metrics_agent", "supervisor")
    workflow.add_edge("log_agent", "supervisor")
    workflow.add_edge("runbook_agent", "supervisor")
    workflow.add_edge("synthesis_agent", "supervisor")
    workflow.add_edge("incident_agent", "supervisor")

    # Compile with MemorySaver checkpointer
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# Test graph instance (does not require Redis)
graph = _build_test_graph()
