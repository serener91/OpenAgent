"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, status

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
)
async def health():
    """Liveness probe endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
)
async def ready():
    """Readiness probe endpoint."""
    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }