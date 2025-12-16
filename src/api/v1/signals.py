"""Signal ingestion endpoints."""

import time
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
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
    idempotency_key: Annotated[Optional[str], Header(alias="X-Idempotency-Key")] = None,
):
    """
    Submit a trading signal for analysis.

    The signal will be:
    1. Validated against the schema
    2. Assigned an event_id
    3. Persisted to the database
    4. Enqueued for enrichment and AI evaluation

    Returns the event_id for tracking.
    """
    start_time = time.time()
    received_at = datetime.now(timezone.utc)

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
