"""FastAPI + FastMCP gateway server."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import Server

from app.config import settings
from app.observability.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
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


# MCP Server instance - will be configured in future tasks
mcp_server = Server(name="mcp-gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    return app