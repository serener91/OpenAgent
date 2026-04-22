"""FastAPI application for the orchestrator service."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.observability.logging import setup_logging
from app.observability.tracing import setup_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    setup_tracing()
    yield


app = FastAPI(
    title="OpenAgent Orchestrator",
    description="Multi-agent orchestration system",
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

app.include_router(health.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "orchestrator",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }