"""FastAPI + FastMCP gateway server."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mcp.server import Server

from app.config import settings
from app.observability.logging import setup_logging
from app.tool_registry import execute_tool, register_file_tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    register_file_tools()
    yield


app = FastAPI(
    title="MCP Gateway",
    description="MCP Gateway service with FastMCP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "mcp_gateway",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class ToolExecutionRequest(BaseModel):
    """Request model for tool execution."""

    tool_name: str
    arguments: dict[str, Any] = {}


class ToolExecutionResponse(BaseModel):
    """Response model for tool execution."""

    result: Any


@app.post("/tools/execute", response_model=ToolExecutionResponse)
async def tools_execute(request: ToolExecutionRequest) -> ToolExecutionResponse:
    """Execute a tool by name with arguments.

    Args:
        request: Tool execution request with tool_name and arguments

    Returns:
        Tool execution response with result
    """
    result = await execute_tool(request.tool_name, request.arguments)
    return ToolExecutionResponse(result=result)


# MCP Server instance - will be configured in future tasks
mcp_server = Server(name="mcp-gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    return app