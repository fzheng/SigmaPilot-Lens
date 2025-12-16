"""Event query endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query

from src.models.schemas.signal import EventListResponse, EventDetailResponse

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
):
    """
    List events with optional filters.

    Supports filtering by symbol, event_type, source, status, and time range.
    """
    # TODO: Implement database query
    return EventListResponse(
        items=[],
        total=0,
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
):
    """
    Get full details of an event.

    Includes:
    - Original signal data
    - Processing timeline
    - Enrichment summary
    - All model decisions
    """
    # TODO: Implement database query
    raise NotImplementedError("Event query not implemented yet")


@router.get(
    "/{event_id}/status",
    summary="Get event status",
    description="Get the current processing status of an event. Access is restricted to internal Docker network only.",
)
async def get_event_status(
    event_id: str,
):
    """
    Get the current processing status of an event.

    Returns the current stage and overall duration.
    """
    # TODO: Implement status lookup
    return {
        "event_id": event_id,
        "status": "UNKNOWN",
        "current_stage": "UNKNOWN",
        "duration_ms": 0,
    }
