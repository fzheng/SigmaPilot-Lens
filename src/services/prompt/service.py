"""Prompt service with caching for database-backed prompt management.

This service provides the core business logic for managing AI prompts:

Features:
    - Database-backed prompt storage with versioning
    - In-memory caching with configurable TTL (default 5 minutes)
    - CRUD operations for prompts via async methods
    - Support for core + wrapper prompt pattern
    - Automatic seeding from file-based prompts on first run
    - Thread-safe cache operations with asyncio locks

Architecture:
    The service uses a singleton pattern (get_prompt_service()) to ensure
    consistent caching across the application. The cache is refreshed on:
    - TTL expiration (every 5 minutes by default)
    - After any create/update/delete operation
    - On service initialization

Usage:
    from src.services.prompt import get_prompt_service

    # Get the singleton service
    service = get_prompt_service()

    # Initialize on startup (loads cache, seeds if empty)
    await service.initialize()

    # Render a prompt for model evaluation
    prompt, version, hash = await service.render_prompt(
        model_name="chatgpt",
        enriched_event={"signal": "BUY", ...},
        constraints={"max_position": 1000},
    )

    # CRUD operations
    await service.create(name="core_decision", version="v2", ...)
    await service.update(name="core_decision", version="v2", content=...)
    await service.delete(name="core_decision", version="v2")
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, and_

from src.models.database import get_db_context
from src.models.orm.prompt import Prompt
from src.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PromptData:
    """Immutable data transfer object for prompt information.

    This dataclass is used to transfer prompt data between layers without
    exposing the ORM model directly. It's immutable to prevent accidental
    modifications and ensure thread-safety.

    Attributes:
        id: UUID as string
        name: Prompt identifier (e.g., "core_decision", "chatgpt_wrapper")
        version: Version string (e.g., "v1", "v2")
        prompt_type: Either "core" or "wrapper"
        model_name: For wrapper prompts, the target model name
        content: The actual prompt text
        content_hash: SHA-256 hash for change detection
        is_active: Whether this prompt is currently active
        description: Human-readable description
        created_at: Creation timestamp
    """

    id: str
    name: str
    version: str
    prompt_type: str  # "core" or "wrapper"
    model_name: Optional[str]  # For wrapper prompts only
    content: str
    content_hash: str
    is_active: bool
    description: Optional[str]
    created_at: datetime

    @classmethod
    def from_orm(cls, prompt: Prompt) -> "PromptData":
        """Create a PromptData instance from an ORM Prompt model.

        Args:
            prompt: SQLAlchemy ORM Prompt instance

        Returns:
            PromptData with copied values (immutable snapshot)
        """
        return cls(
            id=str(prompt.id),
            name=prompt.name,
            version=prompt.version,
            prompt_type=prompt.prompt_type,
            model_name=prompt.model_name,
            content=prompt.content,
            content_hash=prompt.content_hash,
            is_active=prompt.is_active,
            description=prompt.description,
            created_at=prompt.created_at,
        )


class PromptService:
    """Service for managing prompts with caching.

    Caches prompts in memory to avoid database lookups on every
    evaluation. Cache is refreshed on:
    - TTL expiration (default 5 minutes)
    - Explicit invalidation after updates
    - Service restart
    """

    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, prompts_dir: str = "prompts"):
        self._cache: Dict[str, PromptData] = {}  # key: f"{name}:{version}"
        self._cache_timestamp: float = 0
        self._cache_lock = asyncio.Lock()
        self._initialized = False
        self._prompts_dir = Path(prompts_dir)

    async def initialize(self) -> None:
        """Initialize service and load prompts from database.

        If database is empty, seeds from file-based prompts.
        """
        await self._refresh_cache()

        # If no prompts in database, seed from files
        if not self._cache:
            await self._seed_from_files()
            await self._refresh_cache()

        self._initialized = True
        logger.info(f"Prompt service initialized with {len(self._cache)} prompts")

    async def _seed_from_files(self) -> None:
        """Seed database with prompts from file system."""
        if not self._prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self._prompts_dir}")
            return

        seeded_count = 0
        for filepath in self._prompts_dir.glob("*.md"):
            name = filepath.stem
            content = filepath.read_text(encoding="utf-8")

            # Determine prompt type from filename
            if name.startswith("core_decision_"):
                prompt_type = "core"
                prompt_name = "core_decision"
                version = name.replace("core_decision_", "")
                model_name = None
            elif "_wrapper_" in name:
                prompt_type = "wrapper"
                parts = name.rsplit("_wrapper_", 1)
                model_name = parts[0]
                prompt_name = f"{model_name}_wrapper"
                version = parts[1] if len(parts) > 1 else "v1"
            else:
                # Skip non-standard files
                continue

            try:
                await self.create(
                    name=prompt_name,
                    version=version,
                    prompt_type=prompt_type,
                    content=content,
                    model_name=model_name,
                    description=f"Seeded from {filepath.name}",
                    created_by="system",
                )
                seeded_count += 1
                logger.info(f"Seeded prompt: {prompt_name} {version}")
            except Exception as e:
                logger.error(f"Failed to seed prompt {name}: {e}")

        logger.info(f"Seeded {seeded_count} prompts from files")

    async def _refresh_cache(self) -> None:
        """Refresh the in-memory cache from database."""
        async with self._cache_lock:
            try:
                async with get_db_context() as db:
                    # Only load active prompts
                    result = await db.execute(
                        select(Prompt).where(Prompt.is_active == True)
                    )
                    prompts = result.scalars().all()

                    new_cache = {}
                    for prompt in prompts:
                        key = f"{prompt.name}:{prompt.version}"
                        new_cache[key] = PromptData.from_orm(prompt)

                    self._cache = new_cache
                    self._cache_timestamp = time.time()
                    logger.debug(f"Prompt cache refreshed with {len(new_cache)} entries")

            except Exception as e:
                logger.error(f"Failed to refresh prompt cache: {e}")

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        return (time.time() - self._cache_timestamp) < self.CACHE_TTL_SECONDS

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_prompt(
        self,
        name: str,
        version: str = "v1",
    ) -> Optional[PromptData]:
        """Get a specific prompt by name and version.

        Args:
            name: Prompt name (e.g., 'core_decision', 'chatgpt_wrapper')
            version: Prompt version (e.g., 'v1')

        Returns:
            PromptData if found and active, None otherwise
        """
        if not self._is_cache_valid():
            await self._refresh_cache()

        key = f"{name}:{version}"
        return self._cache.get(key)

    async def get_core_prompt(self, version: str = "v1") -> Optional[PromptData]:
        """Get the core decision prompt.

        Args:
            version: Core prompt version

        Returns:
            PromptData for core prompt, None if not found
        """
        return await self.get_prompt("core_decision", version)

    async def get_wrapper_prompt(
        self,
        model_name: str,
        version: str = "v1",
    ) -> Optional[PromptData]:
        """Get a wrapper prompt for a specific model.

        Args:
            model_name: Model name (chatgpt, gemini, claude, deepseek)
            version: Wrapper version

        Returns:
            PromptData for wrapper prompt, None if not found
        """
        return await self.get_prompt(f"{model_name}_wrapper", version)

    async def render_prompt(
        self,
        model_name: str,
        enriched_event: dict,
        constraints: dict,
        core_version: str = "v1",
        wrapper_version: str = "v1",
    ) -> Tuple[str, str, str]:
        """Render a complete prompt for model evaluation.

        Args:
            model_name: Model name (e.g., 'chatgpt', 'gemini')
            enriched_event: The enriched signal event data
            constraints: Trading constraints
            core_version: Core prompt version
            wrapper_version: Wrapper prompt version

        Returns:
            Tuple of (rendered_prompt, prompt_version, prompt_hash)

        Raises:
            ValueError: If required prompts not found
        """
        # Get prompts
        core = await self.get_core_prompt(core_version)
        wrapper = await self.get_wrapper_prompt(model_name, wrapper_version)

        if not core:
            raise ValueError(f"Core prompt version {core_version} not found")
        if not wrapper:
            raise ValueError(f"Wrapper prompt for {model_name} version {wrapper_version} not found")

        # Render core prompt with data
        rendered_core = core.content.replace(
            "{enriched_event}",
            json.dumps(enriched_event, indent=2, default=str)
        ).replace(
            "{constraints}",
            json.dumps(constraints, indent=2)
        )

        # Combine wrapper with rendered core
        rendered_prompt = wrapper.content.replace("{core_prompt}", rendered_core)

        # Generate version and hash
        prompt_version = f"{model_name}_{wrapper_version}_core_{core_version}"
        prompt_hash = self._compute_hash(wrapper.content + core.content)

        return rendered_prompt, prompt_version, prompt_hash

    async def list_all(
        self,
        prompt_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[PromptData]:
        """List all prompts with optional filtering.

        Args:
            prompt_type: Filter by type ('core' or 'wrapper')
            include_inactive: Include inactive prompts

        Returns:
            List of prompts matching criteria
        """
        async with get_db_context() as db:
            query = select(Prompt)

            if prompt_type:
                query = query.where(Prompt.prompt_type == prompt_type)

            if not include_inactive:
                query = query.where(Prompt.is_active == True)

            query = query.order_by(Prompt.name, Prompt.version)

            result = await db.execute(query)
            prompts = result.scalars().all()

            return [PromptData.from_orm(p) for p in prompts]

    async def create(
        self,
        name: str,
        version: str,
        prompt_type: str,
        content: str,
        model_name: Optional[str] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PromptData:
        """Create a new prompt.

        Args:
            name: Prompt name
            version: Version string
            prompt_type: 'core' or 'wrapper'
            content: Prompt content
            model_name: For wrapper prompts, which model this is for
            description: Optional description
            created_by: Who created this prompt

        Returns:
            Created prompt data

        Raises:
            ValueError: If prompt_type is invalid or duplicate exists
        """
        if prompt_type not in ("core", "wrapper"):
            raise ValueError(f"Invalid prompt_type: {prompt_type}")

        if prompt_type == "wrapper" and not model_name:
            raise ValueError("model_name is required for wrapper prompts")

        content_hash = self._compute_hash(content)
        now = datetime.now(timezone.utc)

        async with get_db_context() as db:
            # Check for existing active prompt with same name/version
            result = await db.execute(
                select(Prompt).where(
                    and_(
                        Prompt.name == name,
                        Prompt.version == version,
                        Prompt.is_active == True,
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                raise ValueError(f"Active prompt {name} version {version} already exists")

            prompt = Prompt(
                name=name,
                version=version,
                prompt_type=prompt_type,
                model_name=model_name,
                content=content,
                content_hash=content_hash,
                description=description,
                is_active=True,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            db.add(prompt)
            await db.commit()
            await db.refresh(prompt)

            logger.info(f"Created prompt: {name} {version}")

            # Invalidate cache
            await self._refresh_cache()

            return PromptData.from_orm(prompt)

    async def update(
        self,
        name: str,
        version: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PromptData]:
        """Update an existing prompt.

        Args:
            name: Prompt name
            version: Version string
            content: New content (optional)
            description: New description (optional)
            is_active: New active status (optional)

        Returns:
            Updated prompt data, or None if not found
        """
        async with get_db_context() as db:
            result = await db.execute(
                select(Prompt).where(
                    and_(Prompt.name == name, Prompt.version == version)
                )
            )
            prompt = result.scalar_one_or_none()

            if not prompt:
                return None

            now = datetime.now(timezone.utc)

            if content is not None:
                prompt.content = content
                prompt.content_hash = self._compute_hash(content)

            if description is not None:
                prompt.description = description

            if is_active is not None:
                prompt.is_active = is_active

            prompt.updated_at = now

            await db.commit()
            await db.refresh(prompt)

            logger.info(f"Updated prompt: {name} {version}")

            # Invalidate cache
            await self._refresh_cache()

            return PromptData.from_orm(prompt)

    async def set_active(
        self,
        name: str,
        version: str,
        is_active: bool,
    ) -> bool:
        """Set active status for a prompt.

        Args:
            name: Prompt name
            version: Version string
            is_active: New active status

        Returns:
            True if updated, False if not found
        """
        result = await self.update(name, version, is_active=is_active)
        return result is not None

    async def delete(self, name: str, version: str) -> bool:
        """Delete a prompt.

        Args:
            name: Prompt name
            version: Version string

        Returns:
            True if deleted, False if not found
        """
        async with get_db_context() as db:
            result = await db.execute(
                select(Prompt).where(
                    and_(Prompt.name == name, Prompt.version == version)
                )
            )
            prompt = result.scalar_one_or_none()

            if not prompt:
                return False

            await db.delete(prompt)
            await db.commit()

            logger.info(f"Deleted prompt: {name} {version}")

            # Invalidate cache
            await self._refresh_cache()

            return True

    async def get_available_prompts(self) -> dict:
        """List available prompts grouped by type.

        Returns:
            Dict with core_versions and wrappers keys
        """
        prompts = await self.list_all()

        result = {
            "core_versions": [],
            "wrappers": {},
        }

        for p in prompts:
            if p.prompt_type == "core":
                result["core_versions"].append(p.version)
            elif p.prompt_type == "wrapper" and p.model_name:
                if p.model_name not in result["wrappers"]:
                    result["wrappers"][p.model_name] = []
                result["wrappers"][p.model_name].append(p.version)

        return result

    def invalidate_cache(self) -> None:
        """Force cache invalidation (synchronous)."""
        self._cache_timestamp = 0


# Singleton instance
_prompt_service: Optional[PromptService] = None


def get_prompt_service() -> PromptService:
    """Get the singleton prompt service instance."""
    global _prompt_service
    if _prompt_service is None:
        _prompt_service = PromptService()
    return _prompt_service
