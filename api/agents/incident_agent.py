"""
Incident agent node for LangGraph.

Updates incident record with final agent report.
"""

import json
from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import AIMessage
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.agents.graph import GraphState
from api.models.incident import Incident


def make_incident_agent(
    session: AsyncSession,
) -> Callable[[GraphState], Coroutine[Any, Any, dict[str, Any]]]:
    """
    Factory function to create incident_agent with injected session.

    Args:
        session: AsyncSession for database operations

    Returns:
        Async function that updates incident with final report
    """

    async def incident_agent(state: GraphState) -> dict[str, Any]:
        """
        Incident agent node - updates incident record with final report.

        Parses final_report JSON to extract severity_assessment, then updates
        the incident record with status, agent_report, and severity.

        Args:
            state: Current graph state with final_report and incident_id

        Returns:
            Updated state with messages
        """
        incident_id = state["incident_id"]
        final_report = state["final_report"]

        try:
            # Parse final_report to extract severity_assessment
            report_data = json.loads(final_report)
            severity_assessment = report_data.get("severity_assessment", "medium")

            # Update incident record
            stmt = (
                update(Incident)
                .where(Incident.id == incident_id)
                .values(
                    status="investigated",
                    agent_report=final_report,
                    severity=severity_assessment,
                )
            )

            await session.execute(stmt)
            await session.commit()

            return {
                "messages": [
                    AIMessage(
                        content=f"IncidentAgent updated incident {incident_id} with final report"
                    )
                ],
            }

        except json.JSONDecodeError as e:
            # Fallback: save report as-is without updating severity
            stmt = (
                update(Incident)
                .where(Incident.id == incident_id)
                .values(
                    status="investigated",
                    agent_report=final_report,
                )
            )

            await session.execute(stmt)
            await session.commit()

            return {
                "error": f"Failed to parse final_report as JSON: {str(e)}",
                "messages": [
                    AIMessage(
                        content=f"IncidentAgent updated incident {incident_id} (JSON parse error)"
                    )
                ],
            }

        except Exception as e:
            # Rollback on unexpected errors
            await session.rollback()

            return {
                "error": str(e),
                "messages": [
                    AIMessage(content=f"IncidentAgent failed to update incident: {str(e)}")
                ],
            }

    return incident_agent
