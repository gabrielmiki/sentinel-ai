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
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

# Module-level checkpointer instance (initialized at startup)
_checkpointer: BaseCheckpointSaver | None = None


class GraphState(TypedDict):
    """State passed between nodes in the agent graph."""

    incident_id: str
    trigger: str  # Human-readable description of the alert
    metrics_data: dict[str, Any]  # Filled by MetricsAgent
    log_data: list[str]  # Filled by LogAgent
    runbook_hits: list[dict[str, Any]]  # Filled by RunbookAgent
    final_report: str  # Filled by SynthesisAgent
    incident_updated: bool  # Set to True by IncidentAgent when done (success or error)
    attempted_agents: Annotated[
        list[str], operator.add
    ]  # Track which agents have run (prevents retry loops)
    error: str | None  # Set if any node fails
    messages: Annotated[list[Any], operator.add]  # Accumulates all agent messages


async def supervisor(state: GraphState) -> dict[str, Any]:
    """Supervisor node - coordinates agent execution."""
    return {"messages": [HumanMessage(content="Supervisor coordinating agent execution")]}


def route_supervisor(state: GraphState) -> str:
    """
    Conditional routing function for supervisor node.

    Routes to:
    - metrics_agent if not yet attempted
    - log_agent if not yet attempted
    - runbook_agent if not yet attempted
    - synthesis_agent if all data collection agents have run
    - incident_agent if synthesis completed
    - END if incident_agent has completed

    Note: Agents are only attempted once. If they fail, the graph continues
    with whatever data was collected to produce a partial report.
    """
    # Track which agents have been attempted (prevents infinite retry loops)
    attempted = state.get("attempted_agents", [])

    # Check if all specialist data is populated
    has_metrics = bool(state.get("metrics_data"))
    has_logs = bool(state.get("log_data"))
    has_runbooks = bool(state.get("runbook_hits"))
    has_report = bool(state.get("final_report"))

    # Check if all data collection agents have been attempted
    all_collectors_attempted = all(
        agent in attempted for agent in ["metrics_agent", "log_agent", "runbook_agent"]
    )

    # If synthesis completed and incident updated, we're done
    if has_report and state.get("incident_updated"):
        return END

    # If all collectors ran and synthesis completed, update incident
    if all_collectors_attempted and has_report:
        if "incident_agent" not in attempted:
            return "incident_agent"
        return END

    # If all collectors ran, generate synthesis (even with partial data)
    if all_collectors_attempted:
        if "synthesis_agent" not in attempted:
            return "synthesis_agent"
        # Synthesis failed or produced empty report, still update incident
        if "incident_agent" not in attempted:
            return "incident_agent"
        return END

    # Route to next unattempted data collection agent
    if "metrics_agent" not in attempted:
        return "metrics_agent"
    if "log_agent" not in attempted:
        return "log_agent"
    if "runbook_agent" not in attempted:
        return "runbook_agent"

    # Fallback: all agents attempted but we shouldn't reach here
    return END


async def initialize_checkpointer() -> None:
    """
    Initialize the checkpointer at application startup.

    Currently uses MemorySaver (in-memory checkpointing).
    TODO: Switch to AsyncRedisSaver when Redis Stack is available.
    """
    global _checkpointer

    # Use MemorySaver for now (no Redis Stack required)
    # Checkpoints won't persist across restarts, but functionality works
    _checkpointer = MemorySaver()


async def cleanup_checkpointer() -> None:
    """Clean up the checkpointer at application shutdown."""
    global _checkpointer

    # MemorySaver doesn't require cleanup, just reset the reference
    _checkpointer = None


async def build_graph(session: AsyncSession) -> Any:
    """
    Build and compile the LangGraph with Redis checkpointing.

    Args:
        session: AsyncSession for database operations (injected into incident_agent)

    Returns:
        Compiled graph with Redis checkpointer attached

    Raises:
        RuntimeError: If checkpointer not initialized (call initialize_checkpointer at startup)
    """
    global _checkpointer

    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialized. Call initialize_checkpointer() at application startup."
        )

    # Import agent implementations (deferred to avoid circular imports)
    from api.agents.incident_agent import make_incident_agent
    from api.agents.log_agent import log_agent
    from api.agents.metrics_agent import metrics_agent
    from api.agents.runbook_agent import runbook_agent
    from api.agents.synthesis_agent import synthesis_agent

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

    # Compile with global Redis checkpointer
    return workflow.compile(checkpointer=_checkpointer)  # type: ignore[arg-type]


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
