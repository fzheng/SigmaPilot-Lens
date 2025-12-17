"""Signal ingestion endpoints.

This module provides the primary API endpoint for submitting trading signals
to SigmaPilot Lens for analysis. It handles:

1. Schema Validation: Validates incoming signals against Pydantic models
2. Rate Limiting: Applies per-client rate limits using Redis sliding window
3. Idempotency: Prevents duplicate processing via X-Idempotency-Key header
4. Persistence: Stores signal in PostgreSQL with initial 'queued' status
5. Enqueueing: Pushes signal to Redis Stream for async processing

Signal Flow:
    POST /signals → Validate → Rate Limit → Idempotency Check
                  → Generate event_id → Persist → Enqueue → Response

Response Headers:
    - X-RateLimit-Limit: Requests allowed per minute
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Window: Window size in seconds

Error Responses:
    - 400: Invalid request body (schema validation failed)
    - 403: Access denied (external network)
    - 429: Rate limit exceeded (Retry-After header included)
    - 500: Queue error (failed to enqueue signal)

Access: Restricted to internal Docker network only.
"""

import time
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.rate_limit import get_rate_limiter
from src.models.database import get_db_session
from src.models.orm.event import Event, ProcessingTimeline
from src.models.schemas.signal import (
    SignalSubmitRequest,
    SignalSubmitResponse,
)
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.queue import get_queue_producer

logger = get_logger(__name__)

router = APIRouter()


async def check_rate_limit(request: Request):
    """Dependency to check rate limit before processing request."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    try:
        rate_limiter = get_rate_limiter()
    except RuntimeError:
        # Rate limiter not initialized, skip check
        logger.warning("Rate limiter not initialized, skipping rate limit check")
        return

    # Use client IP or source from request as rate limit key
    client_host = request.client.host if request.client else "unknown"
    rate_limit_key = f"signals:{client_host}"

    is_allowed, remaining, retry_after = await rate_limiter.is_allowed(rate_limit_key)

    if not is_allowed:
        logger.warning(f"Rate limit exceeded for {client_host}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please try again later.",
                }
            },
            headers={"Retry-After": str(retry_after)},
        )


@router.post(
    "",
    response_model=SignalSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a trading signal",
    description="Submit a trading signal for AI analysis and evaluation. Access is restricted to internal Docker network only.",
)
async def submit_signal(
    signal: SignalSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    response: Response,
    request: Request,
    idempotency_key: Annotated[Optional[str], Header(alias="X-Idempotency-Key")] = None,
    _: None = Depends(check_rate_limit),
):
    """
    Submit a trading signal for analysis.

    The signal will be:
    1. Validated against the schema
    2. Assigned an event_id
    3. Persisted to the database
    4. Enqueued for enrichment and AI evaluation

    Returns the event_id for tracking.

    Rate limited to prevent abuse (configurable via RATE_LIMIT_* env vars).
    """
    start_time = time.time()
    received_at = datetime.now(timezone.utc)

    # Add rate limit headers to response
    if settings.RATE_LIMIT_ENABLED:
        try:
            rate_limiter = get_rate_limiter()
            client_host = request.client.host if request.client else "unknown"
            usage = await rate_limiter.get_usage(f"signals:{client_host}")
            response.headers["X-RateLimit-Limit"] = str(usage["limit"])
            response.headers["X-RateLimit-Remaining"] = str(usage["remaining"])
            response.headers["X-RateLimit-Window"] = str(usage["window_seconds"])
        except Exception:
            pass  # Don't fail request if rate limit headers can't be added

    # Check for idempotency
    if idempotency_key:
        existing = await db.execute(
            select(Event).where(Event.idempotency_key == idempotency_key)
        )
        existing_event = existing.scalar_one_or_none()
        if existing_event:
            logger.info(f"Duplicate signal detected: {existing_event.event_id}")
            return SignalSubmitResponse(
                event_id=existing_event.event_id,
                status=existing_event.status.upper(),
                received_at=existing_event.received_at,
            )

    # Generate event ID
    event_id = str(uuid4())

    # Record metrics
    metrics.record_signal_received(
        source=signal.source,
        symbol=signal.symbol,
        event_type=signal.event_type,
    )

    # Log receipt
    log_stage(logger, "RECEIVED", event_id, status="started", symbol=signal.symbol)

    # Create event record
    event = Event(
        event_id=event_id,
        idempotency_key=idempotency_key,
        event_type=signal.event_type,
        symbol=signal.symbol,
        signal_direction=signal.signal_direction,
        entry_price=float(signal.entry_price),
        size=float(signal.size),
        ts_utc=signal.ts_utc,
        source=signal.source,
        status="queued",
        feature_profile=settings.FEATURE_PROFILE,
        received_at=received_at,
        raw_payload=signal.model_dump(mode="json"),
    )

    # Add to database
    db.add(event)

    # Add timeline entry
    timeline_received = ProcessingTimeline(
        event_id=event_id,
        status="RECEIVED",
        details={"source": signal.source},
    )
    db.add(timeline_received)

    await db.commit()

    # Enqueue to Redis Stream
    try:
        producer = get_queue_producer()
        await producer.enqueue_signal(event_id, signal.model_dump(mode="json"))

        # Add enqueued timeline entry
        timeline_enqueued = ProcessingTimeline(
            event_id=event_id,
            status="ENQUEUED",
        )
        db.add(timeline_enqueued)
        await db.commit()

        log_stage(logger, "ENQUEUED", event_id, status="completed")

    except Exception as e:
        logger.error(f"Failed to enqueue signal {event_id}: {e}")
        # Update event status to failed
        event.status = "failed"

        # Create DLQ entry for enqueue failure
        try:
            from src.models.orm.dlq import DLQEntry

            dlq_entry = DLQEntry(
                event_id=event_id,
                stage="enqueue",
                reason_code=_classify_enqueue_error(str(e)),
                error_message=str(e)[:2000],
                payload=signal.model_dump(mode="json"),
            )
            db.add(dlq_entry)
        except Exception as dlq_err:
            logger.error(f"Failed to create DLQ entry for {event_id}: {dlq_err}")

        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "QUEUE_ERROR", "message": "Failed to enqueue signal"}},
        )

    # Record enqueue metrics
    duration = time.time() - start_time
    metrics.record_signal_enqueued(signal.symbol, duration)

    return SignalSubmitResponse(
        event_id=event_id,
        status="ENQUEUED",
        received_at=received_at,
    )


def _classify_enqueue_error(error_message: str) -> str:
    """Classify enqueue error message into a reason code."""
    error_lower = error_message.lower()
    if "timeout" in error_lower:
        return "timeout"
    if "connection" in error_lower or "refused" in error_lower:
        return "network_error"
    if "full" in error_lower or "capacity" in error_lower:
        return "queue_full"
    return "enqueue_error"
