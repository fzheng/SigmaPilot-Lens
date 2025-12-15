"""Enriched signal schemas."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.schemas.signal import TradingSignalEvent


class MarketData(BaseModel):
    """Market data snapshot."""

    mid: float = Field(..., description="Mid price")
    bid: Optional[float] = Field(None, description="Best bid")
    ask: Optional[float] = Field(None, description="Best ask")
    spread_bps: float = Field(..., description="Spread in basis points")
    price_drift_bps_from_entry: float = Field(
        ..., description="Price drift from entry in basis points"
    )
    obi_buckets: Optional[Dict[str, float]] = Field(
        None, description="Order book imbalance by depth"
    )
    fetched_at: datetime = Field(..., description="Data fetch timestamp")


class EMAIndicators(BaseModel):
    """EMA indicator values."""

    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None


class MACDIndicators(BaseModel):
    """MACD indicator values."""

    macd_line: float
    signal_line: float
    histogram: float


class TimeframeIndicators(BaseModel):
    """Technical indicators for a single timeframe."""

    ema: Optional[EMAIndicators] = None
    macd: Optional[MACDIndicators] = None
    rsi: Optional[float] = Field(None, ge=0, le=100, description="RSI value")
    atr: Optional[float] = Field(None, ge=0, description="ATR value")


class TAData(BaseModel):
    """Technical analysis data across timeframes."""

    timeframes: Dict[str, TimeframeIndicators] = Field(
        ..., description="Indicators per timeframe (e.g., '15m', '1h', '4h')"
    )


class SupportResistanceLevel(BaseModel):
    """Support or resistance level."""

    price: float
    strength: float = Field(..., ge=0, le=1)


class LevelsData(BaseModel):
    """Support and resistance levels."""

    supports: List[SupportResistanceLevel] = Field(default_factory=list, max_length=5)
    resistances: List[SupportResistanceLevel] = Field(default_factory=list, max_length=5)


class DerivsData(BaseModel):
    """Derivatives market data (funding, OI)."""

    funding_rate: Optional[float] = Field(None, description="Current funding rate")
    predicted_funding: Optional[float] = Field(None, description="Predicted next funding")
    open_interest: Optional[float] = Field(None, description="Open interest in USD")
    oi_change_24h_pct: Optional[float] = Field(None, description="OI change in last 24h")
    mark_price: Optional[float] = None
    oracle_price: Optional[float] = None


class Constraints(BaseModel):
    """Trading constraints from policy configuration."""

    min_hold_minutes: int = Field(15, ge=0)
    one_direction_only: bool = True
    max_trades_per_hour: int = Field(4, ge=1)
    max_position_size_pct: float = Field(25, ge=0, le=100)


class QualityFlags(BaseModel):
    """Data quality flags."""

    missing_data: List[str] = Field(default_factory=list)
    stale_data: List[str] = Field(default_factory=list)
    out_of_range: List[str] = Field(default_factory=list)
    provider_errors: List[str] = Field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if there are any quality issues."""
        return bool(
            self.missing_data or self.stale_data or self.out_of_range or self.provider_errors
        )


class EnrichedSignalEvent(BaseModel):
    """Enriched signal with market data and technical analysis."""

    event_id: str = Field(..., description="Unique event identifier")
    original: TradingSignalEvent = Field(..., description="Original signal")
    market: MarketData = Field(..., description="Market data snapshot")
    ta: TAData = Field(..., description="Technical analysis data")
    levels: Optional[LevelsData] = Field(None, description="S/R levels (if profile requires)")
    derivs: Optional[DerivsData] = Field(None, description="Derivatives data (if profile requires)")
    constraints: Constraints = Field(..., description="Trading constraints")
    quality_flags: QualityFlags = Field(..., description="Data quality flags")
    enriched_at: datetime = Field(..., description="Enrichment timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "original": {
                    "event_type": "OPEN_SIGNAL",
                    "symbol": "BTC",
                    "signal_direction": "long",
                    "entry_price": 42000.50,
                    "size": 0.1,
                    "liquidation_price": 38000.00,
                    "ts_utc": "2024-01-15T10:30:00Z",
                    "source": "strategy_alpha",
                },
                "market": {
                    "mid": 42050.25,
                    "bid": 42049.00,
                    "ask": 42051.50,
                    "spread_bps": 0.59,
                    "price_drift_bps_from_entry": 11.84,
                    "fetched_at": "2024-01-15T10:30:01Z",
                },
                "ta": {
                    "timeframes": {
                        "1h": {
                            "ema": {"ema_9": 41950.0, "ema_21": 41800.5, "ema_50": 41500.0},
                            "macd": {"macd_line": 120.5, "signal_line": 95.2, "histogram": 25.3},
                            "rsi": 62.1,
                            "atr": 350.2,
                        }
                    }
                },
                "constraints": {
                    "min_hold_minutes": 15,
                    "one_direction_only": True,
                    "max_trades_per_hour": 4,
                    "max_position_size_pct": 25,
                },
                "quality_flags": {
                    "missing_data": [],
                    "stale_data": [],
                    "out_of_range": [],
                    "provider_errors": [],
                },
                "enriched_at": "2024-01-15T10:30:02Z",
            }
        }
