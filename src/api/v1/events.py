"""Event query endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.database import get_db_session
from src.models.orm.event import Event, EnrichedEvent, ProcessingTimeline
from src.models.orm.decision import ModelDecision
from src.models.schemas.signal import (
    EventListResponse,
    EventDetailResponse,
    EventSummary,
    TimelineEntry,
    DecisionSummary,
    EnrichedSummary,
)

router = APIRouter()


@router.get(
    "",
    response_model=EventListResponse,
    summary="List events",
    description="Retrieve a list of submitted events with optional filters. Access is restricted to internal Docker network only.",
)
async def list_events(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    source: Optional[str] = Query(None, description="Filter by source"),
    status: Optional[str] = Query(None, description="Filter by status"),
    since: Optional[datetime] = Query(None, description="Events after this time"),
    until: Optional[datetime] = Query(None, description="Events before this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    List events with optional filters.

    Supports filtering by symbol, event_type, source, status, and time range.
    """
    # Build query with filters
    query = select(Event)

    if symbol:
        query = query.where(Event.symbol == symbol.upper())
    if event_type:
        query = query.where(Event.event_type == event_type)
    if source:
        query = query.where(Event.source == source)
    if status:
        query = query.where(Event.status == status)
    if since:
        query = query.where(Event.received_at >= since)
    if until:
        query = query.where(Event.received_at <= until)

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(Event.received_at.desc()).offset(offset).limit(limit)

    # Execute query
    result = await db.execute(query)
    events = result.scalars().all()

    # Convert to response schema
    items = [
        EventSummary(
            event_id=e.event_id,
            event_type=e.event_type,
            symbol=e.symbol,
            signal_direction=e.signal_direction,
            entry_price=Decimal(str(e.entry_price)),
            size=Decimal(str(e.size)),
            status=e.status,
            source=e.source,
            received_at=e.received_at,
        )
        for e in events
    ]

    return EventListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{event_id}",
    response_model=EventDetailResponse,
    summary="Get event details",
    description="Retrieve full details of a specific event including timeline and decisions. Access is restricted to internal Docker network only.",
)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get full details of an event.

    Includes:
    - Original signal data
    - Processing timeline
    - Enrichment summary
    - All model decisions
    """
    # Query event with relationships
    query = (
        select(Event)
        .where(Event.event_id == event_id)
        .options(
            selectinload(Event.timeline),
            selectinload(Event.enriched),
            selectinload(Event.decisions),
        )
    )
    result = await db.execute(query)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Build timeline entries
    timeline = [
        TimelineEntry(
            status=t.status,
            timestamp=t.timestamp,
            details=t.details,
        )
        for t in sorted(event.timeline, key=lambda x: x.timestamp)
    ]

    # Build enriched summary
    enriched_summary = None
    if event.enriched:
        enriched_summary = EnrichedSummary(
            feature_profile=event.enriched.feature_profile,
            quality_flags=event.enriched.quality_flags or {},
        )

    # Build decision summaries
    decisions = [
        DecisionSummary(
            model=d.model_name,
            decision=d.decision,
            confidence=float(d.confidence),
        )
        for d in event.decisions
    ]

    return EventDetailResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        symbol=event.symbol,
        signal_direction=event.signal_direction,
        entry_price=Decimal(str(event.entry_price)),
        size=Decimal(str(event.size)),
        ts_utc=event.ts_utc,
        source=event.source,
        received_at=event.received_at,
        status=event.status,
        timeline=timeline,
        enriched=enriched_summary,
        decisions=decisions,
    )


@router.get(
    "/{event_id}/status",
    summary="Get event status",
    description="Get the current processing status of an event. Access is restricted to internal Docker network only.",
)
async def get_event_status(
    event_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get the current processing status of an event.

    Returns the current stage and overall duration.
    """
    # Query event
    query = select(Event).where(Event.event_id == event_id)
    result = await db.execute(query)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Calculate duration from received_at to now or published_at
    end_time = event.published_at or datetime.now(event.received_at.tzinfo)
    duration_ms = int((end_time - event.received_at).total_seconds() * 1000)

    # Determine current stage based on status
    stage_map = {
        "queued": "ENQUEUED",
        "enriched": "ENRICHED",
        "evaluated": "EVALUATED",
        "published": "PUBLISHED",
        "failed": "FAILED",
        "dlq": "DLQ",
        "rejected": "REJECTED",
    }
    current_stage = stage_map.get(event.status, event.status.upper())

    return {
        "event_id": event_id,
        "status": event.status,
        "current_stage": current_stage,
        "duration_ms": duration_ms,
        "received_at": event.received_at.isoformat(),
        "enriched_at": event.enriched_at.isoformat() if event.enriched_at else None,
        "evaluated_at": event.evaluated_at.isoformat() if event.evaluated_at else None,
        "published_at": event.published_at.isoformat() if event.published_at else None,
    }
