"""Tests for prompt management."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone
from httpx import AsyncClient


@pytest.fixture
def sample_prompt_data():
    """Sample prompt data for tests."""
    from src.services.prompt.service import PromptData

    return PromptData(
        id="550e8400-e29b-41d4-a716-446655440000",
        name="core_decision",
        version="v1",
        prompt_type="core",
        model_name=None,
        content="# Core Decision Prompt\n\n{enriched_event}\n{constraints}",
        content_hash="abc123def456",
        is_active=True,
        description="Core decision prompt v1",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_wrapper_prompt_data():
    """Sample wrapper prompt data for tests."""
    from src.services.prompt.service import PromptData

    return PromptData(
        id="660e8400-e29b-41d4-a716-446655440001",
        name="chatgpt_wrapper",
        version="v1",
        prompt_type="wrapper",
        model_name="chatgpt",
        content="# ChatGPT Wrapper\n\n{core_prompt}",
        content_hash="def456abc123",
        is_active=True,
        description="ChatGPT wrapper prompt v1",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
class TestPromptService:
    """Tests for PromptService."""

    @pytest.mark.asyncio
    async def test_get_prompt_from_cache(self, sample_prompt_data):
        """Test getting a prompt from cache."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        # Manually populate cache
        service._cache = {
            "core_decision:v1": sample_prompt_data,
        }
        service._cache_timestamp = 9999999999  # Far future

        result = await service.get_prompt("core_decision", "v1")

        assert result is not None
        assert result.name == "core_decision"
        assert result.version == "v1"

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self):
        """Test getting a non-existent prompt."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {}
        service._cache_timestamp = 9999999999

        result = await service.get_prompt("nonexistent", "v1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_core_prompt(self, sample_prompt_data):
        """Test getting the core prompt."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {
            "core_decision:v1": sample_prompt_data,
        }
        service._cache_timestamp = 9999999999

        result = await service.get_core_prompt("v1")

        assert result is not None
        assert result.prompt_type == "core"

    @pytest.mark.asyncio
    async def test_get_wrapper_prompt(self, sample_wrapper_prompt_data):
        """Test getting a wrapper prompt."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {
            "chatgpt_wrapper:v1": sample_wrapper_prompt_data,
        }
        service._cache_timestamp = 9999999999

        result = await service.get_wrapper_prompt("chatgpt", "v1")

        assert result is not None
        assert result.prompt_type == "wrapper"
        assert result.model_name == "chatgpt"

    @pytest.mark.asyncio
    async def test_render_prompt(self, sample_prompt_data, sample_wrapper_prompt_data):
        """Test rendering a complete prompt."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {
            "core_decision:v1": sample_prompt_data,
            "chatgpt_wrapper:v1": sample_wrapper_prompt_data,
        }
        service._cache_timestamp = 9999999999

        rendered, version, hash = await service.render_prompt(
            model_name="chatgpt",
            enriched_event={"signal": "BUY", "price": 100.0},
            constraints={"max_position": 1000},
        )

        assert "chatgpt_v1_core_v1" in version
        assert len(hash) == 64  # SHA-256 hash
        assert "signal" in rendered
        assert "BUY" in rendered

    @pytest.mark.asyncio
    async def test_render_prompt_missing_core(self, sample_wrapper_prompt_data):
        """Test render fails when core prompt is missing."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {
            "chatgpt_wrapper:v1": sample_wrapper_prompt_data,
        }
        service._cache_timestamp = 9999999999

        with pytest.raises(ValueError) as exc_info:
            await service.render_prompt(
                model_name="chatgpt",
                enriched_event={},
                constraints={},
            )

        assert "Core prompt" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_render_prompt_missing_wrapper(self, sample_prompt_data):
        """Test render fails when wrapper prompt is missing."""
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache = {
            "core_decision:v1": sample_prompt_data,
        }
        service._cache_timestamp = 9999999999

        with pytest.raises(ValueError) as exc_info:
            await service.render_prompt(
                model_name="unknown",
                enriched_event={},
                constraints={},
            )

        assert "Wrapper prompt" in str(exc_info.value)

    def test_compute_hash(self):
        """Test content hash computation."""
        from src.services.prompt.service import PromptService

        hash1 = PromptService._compute_hash("test content")
        hash2 = PromptService._compute_hash("test content")
        hash3 = PromptService._compute_hash("different content")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64

    def test_cache_validity(self):
        """Test cache TTL validation."""
        import time
        from src.services.prompt.service import PromptService

        service = PromptService()

        # Cache is invalid when timestamp is 0
        service._cache_timestamp = 0
        assert service._is_cache_valid() is False

        # Cache is valid when timestamp is recent
        service._cache_timestamp = time.time()
        assert service._is_cache_valid() is True

        # Cache is invalid when timestamp is old
        service._cache_timestamp = time.time() - 600  # 10 min ago
        assert service._is_cache_valid() is False

    def test_invalidate_cache(self):
        """Test cache invalidation."""
        import time
        from src.services.prompt.service import PromptService

        service = PromptService()
        service._cache_timestamp = time.time()

        service.invalidate_cache()

        assert service._cache_timestamp == 0
        assert service._is_cache_valid() is False


@pytest.mark.unit
class TestPromptData:
    """Tests for PromptData dataclass."""

    def test_from_orm(self):
        """Test creating PromptData from ORM model."""
        from src.services.prompt.service import PromptData
        from src.models.orm.prompt import Prompt
        import uuid

        now = datetime.now(timezone.utc)
        prompt_id = uuid.uuid4()

        # Create a mock ORM object
        orm_prompt = MagicMock(spec=Prompt)
        orm_prompt.id = prompt_id
        orm_prompt.name = "core_decision"
        orm_prompt.version = "v1"
        orm_prompt.prompt_type = "core"
        orm_prompt.model_name = None
        orm_prompt.content = "# Test"
        orm_prompt.content_hash = "abc123"
        orm_prompt.is_active = True
        orm_prompt.description = "Test prompt"
        orm_prompt.created_at = now

        data = PromptData.from_orm(orm_prompt)

        assert data.id == str(prompt_id)
        assert data.name == "core_decision"
        assert data.version == "v1"
        assert data.prompt_type == "core"
        assert data.content == "# Test"
        assert data.is_active is True


@pytest.mark.unit
class TestPromptAuthRequirements:
    """Tests for authentication requirements on prompt endpoints."""

    def test_prompt_endpoints_require_admin_scope(self):
        """Test that prompt endpoints require admin scope."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            # Read token should not work
            ctx = get_auth_context(authorization="Bearer read-secret")
            dependency = require_scope(Scope.ADMIN)
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 403

            # Submit token should not work
            ctx = get_auth_context(authorization="Bearer submit-secret")
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 403

            # Admin token should work
            ctx = get_auth_context(authorization="Bearer admin-secret")
            result = dependency(ctx)
            assert result.authenticated is True

    def test_prompt_endpoints_allow_all_in_mode_none(self):
        """Test that prompt endpoints allow all requests in AUTH_MODE=none."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization=None)
            assert ctx.has_scope(Scope.ADMIN) is True


@pytest.mark.unit
class TestPromptAPIIntegration:
    """Integration tests for prompt API endpoints using async client."""

    @pytest.mark.asyncio
    async def test_list_prompts_endpoint(self, client: AsyncClient):
        """Test GET /prompts endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.list_all = AsyncMock(return_value=[])
            mock_get_service.return_value = mock_service

            response = await client.get("/api/v1/prompts")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total" in data

    @pytest.mark.asyncio
    async def test_available_prompts_endpoint(self, client: AsyncClient):
        """Test GET /prompts/available endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_available_prompts = AsyncMock(return_value={
                "core_versions": ["v1"],
                "wrappers": {"chatgpt": ["v1"]},
            })
            mock_get_service.return_value = mock_service

            response = await client.get("/api/v1/prompts/available")

            assert response.status_code == 200
            data = response.json()
            assert "core_versions" in data
            assert "wrappers" in data

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self, client: AsyncClient):
        """Test GET /prompts/{name}/{version} returns 404 when not found."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_prompt = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            response = await client.get("/api/v1/prompts/nonexistent/v1")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_prompt_endpoint(self, client: AsyncClient, sample_prompt_data):
        """Test POST /prompts endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(return_value=sample_prompt_data)
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/api/v1/prompts",
                json={
                    "name": "core_decision",
                    "version": "v1",
                    "prompt_type": "core",
                    "content": "# Core Prompt",
                },
            )

            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_delete_prompt_endpoint(self, client: AsyncClient):
        """Test DELETE /prompts/{name}/{version} endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(return_value=True)
            mock_get_service.return_value = mock_service

            response = await client.delete("/api/v1/prompts/core_decision/v1")

            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_render_prompt_endpoint(self, client: AsyncClient):
        """Test POST /prompts/render endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.render_prompt = AsyncMock(return_value=(
                "Rendered content",
                "chatgpt_v1_core_v1",
                "abc123def456",
            ))
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/api/v1/prompts/render",
                json={
                    "model_name": "chatgpt",
                    "enriched_event": {"signal": "BUY"},
                    "constraints": {"max_position": 1000},
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "rendered_prompt" in data
            assert "prompt_version" in data
            assert "prompt_hash" in data

    @pytest.mark.asyncio
    async def test_update_prompt_endpoint(self, client: AsyncClient, sample_prompt_data):
        """Test PUT /prompts/{name}/{version} endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(return_value=sample_prompt_data)
            mock_get_service.return_value = mock_service

            response = await client.put(
                "/api/v1/prompts/core_decision/v1",
                json={
                    "content": "# Updated Content",
                    "description": "Updated description",
                },
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_prompt_endpoint(self, client: AsyncClient, sample_prompt_data):
        """Test PATCH /prompts/{name}/{version} endpoint."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            sample_prompt_data.is_active = False
            mock_service.update = AsyncMock(return_value=sample_prompt_data)
            mock_get_service.return_value = mock_service

            response = await client.patch(
                "/api/v1/prompts/core_decision/v1",
                json={"is_active": False},
            )

            assert response.status_code == 200
            assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_create_prompt_validation_error(self, client: AsyncClient):
        """Test POST /prompts with validation error."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(
                side_effect=ValueError("model_name is required for wrapper prompts")
            )
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/api/v1/prompts",
                json={
                    "name": "test_wrapper",
                    "version": "v1",
                    "prompt_type": "wrapper",
                    "content": "# Wrapper",
                },
            )

            assert response.status_code == 400
            assert "VALIDATION_ERROR" in response.json()["detail"]["error"]["code"]

    @pytest.mark.asyncio
    async def test_render_prompt_error(self, client: AsyncClient):
        """Test POST /prompts/render with missing prompts."""
        with patch("src.api.v1.prompts.get_prompt_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.render_prompt = AsyncMock(
                side_effect=ValueError("Wrapper prompt for unknown version v1 not found")
            )
            mock_get_service.return_value = mock_service

            response = await client.post(
                "/api/v1/prompts/render",
                json={
                    "model_name": "unknown",
                    "enriched_event": {},
                    "constraints": {},
                },
            )

            assert response.status_code == 400
            assert "RENDER_ERROR" in response.json()["detail"]["error"]["code"]

    @pytest.mark.asyncio
    async def test_list_prompts_filter_invalid_type(self, client: AsyncClient):
        """Test GET /prompts with invalid prompt_type filter."""
        response = await client.get("/api/v1/prompts?prompt_type=invalid")

        assert response.status_code == 400
        assert "INVALID_TYPE" in response.json()["detail"]["error"]["code"]
