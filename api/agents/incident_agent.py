"""
Incident agent node for LangGraph.

Updates incident record with final agent report.
"""

import json
import time
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.agents.graph import GraphState
from api.metrics import agent_duration_seconds, agent_invocations_total, resolution_time_seconds
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
        start_time = time.monotonic()
        try:
            # Convert incident_id from str to UUID for SQLAlchemy ORM
            incident_id = uuid.UUID(state["incident_id"])
            final_report = state["final_report"]

            try:
                # Parse final_report to extract severity_assessment
                report_data = json.loads(final_report)
                severity_assessment = report_data.get("severity_assessment", "medium")

                # Fetch incident created_at for resolution time metric
                query_created = select(Incident.created_at).where(Incident.id == incident_id)
                result_created = await session.execute(query_created)
                created_at = result_created.scalar_one_or_none()

                # Record resolution time
                if created_at:
                    resolution_seconds = (datetime.now() - created_at).total_seconds()
                    resolution_time_seconds.observe(resolution_seconds)

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

                result = {
                    "incident_updated": True,
                    "attempted_agents": ["incident_agent"],
                    "messages": [
                        AIMessage(
                            content=f"IncidentAgent updated incident {incident_id} with final report"
                        )
                    ],
                }
                agent_invocations_total.labels(agent_name="incident_agent", status="success").inc()
                return result

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

                result = {
                    "incident_updated": True,
                    "attempted_agents": ["incident_agent"],
                    "error": f"Failed to parse final_report as JSON: {str(e)}",
                    "messages": [
                        AIMessage(
                            content=f"IncidentAgent updated incident {incident_id} (JSON parse error)"
                        )
                    ],
                }
                agent_invocations_total.labels(agent_name="incident_agent", status="success").inc()
                return result

        except Exception as e:
            agent_invocations_total.labels(agent_name="incident_agent", status="error").inc()
            # Rollback on unexpected errors
            await session.rollback()

            return {
                "incident_updated": True,
                "attempted_agents": ["incident_agent"],
                "error": str(e),
                "messages": [
                    AIMessage(content=f"IncidentAgent failed to update incident: {str(e)}")
                ],
            }

        finally:
            agent_duration_seconds.labels(agent_name="incident_agent").observe(
                time.monotonic() - start_time
            )

    return incident_agent
