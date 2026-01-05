"""LLM configuration ORM model for runtime API key management."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class LLMConfig(Base):
    """LLM provider configuration stored in database for runtime management.

    Allows API keys and model settings to be updated without container restart.
    API keys are stored encrypted (application-level encryption recommended).
    """

    __tablename__ = "llm_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Model identification (chatgpt, gemini, claude, deepseek)
    model_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Enable/disable without deleting config
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Provider info
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g., "openai", "google", "anthropic", "deepseek"

    # API key (should be encrypted at rest in production)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Model settings
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g., "gpt-4o", "gemini-1.5-pro", "claude-sonnet-4-20250514"

    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30000)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)

    # Optional custom prompt path (relative to prompts/ directory)
    prompt_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Last validation status
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # ok, invalid_key, rate_limited, error

    def __repr__(self) -> str:
        return f"<LLMConfig {self.model_name} enabled={self.enabled}>"
