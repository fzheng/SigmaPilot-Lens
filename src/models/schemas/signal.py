"""Trading signal schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TradingSignalEvent(BaseModel):
    """Input schema for trading signals."""

    event_type: Literal["OPEN_SIGNAL", "CLOSE_SIGNAL"] = Field(
        ..., description="Type of trading signal"
    )
    symbol: str = Field(
        ..., min_length=1, max_length=20, description="Trading symbol (e.g., BTC, ETH)"
    )
    signal_direction: Literal["long", "short", "close_long", "close_short"] = Field(
        ..., description="Direction of the signal"
    )
    entry_price: Decimal = Field(..., gt=0, description="Entry price for the position")
    size: Decimal = Field(..., gt=0, description="Position size")
    liquidation_price: Decimal = Field(..., gt=0, description="Liquidation price level")
    ts_utc: datetime = Field(..., description="Signal timestamp in UTC")
    source: str = Field(
        ..., min_length=1, max_length=100, description="Source identifier of the signal"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "OPEN_SIGNAL",
                "symbol": "BTC",
                "signal_direction": "long",
                "entry_price": 42000.50,
                "size": 0.1,
                "liquidation_price": 38000.00,
                "ts_utc": "2024-01-15T10:30:00Z",
                "source": "strategy_alpha",
            }
        }


# Alias for API request
SignalSubmitRequest = TradingSignalEvent


class SignalSubmitResponse(BaseModel):
    """Response schema for signal submission."""

    event_id: str = Field(..., description="Unique event identifier")
    status: str = Field(..., description="Current status (ENQUEUED)")
    received_at: datetime = Field(..., description="Server receive timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "ENQUEUED",
                "received_at": "2024-01-15T10:30:00.123Z",
            }
        }


class TimelineEntry(BaseModel):
    """Processing timeline entry."""

    status: str = Field(..., description="Status at this point")
    timestamp: datetime = Field(..., description="Timestamp of status change")
    details: Optional[dict] = Field(None, description="Additional details")


class DecisionSummary(BaseModel):
    """Summary of a model decision."""

    model: str = Field(..., description="Model name")
    decision: str = Field(..., description="Decision type")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")


class EventSummary(BaseModel):
    """Summary of an event for list views."""

    event_id: str
    event_type: str
    symbol: str
    signal_direction: str
    entry_price: Decimal
    size: Decimal
    status: str
    source: str
    received_at: datetime


class EventListResponse(BaseModel):
    """Response schema for event list endpoint."""

    items: List[EventSummary]
    total: int
    limit: int
    offset: int


class EnrichedSummary(BaseModel):
    """Summary of enrichment data."""

    feature_profile: str
    quality_flags: dict


class EventDetailResponse(BaseModel):
    """Response schema for event detail endpoint."""

    event_id: str
    event_type: str
    symbol: str
    signal_direction: str
    entry_price: Decimal
    size: Decimal
    liquidation_price: Decimal
    ts_utc: datetime
    source: str
    received_at: datetime
    status: str
    timeline: List[TimelineEntry]
    enriched: Optional[EnrichedSummary] = None
    decisions: List[DecisionSummary] = []
