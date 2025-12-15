"""Event ORM models."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class Event(Base):
    """Raw trading signal event with full lifecycle tracking."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)

    # Idempotency key to prevent duplicate processing
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # Signal data
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_direction: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    size: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    liquidation_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)

    # Processing status (queued|enriched|evaluated|published|failed|dlq)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)

    # Feature profile used for enrichment (for reproducibility)
    feature_profile: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Lifecycle timestamps
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Raw payload for audit
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # API key reference
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    enriched: Mapped["EnrichedEvent"] = relationship(back_populates="event", uselist=False)
    timeline: Mapped[list["ProcessingTimeline"]] = relationship(back_populates="event")
    decisions: Mapped[list["ModelDecision"]] = relationship(back_populates="event")

    __table_args__ = (
        Index("idx_events_received_at", "received_at"),
        Index("idx_events_source", "source"),
        Index("idx_events_status", "status"),
        Index("idx_events_symbol_received", "symbol", "received_at"),
    )


class EnrichedEvent(Base):
    """Enriched signal event with market data and TA."""

    __tablename__ = "enriched_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.event_id"), nullable=False, index=True
    )

    # Feature profile used
    feature_profile: Mapped[str] = mapped_column(String(50), nullable=False)

    # Provider information
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="hyperliquid")
    provider_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Enriched data
    market_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ta_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    levels_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    derivs_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Per-component data timestamps for staleness tracking
    data_timestamps: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Timestamps per data component: {mid_ts, l2_ts, candles_ts, funding_ts, ...}"
    )

    # Quality flags (stale, missing, out_of_range, provider_errors)
    quality_flags: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Compact enriched payload for AI (< 4KB target)
    enriched_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Compact payload sent to AI models"
    )

    # Timing
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    enrichment_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="enriched")


class ProcessingTimeline(Base):
    """Processing status timeline for events."""

    __tablename__ = "processing_timeline"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.event_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="timeline")


# Import at the bottom to avoid circular imports
from src.models.orm.decision import ModelDecision  # noqa: E402
