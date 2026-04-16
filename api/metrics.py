"""
Prometheus metrics for SentinelAI.

Custom metrics for agent performance, incident tracking, and resolution times.
"""

from prometheus_client import Counter, Gauge, Histogram

# Agent invocation tracking
agent_invocations_total = Counter(
    "sentinelai_agent_invocations_total",
    "Total number of agent invocations",
    ["agent_name", "status"],
)

# Agent execution duration
agent_duration_seconds = Histogram(
    "sentinelai_agent_duration_seconds",
    "Time spent executing each agent node",
    ["agent_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# Active incidents gauge
active_incidents = Gauge(
    "sentinelai_active_incidents",
    "Number of currently active (open/investigating) incidents",
)

# Incident resolution time
resolution_time_seconds = Histogram(
    "sentinelai_resolution_time_seconds",
    "Time from incident creation to agent report completion",
    buckets=[30, 60, 120, 300, 600, 1800, 3600],
)
