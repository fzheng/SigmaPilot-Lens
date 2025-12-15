"""Health check endpoints."""

from fastapi import APIRouter, Response

from src.core.config import settings
from src.models.database import check_db_connection
from src.observability.logging import get_logger
from src.observability.metrics import metrics

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Liveness probe endpoint.

    Returns basic status - use this for container liveness checks.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe endpoint.

    Checks connectivity to all required dependencies.
    Returns 503 if any dependency is unhealthy.
    """
    checks = {}
    all_healthy = True

    # Check PostgreSQL
    try:
        db_ok = await check_db_connection()
        checks["postgres"] = "ok" if db_ok else "error"
        if not db_ok:
            all_healthy = False
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["postgres"] = "error"
        all_healthy = False

    # Check Redis
    try:
        from src.services.queue.redis_client import get_redis_client
        redis = get_redis_client()
        from src.services.queue import RedisClient
        client = RedisClient(redis)
        redis_ok = await client.ping()
        checks["redis"] = "ok" if redis_ok else "error"
        if not redis_ok:
            all_healthy = False
    except RuntimeError:
        # Redis not initialized yet
        checks["redis"] = "not_initialized"
        all_healthy = False
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = "error"
        all_healthy = False

    result = {
        "status": "ready" if all_healthy else "not_ready",
        "dependencies": checks,
    }

    if not all_healthy:
        return Response(
            content=str(result),
            status_code=503,
            media_type="application/json",
        )

    return result


@router.get("/queue/depth")
async def get_queue_depth():
    """
    Get current queue depths for monitoring.

    Returns the number of signals pending at each stage.
    """
    depths = {
        "pending": 0,
        "enriched": 0,
        "dlq": 0,
    }

    try:
        from src.services.queue.redis_client import get_redis_client
        from src.services.queue import RedisClient
        redis = get_redis_client()
        client = RedisClient(redis)

        depths["pending"] = await client.xlen("lens:signals:pending")
        depths["enriched"] = await client.xlen("lens:signals:enriched")
        depths["dlq"] = await client.xlen("lens:dlq")

        # Update metrics
        metrics.update_queue_depth("pending", depths["pending"])
        metrics.update_queue_depth("enriched", depths["enriched"])
        metrics.update_queue_depth("dlq", depths["dlq"])

    except RuntimeError:
        # Redis not initialized
        pass
    except Exception as e:
        logger.error(f"Failed to get queue depth: {e}")

    return {"queues": depths}


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns all metrics in Prometheus text format.
    """
    if not settings.METRICS_ENABLED:
        return Response(content="Metrics disabled", status_code=404)

    content = metrics.get_metrics()
    return Response(content=content, media_type="text/plain; charset=utf-8")
