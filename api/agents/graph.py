"""
LangGraph state graph for SentinelAI incident response.

Orchestrates 4 specialist agents (metrics, logs, runbooks, synthesis)
supervised by a coordinator, then updates the incident with the final report.
"""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph


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
    return {"messages": [HumanMessage(content="supervisor stub called")]}


async def metrics_agent(state: GraphState) -> dict[str, Any]:
    """Metrics agent node - queries Prometheus for metrics."""
    return {
        "metrics_data": {"stub": "placeholder metrics data"},
        "messages": [HumanMessage(content="metrics_agent stub called")],
    }


async def log_agent(state: GraphState) -> dict[str, Any]:
    """Log agent node - searches Loki for relevant logs."""
    return {
        "log_data": ["stub log entry 1", "stub log entry 2"],
        "messages": [HumanMessage(content="log_agent stub called")],
    }


async def runbook_agent(state: GraphState) -> dict[str, Any]:
    """Runbook agent node - searches vector DB for relevant runbooks."""
    return {
        "runbook_hits": [{"title": "Stub Runbook", "content": "Placeholder runbook content"}],
        "messages": [HumanMessage(content="runbook_agent stub called")],
    }


async def synthesis_agent(state: GraphState) -> dict[str, Any]:
    """Synthesis agent node - generates final incident report."""
    return {
        "final_report": "Stub final report: All data collected and synthesized",
        "messages": [HumanMessage(content="synthesis_agent stub called")],
    }


async def incident_agent(state: GraphState) -> dict[str, Any]:
    """Incident agent node - updates incident with final report."""
    return {"messages": [HumanMessage(content="incident_agent stub called")]}


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
            "incident_agent stub called" in str(msg.content) for msg in messages
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


# Build the graph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("supervisor", supervisor)
workflow.add_node("metrics_agent", metrics_agent)
workflow.add_node("log_agent", log_agent)
workflow.add_node("runbook_agent", runbook_agent)
workflow.add_node("synthesis_agent", synthesis_agent)
workflow.add_node("incident_agent", incident_agent)

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

# Compile the graph
graph = workflow.compile()
