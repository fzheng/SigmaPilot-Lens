"""LLM configuration service with caching for runtime API key management.

This service provides:
- Database-backed LLM configuration storage
- In-memory caching with configurable TTL
- CRUD operations for LLM configs
- API key validation testing
- Predefined model-to-provider mappings
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select

from src.models.database import get_db_context
from src.models.orm.llm_config import LLMConfig
from src.observability.logging import get_logger

logger = get_logger(__name__)


# Predefined model-to-provider mappings (not user-editable)
MODEL_PROVIDERS = {
    "chatgpt": "openai",
    "gemini": "google",
    "claude": "anthropic",
    "deepseek": "deepseek",
}

# Default model IDs for each model
DEFAULT_MODEL_IDS = {
    "chatgpt": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "claude": "claude-sonnet-4-20250514",
    "deepseek": "deepseek-chat",
}


@dataclass
class LLMConfigData:
    """Immutable LLM configuration data for use by adapters."""

    model_name: str
    enabled: bool
    provider: str
    api_key: str
    model_id: str
    timeout_ms: int
    max_tokens: int
    prompt_path: Optional[str]

    @classmethod
    def from_orm(cls, config: LLMConfig) -> "LLMConfigData":
        """Create from ORM model."""
        return cls(
            model_name=config.model_name,
            enabled=config.enabled,
            provider=config.provider,
            api_key=config.api_key,
            model_id=config.model_id,
            timeout_ms=config.timeout_ms,
            max_tokens=config.max_tokens,
            prompt_path=config.prompt_path,
        )


class LLMConfigService:
    """Service for managing LLM configurations with caching.

    Caches configurations in memory to avoid database lookups on every
    evaluation. Cache is refreshed on:
    - TTL expiration (default 5 minutes)
    - Explicit invalidation after updates
    - Service restart
    """

    # Cache TTL in seconds
    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._cache: Dict[str, LLMConfigData] = {}
        self._cache_timestamp: float = 0
        self._cache_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize service and load configs from database.

        Should be called on application startup.
        """
        await self._refresh_cache()
        self._initialized = True
        logger.info(f"LLM config service initialized with {len(self._cache)} configs")

    async def _refresh_cache(self) -> None:
        """Refresh the in-memory cache from database."""
        async with self._cache_lock:
            try:
                async with get_db_context() as db:
                    result = await db.execute(select(LLMConfig))
                    configs = result.scalars().all()

                    new_cache = {}
                    for config in configs:
                        new_cache[config.model_name] = LLMConfigData.from_orm(config)

                    self._cache = new_cache
                    self._cache_timestamp = time.time()
                    logger.debug(f"LLM config cache refreshed with {len(new_cache)} entries")

            except Exception as e:
                logger.error(f"Failed to refresh LLM config cache: {e}")
                # Keep existing cache on error

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        return (time.time() - self._cache_timestamp) < self.CACHE_TTL_SECONDS

    async def get_config(self, model_name: str) -> Optional[LLMConfigData]:
        """Get configuration for a specific model.

        Args:
            model_name: Model identifier (chatgpt, gemini, claude, deepseek)

        Returns:
            LLMConfigData if found, enabled, and has API key; None otherwise
        """
        # Refresh cache if expired
        if not self._is_cache_valid():
            await self._refresh_cache()

        # Check database cache
        if model_name in self._cache:
            config = self._cache[model_name]
            if config.enabled and config.api_key:
                return config
            elif not config.enabled:
                logger.debug(f"Model {model_name} is disabled")
                return None

        return None

    async def get_enabled_models(self) -> List[str]:
        """Get list of enabled model names.

        Returns:
            List of model names that are enabled and have valid API keys
        """
        if not self._is_cache_valid():
            await self._refresh_cache()

        return [
            name for name, config in self._cache.items()
            if config.enabled and config.api_key
        ]

    async def list_all(self) -> List[LLMConfigData]:
        """List all configurations (enabled and disabled).

        Returns:
            List of all LLM configurations
        """
        if not self._is_cache_valid():
            await self._refresh_cache()
        return list(self._cache.values())

    async def create_or_update(
        self,
        model_name: str,
        provider: str,
        api_key: str,
        model_id: str,
        enabled: bool = True,
        timeout_ms: int = 30000,
        max_tokens: int = 1000,
        prompt_path: Optional[str] = None,
    ) -> LLMConfigData:
        """Create or update an LLM configuration.

        Args:
            model_name: Unique model identifier
            provider: Provider name (openai, google, anthropic, deepseek)
            api_key: API key for the provider
            model_id: Model identifier (e.g., gpt-4o)
            enabled: Whether the model is enabled
            timeout_ms: Request timeout in milliseconds
            max_tokens: Maximum tokens for response
            prompt_path: Optional custom prompt path

        Returns:
            Updated configuration data
        """
        async with get_db_context() as db:
            # Check if exists
            result = await db.execute(
                select(LLMConfig).where(LLMConfig.model_name == model_name)
            )
            config = result.scalar_one_or_none()

            now = datetime.now(timezone.utc)

            if config:
                # Update existing
                config.provider = provider
                config.api_key = api_key
                config.model_id = model_id
                config.enabled = enabled
                config.timeout_ms = timeout_ms
                config.max_tokens = max_tokens
                config.prompt_path = prompt_path
                config.updated_at = now
                logger.info(f"Updated LLM config for {model_name}")
            else:
                # Create new
                config = LLMConfig(
                    model_name=model_name,
                    provider=provider,
                    api_key=api_key,
                    model_id=model_id,
                    enabled=enabled,
                    timeout_ms=timeout_ms,
                    max_tokens=max_tokens,
                    prompt_path=prompt_path,
                    created_at=now,
                    updated_at=now,
                )
                db.add(config)
                logger.info(f"Created LLM config for {model_name}")

            await db.commit()
            await db.refresh(config)

            # Invalidate cache
            await self._refresh_cache()

            return LLMConfigData.from_orm(config)

    async def set_enabled(self, model_name: str, enabled: bool) -> bool:
        """Enable or disable a model.

        Args:
            model_name: Model to enable/disable
            enabled: New enabled state

        Returns:
            True if model was found and updated, False otherwise
        """
        async with get_db_context() as db:
            result = await db.execute(
                select(LLMConfig).where(LLMConfig.model_name == model_name)
            )
            config = result.scalar_one_or_none()

            if not config:
                return False

            config.enabled = enabled
            config.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Invalidate cache
            await self._refresh_cache()

            logger.info(f"Model {model_name} {'enabled' if enabled else 'disabled'}")
            return True

    async def delete(self, model_name: str) -> bool:
        """Delete an LLM configuration.

        Args:
            model_name: Model to delete

        Returns:
            True if deleted, False if not found
        """
        async with get_db_context() as db:
            result = await db.execute(
                select(LLMConfig).where(LLMConfig.model_name == model_name)
            )
            config = result.scalar_one_or_none()

            if not config:
                return False

            await db.delete(config)
            await db.commit()

            # Invalidate cache
            await self._refresh_cache()

            logger.info(f"Deleted LLM config for {model_name}")
            return True

    async def update_validation_status(
        self,
        model_name: str,
        status: str,
    ) -> None:
        """Update the validation status for a model.

        Args:
            model_name: Model to update
            status: Validation status (ok, invalid_key, rate_limited, error)
        """
        async with get_db_context() as db:
            result = await db.execute(
                select(LLMConfig).where(LLMConfig.model_name == model_name)
            )
            config = result.scalar_one_or_none()

            if config:
                config.validation_status = status
                config.last_validated_at = datetime.now(timezone.utc)
                await db.commit()

    async def test_api_key(self, model_name: str) -> Dict:
        """Test if an API key is valid by making a minimal API call.

        Args:
            model_name: Model to test

        Returns:
            Dict with 'success', 'message', and 'latency_ms' keys
        """
        config = await self.get_config(model_name)
        if not config:
            return {
                "success": False,
                "message": f"No configuration found for {model_name}",
                "latency_ms": 0,
            }

        try:
            # Import here to avoid circular imports
            from src.services.evaluation.models import create_adapter

            start_time = time.time()
            adapter = create_adapter(model_name, config)

            # Make a minimal test call
            if hasattr(adapter, 'test_connection'):
                result = await adapter.test_connection()
            else:
                # Fallback: try a minimal prompt
                result = await adapter.evaluate("Say 'ok' and nothing else.")
                result = result.is_success

            latency_ms = int((time.time() - start_time) * 1000)

            if result:
                await self.update_validation_status(model_name, "ok")
                return {
                    "success": True,
                    "message": "API key is valid",
                    "latency_ms": latency_ms,
                }
            else:
                await self.update_validation_status(model_name, "error")
                return {
                    "success": False,
                    "message": "API call failed",
                    "latency_ms": latency_ms,
                }

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
                status = "invalid_key"
            elif "rate" in error_msg or "429" in error_msg:
                status = "rate_limited"
            else:
                status = "error"

            await self.update_validation_status(model_name, status)
            return {
                "success": False,
                "message": str(e),
                "latency_ms": 0,
            }

    def invalidate_cache(self) -> None:
        """Force cache invalidation (synchronous)."""
        self._cache_timestamp = 0


# Singleton instance
_llm_config_service: Optional[LLMConfigService] = None


def get_llm_config_service() -> LLMConfigService:
    """Get the singleton LLM config service instance."""
    global _llm_config_service
    if _llm_config_service is None:
        _llm_config_service = LLMConfigService()
    return _llm_config_service
