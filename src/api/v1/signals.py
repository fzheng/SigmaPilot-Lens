"""Signal ingestion endpoints."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status

from src.api.deps import RateLimitedKey
from src.models.schemas.signal import (
    SignalSubmitRequest,
    SignalSubmitResponse,
)

router = APIRouter()


@router.post(
    "",
    response_model=SignalSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a trading signal",
    description="Submit a trading signal for AI analysis and evaluation.",
)
async def submit_signal(
    signal: SignalSubmitRequest,
    key_info: RateLimitedKey,
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
    event_id = str(uuid4())
    received_at = datetime.now(timezone.utc)

    # TODO: Persist to database
    # TODO: Enqueue to Redis Stream

    return SignalSubmitResponse(
        event_id=event_id,
        status="ENQUEUED",
        received_at=received_at,
    )
