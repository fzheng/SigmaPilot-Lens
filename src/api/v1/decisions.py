"""Decision query endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.database import get_db_session
from src.models.orm.decision import ModelDecision as DecisionORM
from src.models.orm.event import Event
from src.models.schemas.decision import (
    DecisionListResponse,
    DecisionDetailResponse,
    DecisionListItem,
    EntryPlan,
    RiskPlan,
    ModelMeta,
)

router = APIRouter()


def _build_entry_plan(entry_plan_data: Optional[dict]) -> Optional[EntryPlan]:
    """Build EntryPlan from database JSON."""
    if not entry_plan_data:
        return None
    return EntryPlan(
        type=entry_plan_data.get("type", "market"),
        offset_bps=entry_plan_data.get("offset_bps"),
    )


def _build_risk_plan(risk_plan_data: Optional[dict]) -> Optional[RiskPlan]:
    """Build RiskPlan from database JSON."""
    if not risk_plan_data:
        return None
    return RiskPlan(
        stop_method=risk_plan_data.get("stop_method", "fixed"),
        stop_level=risk_plan_data.get("stop_level"),
        atr_multiple=risk_plan_data.get("atr_multiple"),
        trail_pct=risk_plan_data.get("trail_pct"),
    )


def _map_status(db_status: str) -> str:
    """Map database status to API status.

    Handles both lowercase (legacy) and uppercase (ModelStatus enum) values.
    """
    # Normalize to lowercase for lookup
    status_lower = db_status.lower() if db_status else ""
    status_map = {
        "ok": "SUCCESS",
        "success": "SUCCESS",
        "invalid_json": "SCHEMA_ERROR",
        "schema_error": "SCHEMA_ERROR",
        "validation_failed": "SCHEMA_ERROR",
        "timeout": "TIMEOUT",
        "provider_error": "API_ERROR",
        "api_error": "API_ERROR",
        "rate_limited": "RATE_LIMITED",
        "network_error": "NETWORK_ERROR",
        "invalid_config": "INVALID_CONFIG",
    }
    return status_map.get(status_lower, "API_ERROR")


@router.get(
    "",
    response_model=DecisionListResponse,
    summary="List decisions",
    description="Query AI model decisions with optional filters. Access is restricted to internal Docker network only.",
)
async def list_decisions(
    model: Optional[str] = Query(None, description="Filter by model name"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    decision: Optional[str] = Query(None, description="Filter by decision type"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum confidence"),
    since: Optional[datetime] = Query(None, description="Decisions after this time"),
    until: Optional[datetime] = Query(None, description="Decisions before this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Query AI model decisions.

    Supports filtering by model, symbol, event_type, decision type,
    minimum confidence, and time range.
    """
    # Build query with join to Event for symbol/event_type filters
    query = select(DecisionORM).join(Event, DecisionORM.event_id == Event.event_id)

    if model:
        query = query.where(DecisionORM.model_name == model)
    if symbol:
        query = query.where(Event.symbol == symbol.upper())
    if event_type:
        query = query.where(Event.event_type == event_type)
    if decision:
        query = query.where(DecisionORM.decision == decision)
    if min_confidence is not None:
        query = query.where(DecisionORM.confidence >= min_confidence)
    if since:
        query = query.where(DecisionORM.evaluated_at >= since)
    if until:
        query = query.where(DecisionORM.evaluated_at <= until)

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(DecisionORM.evaluated_at.desc()).offset(offset).limit(limit)

    # Add eager loading for Event
    query = query.options(selectinload(DecisionORM.event))

    # Execute query
    result = await db.execute(query)
    decisions = result.scalars().all()

    # Convert to response schema
    items = [
        DecisionListItem(
            id=str(d.id),
            event_id=d.event_id,
            symbol=d.event.symbol if d.event else "UNKNOWN",
            event_type=d.event.event_type if d.event else "UNKNOWN",
            model=d.model_name,
            decision=d.decision,
            confidence=float(d.confidence),
            entry_plan=_build_entry_plan(d.entry_plan),
            risk_plan=_build_risk_plan(d.risk_plan),
            size_pct=float(d.size_pct) if d.size_pct else None,
            reasons=d.reasons if isinstance(d.reasons, list) else d.reasons.get("reasons", []) if d.reasons else [],
            evaluated_at=d.evaluated_at,
        )
        for d in decisions
    ]

    return DecisionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{decision_id}",
    response_model=DecisionDetailResponse,
    summary="Get decision details",
    description="Retrieve full details of a specific decision. Access is restricted to internal Docker network only.",
)
async def get_decision(
    decision_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get full details of a decision.

    Includes entry plan, risk plan, reasons, and model metadata.
    """
    # Parse UUID
    try:
        decision_uuid = UUID(decision_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid decision ID format")

    # Query decision with event
    query = (
        select(DecisionORM)
        .where(DecisionORM.id == decision_uuid)
        .options(selectinload(DecisionORM.event))
    )
    result = await db.execute(query)
    d = result.scalar_one_or_none()

    if not d:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    # Build model meta
    model_meta = ModelMeta(
        model_name=d.model_name,
        model_version=d.model_version,
        latency_ms=d.latency_ms,
        status=_map_status(d.status),
        error_code=d.error_code,
        error_message=d.error_message,
        tokens_used=(d.tokens_in or 0) + (d.tokens_out or 0) if d.tokens_in or d.tokens_out else None,
    )

    # Parse reasons
    reasons = d.reasons if isinstance(d.reasons, list) else d.reasons.get("reasons", []) if d.reasons else []

    return DecisionDetailResponse(
        id=str(d.id),
        event_id=d.event_id,
        symbol=d.event.symbol if d.event else "UNKNOWN",
        event_type=d.event.event_type if d.event else "UNKNOWN",
        model=d.model_name,
        decision=d.decision,
        confidence=float(d.confidence),
        entry_plan=_build_entry_plan(d.entry_plan),
        risk_plan=_build_risk_plan(d.risk_plan),
        size_pct=float(d.size_pct) if d.size_pct else None,
        reasons=reasons,
        model_meta=model_meta,
        evaluated_at=d.evaluated_at,
    )
