"""Dead Letter Queue (DLQ) management endpoints."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db_session
from src.models.orm.dlq import DLQEntry
from src.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# Response schemas
class DLQEntrySummary(BaseModel):
    """DLQ entry summary for list views."""

    id: str
    event_id: Optional[str]
    stage: str
    reason_code: str
    error_message: str
    retry_count: int
    created_at: datetime
    resolved_at: Optional[datetime] = None


class DLQEntryDetail(BaseModel):
    """Full DLQ entry details."""

    id: str
    event_id: Optional[str]
    stage: str
    reason_code: str
    error_message: str
    payload: dict
    retry_count: int
    last_retry_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    created_at: datetime


class DLQListResponse(BaseModel):
    """Response schema for DLQ list endpoint."""

    items: List[DLQEntrySummary]
    total: int
    limit: int
    offset: int


class DLQRetryResponse(BaseModel):
    """Response schema for DLQ retry endpoint."""

    id: str
    status: str
    message: str
    retry_count: int


class DLQResolveRequest(BaseModel):
    """Request schema for resolving a DLQ entry."""

    resolution_note: str = Field(..., min_length=1, max_length=1000)


class DLQResolveResponse(BaseModel):
    """Response schema for DLQ resolve endpoint."""

    id: str
    status: str
    resolved_at: datetime


@router.get(
    "",
    response_model=DLQListResponse,
    summary="List DLQ entries",
    description="Query dead letter queue entries with optional filters. Access is restricted to internal Docker network only.",
)
async def list_dlq_entries(
    stage: Optional[str] = Query(None, description="Filter by stage (enqueue|enrich|evaluate|publish)"),
    reason_code: Optional[str] = Query(None, description="Filter by reason code"),
    event_id: Optional[str] = Query(None, description="Filter by event ID"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status (null=all, true=resolved, false=unresolved)"),
    since: Optional[datetime] = Query(None, description="Entries after this time"),
    until: Optional[datetime] = Query(None, description="Entries before this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Query DLQ entries.

    Supports filtering by stage, reason_code, event_id, resolution status, and time range.
    """
    # Build query with filters
    query = select(DLQEntry)

    if stage:
        query = query.where(DLQEntry.stage == stage)
    if reason_code:
        query = query.where(DLQEntry.reason_code == reason_code)
    if event_id:
        query = query.where(DLQEntry.event_id == event_id)
    if resolved is not None:
        if resolved:
            query = query.where(DLQEntry.resolved_at.is_not(None))
        else:
            query = query.where(DLQEntry.resolved_at.is_(None))
    if since:
        query = query.where(DLQEntry.created_at >= since)
    if until:
        query = query.where(DLQEntry.created_at <= until)

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(DLQEntry.created_at.desc()).offset(offset).limit(limit)

    # Execute query
    result = await db.execute(query)
    entries = result.scalars().all()

    # Convert to response schema
    items = [
        DLQEntrySummary(
            id=str(e.id),
            event_id=e.event_id,
            stage=e.stage,
            reason_code=e.reason_code,
            error_message=e.error_message[:200] if len(e.error_message) > 200 else e.error_message,
            retry_count=e.retry_count,
            created_at=e.created_at,
            resolved_at=e.resolved_at,
        )
        for e in entries
    ]

    return DLQListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{dlq_id}",
    response_model=DLQEntryDetail,
    summary="Get DLQ entry details",
    description="Retrieve full details of a specific DLQ entry. Access is restricted to internal Docker network only.",
)
async def get_dlq_entry(
    dlq_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get full details of a DLQ entry.

    Includes the full payload for debugging and potential replay.
    """
    # Parse UUID
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid DLQ entry ID format")

    # Query DLQ entry
    query = select(DLQEntry).where(DLQEntry.id == dlq_uuid)
    result = await db.execute(query)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry {dlq_id} not found")

    return DLQEntryDetail(
        id=str(entry.id),
        event_id=entry.event_id,
        stage=entry.stage,
        reason_code=entry.reason_code,
        error_message=entry.error_message,
        payload=entry.payload,
        retry_count=entry.retry_count,
        last_retry_at=entry.last_retry_at,
        resolved_at=entry.resolved_at,
        resolution_note=entry.resolution_note,
        created_at=entry.created_at,
    )


@router.post(
    "/{dlq_id}/retry",
    response_model=DLQRetryResponse,
    summary="Retry a DLQ entry",
    description="Attempt to re-process a failed DLQ entry. Access is restricted to internal Docker network only.",
)
async def retry_dlq_entry(
    dlq_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Retry processing a DLQ entry.

    Increments the retry counter and attempts to re-enqueue the payload
    for processing based on the original stage.
    """
    # Parse UUID
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid DLQ entry ID format")

    # Query DLQ entry
    query = select(DLQEntry).where(DLQEntry.id == dlq_uuid)
    result = await db.execute(query)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry {dlq_id} not found")

    # Check if already resolved
    if entry.resolved_at:
        raise HTTPException(
            status_code=400,
            detail="Cannot retry a resolved DLQ entry"
        )

    # Update retry count and timestamp
    entry.retry_count += 1
    entry.last_retry_at = datetime.utcnow()

    # Attempt to re-enqueue based on stage
    try:
        if entry.stage == "enqueue":
            # Re-enqueue to pending signals
            from src.services.queue import get_queue_producer
            producer = get_queue_producer()
            if entry.event_id:
                await producer.enqueue_signal(entry.event_id, entry.payload)
            else:
                raise ValueError("No event_id for enqueue retry")

        elif entry.stage == "enrich":
            # Re-enqueue to pending signals (will go through enrichment again)
            from src.services.queue import get_queue_producer
            producer = get_queue_producer()
            if entry.event_id:
                await producer.enqueue_signal(entry.event_id, entry.payload)
            else:
                raise ValueError("No event_id for enrichment retry")

        elif entry.stage == "evaluate":
            # Re-enqueue to enriched queue
            from src.services.queue import get_queue_producer
            producer = get_queue_producer()
            if entry.event_id:
                await producer.enqueue_enriched(entry.event_id, entry.payload)
            else:
                raise ValueError("No event_id for evaluation retry")

        elif entry.stage == "publish":
            # Re-publish via WebSocket
            from src.services.publisher import get_publisher
            publisher = get_publisher()
            if entry.event_id:
                await publisher.publish(entry.event_id, entry.payload)
            else:
                raise ValueError("No event_id for publish retry")

        else:
            raise ValueError(f"Unknown stage: {entry.stage}")

        await db.commit()
        logger.info(f"DLQ entry {dlq_id} retry #{entry.retry_count} enqueued successfully")

        return DLQRetryResponse(
            id=str(entry.id),
            status="retrying",
            message=f"Entry re-enqueued for {entry.stage} processing",
            retry_count=entry.retry_count,
        )

    except Exception as e:
        await db.commit()  # Still save the retry count update
        logger.error(f"DLQ retry failed for {dlq_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Retry failed: {str(e)}"
        )


@router.post(
    "/{dlq_id}/resolve",
    response_model=DLQResolveResponse,
    summary="Mark a DLQ entry as resolved",
    description="Mark a DLQ entry as resolved (manually handled). Access is restricted to internal Docker network only.",
)
async def resolve_dlq_entry(
    dlq_id: str,
    request: DLQResolveRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Mark a DLQ entry as resolved.

    Use this when manually handling a failed entry or when the issue
    has been addressed outside the normal retry flow.
    """
    # Parse UUID
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid DLQ entry ID format")

    # Query DLQ entry
    query = select(DLQEntry).where(DLQEntry.id == dlq_uuid)
    result = await db.execute(query)
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry {dlq_id} not found")

    # Check if already resolved
    if entry.resolved_at:
        raise HTTPException(
            status_code=400,
            detail="DLQ entry is already resolved"
        )

    # Mark as resolved
    now = datetime.utcnow()
    entry.resolved_at = now
    entry.resolution_note = request.resolution_note

    await db.commit()
    logger.info(f"DLQ entry {dlq_id} marked as resolved: {request.resolution_note[:50]}...")

    return DLQResolveResponse(
        id=str(entry.id),
        status="resolved",
        resolved_at=now,
    )
