"""AI model decision schemas."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EntryPlan(BaseModel):
    """Entry execution plan."""

    type: Literal["market", "limit"] = Field(..., description="Order type")
    offset_bps: Optional[float] = Field(
        None, description="Offset from current price in basis points (for limit orders)"
    )


class RiskPlan(BaseModel):
    """Risk management plan."""

    stop_method: Literal["fixed", "atr", "trailing"] = Field(..., description="Stop loss method")
    stop_level: Optional[float] = Field(None, description="Fixed stop price level")
    atr_multiple: Optional[float] = Field(
        None, ge=0.5, le=10, description="ATR multiple for stop calculation"
    )
    trail_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Trailing stop percentage"
    )


class ModelMeta(BaseModel):
    """Model execution metadata."""

    model_name: str = Field(..., description="Name of the AI model")
    model_version: Optional[str] = Field(None, description="Model version identifier")
    latency_ms: int = Field(..., ge=0, description="Evaluation latency in milliseconds")
    status: Literal["SUCCESS", "TIMEOUT", "API_ERROR", "SCHEMA_ERROR", "RATE_LIMITED"] = Field(
        ..., description="Evaluation status"
    )
    error_code: Optional[str] = Field(None, description="Error code if status is not SUCCESS")
    error_message: Optional[str] = Field(None, description="Error message if status is not SUCCESS")
    tokens_used: Optional[int] = Field(None, description="Total tokens used")


class ModelDecision(BaseModel):
    """AI model decision output."""

    decision: Literal["FOLLOW_ENTER", "IGNORE", "FOLLOW_EXIT", "HOLD", "TIGHTEN_STOP"] = Field(
        ..., description="The AI model's recommendation"
    )
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    entry_plan: Optional[EntryPlan] = Field(None, description="Entry execution plan")
    risk_plan: Optional[RiskPlan] = Field(None, description="Risk management plan")
    size_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Suggested position size percentage"
    )
    reasons: List[str] = Field(..., min_length=1, description="Short reason tags")
    model_meta: ModelMeta = Field(..., description="Model execution metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "decision": "FOLLOW_ENTER",
                "confidence": 0.78,
                "entry_plan": {"type": "limit", "offset_bps": -5},
                "risk_plan": {"stop_method": "atr", "atr_multiple": 2.0},
                "size_pct": 15,
                "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
                "model_meta": {
                    "model_name": "chatgpt",
                    "model_version": "gpt-4o",
                    "latency_ms": 1850,
                    "status": "SUCCESS",
                    "tokens_used": 1250,
                },
            }
        }


class DecisionListItem(BaseModel):
    """Decision item for list responses."""

    id: str
    event_id: str
    symbol: str
    event_type: str
    model: str
    decision: str
    confidence: float
    entry_plan: Optional[EntryPlan] = None
    risk_plan: Optional[RiskPlan] = None
    size_pct: Optional[float] = None
    reasons: List[str]
    evaluated_at: datetime


class DecisionListResponse(BaseModel):
    """Response schema for decision list endpoint."""

    items: List[DecisionListItem]
    total: int
    limit: int
    offset: int


class DecisionDetailResponse(BaseModel):
    """Response schema for decision detail endpoint."""

    id: str
    event_id: str
    symbol: str
    event_type: str
    model: str
    decision: str
    confidence: float
    entry_plan: Optional[EntryPlan] = None
    risk_plan: Optional[RiskPlan] = None
    size_pct: Optional[float] = None
    reasons: List[str]
    model_meta: ModelMeta
    evaluated_at: datetime
