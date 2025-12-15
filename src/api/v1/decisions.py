"""Decision query endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from src.api.deps import VerifiedKey
from src.models.schemas.decision import DecisionListResponse, DecisionDetailResponse

router = APIRouter()


@router.get(
    "",
    response_model=DecisionListResponse,
    summary="List decisions",
    description="Query AI model decisions with optional filters.",
)
async def list_decisions(
    key_info: VerifiedKey,
    model: Optional[str] = Query(None, description="Filter by model name"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    decision: Optional[str] = Query(None, description="Filter by decision type"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum confidence"),
    since: Optional[datetime] = Query(None, description="Decisions after this time"),
    until: Optional[datetime] = Query(None, description="Decisions before this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Query AI model decisions.

    Supports filtering by model, symbol, event_type, decision type,
    minimum confidence, and time range.
    """
    # TODO: Implement database query
    return DecisionListResponse(
        items=[],
        total=0,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{decision_id}",
    response_model=DecisionDetailResponse,
    summary="Get decision details",
    description="Retrieve full details of a specific decision.",
)
async def get_decision(
    decision_id: str,
    key_info: VerifiedKey,
):
    """
    Get full details of a decision.

    Includes entry plan, risk plan, reasons, and model metadata.
    """
    # TODO: Implement database query
    raise NotImplementedError("Decision query not implemented yet")
