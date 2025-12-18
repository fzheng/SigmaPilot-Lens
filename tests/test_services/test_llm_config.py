"""Tests for LLM configuration service.

This module tests the LLM configuration service which provides:
- Database-backed LLM configuration storage
- In-memory caching with configurable TTL
- CRUD operations for LLM configs
- API key masking for security
- Fallback to environment variables

Key test scenarios:
- LLMConfigData dataclass creation
- Config service get/list operations
- Cache invalidation and TTL behavior
- Environment variable fallback
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import asdict


@pytest.mark.unit
class TestLLMConfigData:
    """Tests for LLMConfigData dataclass."""

    def test_create_from_values(self):
        """Test creating LLMConfigData with direct values."""
        from src.services.llm_config.service import LLMConfigData

        config = LLMConfigData(
            model_name="chatgpt",
            enabled=True,
            provider="openai",
            api_key="sk-test-key",
            model_id="gpt-4o",
            timeout_ms=30000,
            max_tokens=1000,
            prompt_path="prompts/test.md",
        )

        assert config.model_name == "chatgpt"
        assert config.enabled is True
        assert config.provider == "openai"
        assert config.api_key == "sk-test-key"
        assert config.model_id == "gpt-4o"
        assert config.timeout_ms == 30000
        assert config.max_tokens == 1000
        assert config.prompt_path == "prompts/test.md"

    def test_create_from_orm(self):
        """Test creating LLMConfigData from ORM model."""
        from src.services.llm_config.service import LLMConfigData

        # Mock ORM object
        mock_orm = MagicMock()
        mock_orm.model_name = "gemini"
        mock_orm.enabled = True
        mock_orm.provider = "google"
        mock_orm.api_key = "goog-test-key"
        mock_orm.model_id = "gemini-1.5-pro"
        mock_orm.timeout_ms = 25000
        mock_orm.max_tokens = 2000
        mock_orm.prompt_path = None

        config = LLMConfigData.from_orm(mock_orm)

        assert config.model_name == "gemini"
        assert config.provider == "google"
        assert config.api_key == "goog-test-key"
        assert config.model_id == "gemini-1.5-pro"
        assert config.prompt_path is None

    def test_predefined_model_providers(self):
        """Test that model providers are predefined and not editable."""
        from src.services.llm_config.service import MODEL_PROVIDERS, DEFAULT_MODEL_IDS

        # Verify predefined mappings
        assert MODEL_PROVIDERS["chatgpt"] == "openai"
        assert MODEL_PROVIDERS["gemini"] == "google"
        assert MODEL_PROVIDERS["claude"] == "anthropic"
        assert MODEL_PROVIDERS["deepseek"] == "deepseek"

        # Verify default model IDs
        assert DEFAULT_MODEL_IDS["chatgpt"] == "gpt-4o"
        assert DEFAULT_MODEL_IDS["gemini"] == "gemini-1.5-pro"
        assert DEFAULT_MODEL_IDS["claude"] == "claude-sonnet-4-20250514"
        assert DEFAULT_MODEL_IDS["deepseek"] == "deepseek-chat"

    def test_supported_models_count(self):
        """Test that all supported models have providers and defaults."""
        from src.services.llm_config.service import MODEL_PROVIDERS, DEFAULT_MODEL_IDS

        assert len(MODEL_PROVIDERS) == 4
        assert len(DEFAULT_MODEL_IDS) == 4
        assert set(MODEL_PROVIDERS.keys()) == set(DEFAULT_MODEL_IDS.keys())


@pytest.mark.unit
class TestLLMConfigService:
    """Tests for LLMConfigService."""

    def test_cache_ttl_check(self):
        """Test cache validity based on TTL."""
        import time
        from src.services.llm_config.service import LLMConfigService

        service = LLMConfigService()

        # Cache is invalid when timestamp is 0
        assert service._is_cache_valid() is False

        # Set timestamp to now
        service._cache_timestamp = time.time()
        assert service._is_cache_valid() is True

        # Set timestamp to past TTL
        service._cache_timestamp = time.time() - service.CACHE_TTL_SECONDS - 1
        assert service._is_cache_valid() is False

    def test_invalidate_cache(self):
        """Test manual cache invalidation."""
        import time
        from src.services.llm_config.service import LLMConfigService

        service = LLMConfigService()
        service._cache_timestamp = time.time()

        # Cache should be valid
        assert service._is_cache_valid() is True

        # Invalidate
        service.invalidate_cache()

        # Cache should now be invalid
        assert service._is_cache_valid() is False
        assert service._cache_timestamp == 0


@pytest.mark.unit
class TestLLMConfigServiceAsync:
    """Async tests for LLMConfigService."""

    @pytest.mark.asyncio
    async def test_get_config_from_cache(self):
        """Test getting config from in-memory cache."""
        import time
        from src.services.llm_config.service import LLMConfigService, LLMConfigData

        service = LLMConfigService()

        # Populate cache directly
        service._cache = {
            "chatgpt": LLMConfigData(
                model_name="chatgpt",
                enabled=True,
                provider="openai",
                api_key="sk-cached-key",
                model_id="gpt-4o",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            )
        }
        service._cache_timestamp = time.time()

        config = await service.get_config("chatgpt")

        assert config is not None
        assert config.model_name == "chatgpt"
        assert config.api_key == "sk-cached-key"

    @pytest.mark.asyncio
    async def test_get_config_disabled_returns_none(self):
        """Test that disabled models return None."""
        import time
        from src.services.llm_config.service import LLMConfigService, LLMConfigData

        service = LLMConfigService()

        # Populate cache with disabled model
        service._cache = {
            "disabled_model": LLMConfigData(
                model_name="disabled_model",
                enabled=False,
                provider="openai",
                api_key="sk-key",
                model_id="gpt-4o",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            )
        }
        service._cache_timestamp = time.time()

        config = await service.get_config("disabled_model")

        assert config is None

    @pytest.mark.asyncio
    async def test_get_enabled_models(self):
        """Test getting list of enabled models."""
        import time
        from src.services.llm_config.service import LLMConfigService, LLMConfigData

        service = LLMConfigService()

        # Populate cache with mix of enabled/disabled
        service._cache = {
            "chatgpt": LLMConfigData(
                model_name="chatgpt",
                enabled=True,
                provider="openai",
                api_key="sk-key1",
                model_id="gpt-4o",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            ),
            "gemini": LLMConfigData(
                model_name="gemini",
                enabled=True,
                provider="google",
                api_key="goog-key",
                model_id="gemini-1.5-pro",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            ),
            "disabled": LLMConfigData(
                model_name="disabled",
                enabled=False,
                provider="openai",
                api_key="sk-disabled",
                model_id="gpt-4o",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            ),
        }
        service._cache_timestamp = time.time()

        # Patch at module level where settings is imported
        with patch.object(service, '_is_cache_valid', return_value=True):
            # Mock the settings import inside the method
            import src.services.llm_config.service as llm_service_module
            original_settings = llm_service_module.settings if hasattr(llm_service_module, 'settings') else None

            # The method imports settings inside, so we need to patch at import location
            with patch("src.core.config.settings") as mock_settings:
                mock_settings.ai_models_list = []
                enabled = await service.get_enabled_models()

        assert "chatgpt" in enabled
        assert "gemini" in enabled
        assert "disabled" not in enabled

    @pytest.mark.asyncio
    async def test_list_all_returns_all_configs(self):
        """Test listing all configs including disabled."""
        import time
        from src.services.llm_config.service import LLMConfigService, LLMConfigData

        service = LLMConfigService()

        # Populate cache
        service._cache = {
            "model1": LLMConfigData(
                model_name="model1",
                enabled=True,
                provider="openai",
                api_key="key1",
                model_id="gpt-4o",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            ),
            "model2": LLMConfigData(
                model_name="model2",
                enabled=False,
                provider="google",
                api_key="key2",
                model_id="gemini",
                timeout_ms=30000,
                max_tokens=1000,
                prompt_path=None,
            ),
        }
        service._cache_timestamp = time.time()

        all_configs = await service.list_all()

        assert len(all_configs) == 2
        model_names = [c.model_name for c in all_configs]
        assert "model1" in model_names
        assert "model2" in model_names


@pytest.mark.unit
class TestLLMConfigAPISchemas:
    """Tests for LLM config API schemas."""

    def test_llm_config_response_schema(self):
        """Test LLMConfigResponse schema structure."""
        from src.api.v1.llm_configs import LLMConfigResponse

        response = LLMConfigResponse(
            model_name="chatgpt",
            enabled=True,
            provider="openai",
            api_key_masked="****-test",
            model_id="gpt-4o",
            timeout_ms=30000,
            max_tokens=1000,
            prompt_path=None,
            validation_status="ok",
            last_validated_at=None,
        )

        assert response.model_name == "chatgpt"
        assert response.api_key_masked == "****-test"
        assert response.validation_status == "ok"

    def test_llm_config_create_schema(self):
        """Test LLMConfigCreate schema."""
        from src.api.v1.llm_configs import LLMConfigCreate

        # Provider is now automatically determined by model name
        request = LLMConfigCreate(
            api_key="sk-real-key",
            model_id="gpt-4o",
            enabled=True,
        )

        assert request.api_key == "sk-real-key"
        assert request.model_id == "gpt-4o"
        assert request.enabled is True
        assert request.timeout_ms == 30000  # Default
        assert request.max_tokens == 1000  # Default

    def test_llm_config_patch_allows_partial(self):
        """Test that patch request allows partial updates."""
        from src.api.v1.llm_configs import LLMConfigPatch

        # Only updating enabled flag
        request = LLMConfigPatch(enabled=False)

        assert request.enabled is False
        assert request.api_key is None
        assert request.model_id is None


@pytest.mark.unit
class TestAPIKeyMasking:
    """Tests for API key masking in responses."""

    def test_mask_api_key_function(self):
        """Test API key masking shows only last 4 chars."""
        from src.api.v1.llm_configs import _mask_api_key

        # Normal key
        masked = _mask_api_key("sk-abcdefghijklmnop")
        assert masked == "****mnop"
        assert "sk-" not in masked

        # Short key (4 chars or less returns just ****)
        masked = _mask_api_key("abc")
        assert masked == "****"

        # Empty key
        masked = _mask_api_key("")
        assert masked == "****"

    def test_mask_preserves_last_four_chars(self):
        """Test that masking preserves exactly last 4 characters."""
        from src.api.v1.llm_configs import _mask_api_key

        key = "test-key-with-suffix1234"
        masked = _mask_api_key(key)

        assert masked.endswith("1234")
        assert masked == "****1234"


@pytest.mark.unit
class TestLLMConfigServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_llm_config_service_returns_singleton(self):
        """Test that get_llm_config_service returns same instance."""
        from src.services.llm_config import get_llm_config_service

        service1 = get_llm_config_service()
        service2 = get_llm_config_service()

        assert service1 is service2
