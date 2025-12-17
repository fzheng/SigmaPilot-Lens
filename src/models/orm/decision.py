"""Model decision ORM models."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class ModelDecision(Base):
    """AI model decision with full audit trail."""

    __tablename__ = "model_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.event_id"), nullable=False, index=True
    )

    # Model identification
    model_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Prompt versioning for reproducibility
    prompt_version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Prompt version identifier (e.g., v1, v2)"
    )
    prompt_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 hash of the prompt used"
    )

    # Decision output
    decision: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    entry_plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    risk_plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    size_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    reasons: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Full decision payload (for audit)
    decision_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Complete model output as received"
    )

    # Performance metrics
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status tracking: ok, timeout, rate_limited, api_error, schema_error, network_error, invalid_config
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ok", index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Raw model response (for debugging invalid outputs)
    raw_response: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Raw model response (stored only on error)"
    )

    # Timestamps
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    event: Mapped["Event"] = relationship(back_populates="decisions")

    __table_args__ = (
        Index("idx_decisions_evaluated_at", "evaluated_at"),
        Index("idx_decisions_model_status", "model_name", "status"),
        Index("idx_decisions_event_model", "event_id", "model_name"),
    )


# Import at the bottom to avoid circular imports
from src.models.orm.event import Event  # noqa: E402, F401
