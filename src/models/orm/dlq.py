"""Dead letter queue ORM model."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class DLQEntry(Base):
    """Dead letter queue entry for failed processing."""

    __tablename__ = "dlq_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # Stage where failure occurred (enqueue|enrich|evaluate|publish)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Error details
    reason_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Structured error code"
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=False)

    # Full payload for replay/debugging
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Resolution tracking
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_dlq_created_at", "created_at"),
        Index("idx_dlq_stage_reason", "stage", "reason_code"),
        Index("idx_dlq_unresolved", "resolved_at", postgresql_where="resolved_at IS NULL"),
    )
