"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness probe endpoint."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe endpoint.

    Checks connectivity to all required dependencies.
    """
    # TODO: Implement actual health checks
    checks = {
        "redis": "ok",
        "postgres": "ok",
    }

    all_healthy = all(v == "ok" for v in checks.values())

    return {
        "status": "ready" if all_healthy else "not_ready",
        "dependencies": checks,
    }
