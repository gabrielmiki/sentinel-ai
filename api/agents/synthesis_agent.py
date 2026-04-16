"""
Synthesis agent node for LangGraph.

Uses LLM to analyze collected metrics, logs, and runbooks to generate
a structured incident report.
"""

import json
import os
import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from api.agents.graph import GraphState
from api.metrics import agent_duration_seconds, agent_invocations_total

SYSTEM_PROMPT = """You are an SRE incident analyst. Given metrics, logs, and runbook context, produce a structured incident report as valid JSON with exactly these keys: summary (str, max 2 sentences), root_cause_hypothesis (str), affected_components (list[str]), recommended_actions (list[str], max 5), severity_assessment (one of: low/medium/high/critical). Respond with JSON only, no markdown fences."""


def _format_metrics(metrics_data: dict[str, Any]) -> str:
    """
    Format metrics data showing only anomalous values.

    Args:
        metrics_data: Metrics data from MetricsAgent

    Returns:
        Formatted string of metrics with results
    """
    lines = []
    for metric_name, metric_value in metrics_data.items():
        # Check if metric has data (successful query)
        if "status" in metric_value and "data" in metric_value:
            data = metric_value["data"]
            if data and "result" in data and len(data["result"]) > 0:
                lines.append(f"- {metric_name}: {len(data['result'])} data points")
        elif "error" in metric_value:
            lines.append(f"- {metric_name}: Error - {metric_value['error']}")

    return "\n".join(lines) if lines else "No metrics data available"


def _format_logs(log_data: list[str]) -> str:
    """
    Format log entries (first 10).

    Args:
        log_data: List of log messages

    Returns:
        Formatted string of log entries
    """
    if not log_data:
        return "No log data available"

    # Take first 10 entries
    top_logs = log_data[:10]
    lines = [f"{i + 1}. {log}" for i, log in enumerate(top_logs)]
    return "\n".join(lines)


def _format_runbooks(runbook_hits: list[dict[str, Any]]) -> str:
    """
    Format runbook hits showing title and first 200 chars.

    Args:
        runbook_hits: List of runbook dicts from RunbookAgent

    Returns:
        Formatted string of runbooks
    """
    if not runbook_hits:
        return "No runbooks found"

    lines = []
    for i, runbook in enumerate(runbook_hits, 1):
        title = runbook.get("title", "Untitled")
        content = runbook.get("content", "")
        preview = content[:200] + "..." if len(content) > 200 else content
        lines.append(f"{i}. {title}\n   {preview}")

    return "\n\n".join(lines)


def _build_user_message(state: GraphState) -> str:
    """
    Build user message combining all incident context.

    Args:
        state: Current graph state with all collected data

    Returns:
        Formatted user message string
    """
    metrics_summary = _format_metrics(state["metrics_data"])
    logs_summary = _format_logs(state["log_data"])
    runbooks_summary = _format_runbooks(state["runbook_hits"])

    return f"""Incident Trigger:
{state["trigger"]}

Metrics Analysis:
{metrics_summary}

Recent Logs:
{logs_summary}

Relevant Runbooks:
{runbooks_summary}

Generate a structured incident report in JSON format."""


async def synthesis_agent(state: GraphState) -> dict[str, Any]:
    """
    Synthesis agent node - generates final incident report using LLM.

    Analyzes metrics, logs, and runbooks to produce a structured JSON report
    with summary, root cause hypothesis, affected components, recommended
    actions, and severity assessment.

    Args:
        state: Current graph state with metrics, logs, and runbooks

    Returns:
        Updated state with final_report and messages
    """
    start_time = time.monotonic()
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # Fallback report when API key not configured
            fallback_report = {
                "summary": "Analysis failed: Anthropic API key not configured",
                "root_cause_hypothesis": "Configuration error",
                "affected_components": ["unknown"],
                "recommended_actions": ["Configure ANTHROPIC_API_KEY environment variable"],
                "severity_assessment": "medium",
            }
            result = {
                "final_report": json.dumps(fallback_report),
                "attempted_agents": ["synthesis_agent"],
                "messages": [
                    AIMessage(content="SynthesisAgent generated fallback report (no API key)")
                ],
            }
            agent_invocations_total.labels(agent_name="synthesis_agent", status="success").inc()
            return result

        # Initialize LLM
        llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)  # type: ignore[call-arg]

        # Build messages
        user_message = _build_user_message(state)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]

        try:
            # First attempt
            response = await llm.ainvoke(messages)
            content = (
                response.content if isinstance(response.content, str) else str(response.content)
            )
            parsed_report = json.loads(content)

            result = {
                "final_report": json.dumps(parsed_report),
                "attempted_agents": ["synthesis_agent"],
                "messages": [AIMessage(content="SynthesisAgent generated incident report")],
            }
            agent_invocations_total.labels(agent_name="synthesis_agent", status="success").inc()
            return result

        except json.JSONDecodeError:
            # Retry with correction prompt
            try:
                correction_message = HumanMessage(
                    content="Your previous response was not valid JSON. Please respond with ONLY valid JSON, no markdown fences or additional text."
                )
                messages.append(response)
                messages.append(correction_message)

                retry_response = await llm.ainvoke(messages)
                retry_content = (
                    retry_response.content
                    if isinstance(retry_response.content, str)
                    else str(retry_response.content)
                )
                parsed_report = json.loads(retry_content)

                result = {
                    "final_report": json.dumps(parsed_report),
                    "attempted_agents": ["synthesis_agent"],
                    "messages": [
                        AIMessage(content="SynthesisAgent generated incident report (retry)")
                    ],
                }
                agent_invocations_total.labels(agent_name="synthesis_agent", status="success").inc()
                return result

            except json.JSONDecodeError:
                # Fallback report with raw response
                fallback_report = {
                    "summary": "Analysis failed",
                    "root_cause_hypothesis": "LLM parsing error",
                    "affected_components": ["unknown"],
                    "recommended_actions": [f"Raw LLM response: {retry_response.content[:200]}"],
                    "severity_assessment": "medium",
                }

                result = {
                    "final_report": json.dumps(fallback_report),
                    "attempted_agents": ["synthesis_agent"],
                    "messages": [
                        AIMessage(
                            content="SynthesisAgent generated fallback report (parsing failed)"
                        )
                    ],
                }
                agent_invocations_total.labels(agent_name="synthesis_agent", status="success").inc()
                return result

    except Exception as e:
        agent_invocations_total.labels(agent_name="synthesis_agent", status="error").inc()
        # Unexpected error fallback
        fallback_report = {
            "summary": "Analysis failed",
            "root_cause_hypothesis": f"Unexpected error: {str(e)}",
            "affected_components": ["unknown"],
            "recommended_actions": ["Review agent logs", "Check LLM configuration"],
            "severity_assessment": "medium",
        }

        return {
            "final_report": json.dumps(fallback_report),
            "attempted_agents": ["synthesis_agent"],
            "error": str(e),
            "messages": [AIMessage(content=f"SynthesisAgent encountered error: {str(e)}")],
        }

    finally:
        agent_duration_seconds.labels(agent_name="synthesis_agent").observe(
            time.monotonic() - start_time
        )
