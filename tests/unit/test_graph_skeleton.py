"""
Unit tests for LangGraph skeleton.

Verifies graph structure, routing logic, and stub execution.
"""

import pytest

from api.agents.graph import GraphState, graph, route_supervisor


class TestGraphState:
    """Tests for GraphState TypedDict."""

    def test_graph_state_structure(self) -> None:
        """Verify GraphState has all required fields."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        assert state["incident_id"] == "test-id"
        assert state["trigger"] == "Test alert"
        assert isinstance(state["metrics_data"], dict)
        assert isinstance(state["log_data"], list)
        assert isinstance(state["runbook_hits"], list)
        assert state["final_report"] == ""
        assert state["error"] is None
        assert isinstance(state["messages"], list)


class TestRouteSupervisor:
    """Tests for supervisor routing logic."""

    def test_routes_to_metrics_agent_when_no_metrics(self) -> None:
        """Verify supervisor routes to metrics_agent when metrics_data is empty."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        assert route_supervisor(state) == "metrics_agent"

    def test_routes_to_log_agent_when_no_logs(self) -> None:
        """Verify supervisor routes to log_agent when log_data is empty."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {"cpu": 90},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        assert route_supervisor(state) == "log_agent"

    def test_routes_to_runbook_agent_when_no_runbooks(self) -> None:
        """Verify supervisor routes to runbook_agent when runbook_hits is empty."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {"cpu": 90},
            "log_data": ["error log"],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        assert route_supervisor(state) == "runbook_agent"

    def test_routes_to_synthesis_agent_when_no_report(self) -> None:
        """Verify supervisor routes to synthesis_agent when final_report is empty."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {"cpu": 90},
            "log_data": ["error log"],
            "runbook_hits": [{"title": "Runbook 1"}],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        assert route_supervisor(state) == "synthesis_agent"

    def test_routes_to_incident_agent_when_all_data_populated(self) -> None:
        """Verify supervisor routes to incident_agent when all data is populated."""
        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {"cpu": 90},
            "log_data": ["error log"],
            "runbook_hits": [{"title": "Runbook 1"}],
            "final_report": "Final report content",
            "error": None,
            "messages": [],
        }

        assert route_supervisor(state) == "incident_agent"

    def test_routes_to_end_after_incident_agent_completes(self) -> None:
        """Verify supervisor routes to END after incident_agent has run."""
        from langchain_core.messages import HumanMessage

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {"cpu": 90},
            "log_data": ["error log"],
            "runbook_hits": [{"title": "Runbook 1"}],
            "final_report": "Final report content",
            "error": None,
            "messages": [HumanMessage(content="incident_agent stub called")],
        }

        assert route_supervisor(state) == "__end__"


class TestGraphStructure:
    """Tests for graph structure and compilation."""

    def test_graph_compiles_without_errors(self) -> None:
        """Verify graph compiles successfully."""
        assert graph is not None
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "ainvoke")

    @pytest.mark.asyncio
    async def test_graph_executes_metrics_agent_first(self) -> None:
        """Verify graph routes to metrics_agent on first execution."""
        initial_state: GraphState = {
            "incident_id": "test-incident",
            "trigger": "High CPU usage alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await graph.ainvoke(initial_state)  # type: ignore[arg-type]

        # Should have supervisor and metrics_agent messages
        assert len(result["messages"]) >= 2
        message_contents = [msg.content for msg in result["messages"]]
        assert "supervisor stub called" in message_contents
        assert "metrics_agent stub called" in message_contents

    @pytest.mark.asyncio
    async def test_graph_accumulates_messages(self) -> None:
        """Verify messages accumulate across multiple invocations."""
        from langchain_core.messages import HumanMessage

        initial_state: GraphState = {
            "incident_id": "test-incident",
            "trigger": "High CPU usage alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [HumanMessage(content="Initial message")],
        }

        result = await graph.ainvoke(initial_state)  # type: ignore[arg-type]

        # Should preserve initial message and add new ones
        message_contents = [msg.content for msg in result["messages"]]
        assert "Initial message" in message_contents
        assert len(result["messages"]) >= 2  # Initial + supervisor + agent


class TestGraphNodes:
    """Tests for individual graph nodes (stubs)."""

    @pytest.mark.asyncio
    async def test_supervisor_stub_returns_message(self) -> None:
        """Verify supervisor stub returns expected message."""
        from api.agents.graph import supervisor

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await supervisor(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "supervisor stub called"

    @pytest.mark.asyncio
    async def test_metrics_agent_stub_returns_message(self) -> None:
        """Verify metrics_agent stub returns expected message."""
        from api.agents.graph import metrics_agent

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await metrics_agent(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "metrics_agent stub called"

    @pytest.mark.asyncio
    async def test_log_agent_stub_returns_message(self) -> None:
        """Verify log_agent stub returns expected message."""
        from api.agents.graph import log_agent

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await log_agent(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "log_agent stub called"

    @pytest.mark.asyncio
    async def test_runbook_agent_stub_returns_message(self) -> None:
        """Verify runbook_agent stub returns expected message."""
        from api.agents.graph import runbook_agent

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await runbook_agent(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "runbook_agent stub called"

    @pytest.mark.asyncio
    async def test_synthesis_agent_stub_returns_message(self) -> None:
        """Verify synthesis_agent stub returns expected message."""
        from api.agents.graph import synthesis_agent

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await synthesis_agent(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "synthesis_agent stub called"

    @pytest.mark.asyncio
    async def test_incident_agent_stub_returns_message(self) -> None:
        """Verify incident_agent stub returns expected message."""
        from api.agents.graph import incident_agent

        state: GraphState = {
            "incident_id": "test-id",
            "trigger": "Test alert",
            "metrics_data": {},
            "log_data": [],
            "runbook_hits": [],
            "final_report": "",
            "error": None,
            "messages": [],
        }

        result = await incident_agent(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "incident_agent stub called"
