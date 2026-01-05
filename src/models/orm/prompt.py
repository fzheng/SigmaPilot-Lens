"""Prompt ORM model for database-backed prompt storage.

This module defines the SQLAlchemy ORM model for storing AI prompts in the database.
Prompts are used by the evaluation worker to generate decisions from trading signals.

The prompt system uses a "core + wrapper" pattern:
- Core prompts contain the shared decision-making logic and output schema
- Wrapper prompts provide model-specific formatting (e.g., JSON enforcement for Claude)

Example usage:
    # Core prompt: shared by all models
    core = Prompt(name="core_decision", version="v1", prompt_type="core", ...)

    # Wrapper prompt: specific to ChatGPT
    wrapper = Prompt(name="chatgpt_wrapper", version="v1", prompt_type="wrapper",
                     model_name="chatgpt", ...)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class Prompt(Base):
    """Database-backed prompt storage for AI model evaluation.

    This model stores versioned prompts that can be updated at runtime without
    requiring a deployment. Supports the core + wrapper pattern where:

    - Core prompts (prompt_type='core'): Contain shared decision logic, output
      schema, and evaluation guidelines. Used by all models.

    - Wrapper prompts (prompt_type='wrapper'): Model-specific formatting that
      wraps around the core prompt. Each AI provider may need different
      instructions for JSON output, system prompts, etc.

    Key Features:
        - Versioning: Multiple versions can coexist (v1, v2, etc.)
        - Activation: Toggle is_active to switch between versions without deletion
        - Audit trail: Track creation/modification times and authors
        - Content hashing: SHA-256 hash for detecting changes

    Database Constraints:
        - Unique constraint on (name, version) for active prompts
        - Indexes on name, version, prompt_type, model_name, and is_active

    Attributes:
        id: UUID primary key
        name: Prompt identifier (e.g., "core_decision", "chatgpt_wrapper")
        version: Version string (e.g., "v1", "v2", "v1.1")
        prompt_type: Either "core" or "wrapper"
        model_name: For wrappers, the target model (e.g., "chatgpt", "gemini")
        content: The actual prompt text with placeholders
        description: Human-readable description for admin UI
        is_active: Whether this prompt version is currently in use
        content_hash: SHA-256 hash for change detection
        created_at: When this prompt was created
        updated_at: When this prompt was last modified
        created_by: Username/identifier of the creator (from auth context)
    """

    __tablename__ = "prompts"

    # ==========================================================================
    # Primary Key
    # ==========================================================================
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier for this prompt record"
    )

    # ==========================================================================
    # Prompt Identification
    # ==========================================================================
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Prompt name, e.g., 'core_decision', 'chatgpt_wrapper'"
    )

    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version string, e.g., 'v1', 'v2', 'v1.1'"
    )

    prompt_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Either 'core' for shared logic or 'wrapper' for model-specific"
    )

    model_name: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="For wrapper prompts: target model (chatgpt, gemini, claude, deepseek)"
    )

    # ==========================================================================
    # Content
    # ==========================================================================
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The prompt text with placeholders like {enriched_event}"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description for admin UI"
    )

    # ==========================================================================
    # Status and Versioning
    # ==========================================================================
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this version is active; only one active per name+version"
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of content for change detection"
    )

    # ==========================================================================
    # Audit Fields
    # ==========================================================================
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        comment="When this prompt was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="When this prompt was last modified"
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Username/subject from auth context who created this prompt"
    )

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"<Prompt {self.name} {self.version} active={self.is_active}>"
