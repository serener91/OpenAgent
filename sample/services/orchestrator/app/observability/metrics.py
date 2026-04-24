from fastapi import APIRouter, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "orchestrator_requests_total",
    ["endpoint", "method", "status"],
)

ACTIVE_REQUESTS = Gauge(
    "orchestrator_requests_active",
    [],
)

AGENT_TASK_COUNT = Counter(
    "agent_tasks_total",
    ["agent_name", "status"],
)

AGENT_TASK_DURATION = Histogram(
    "agent_tasks_duration_seconds",
    ["agent_name"],
)

MCP_TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    ["tool_name", "status"],
)

MCP_TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    ["tool_name"],
)

ACTIVE_SESSIONS = Gauge(
    "session_active",
    [],
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)