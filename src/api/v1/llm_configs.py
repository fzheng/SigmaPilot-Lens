"""LLM configuration management endpoints.

This module provides REST API endpoints for managing LLM provider configurations
at runtime. Allows updating API keys, enabling/disabling models, and testing
connections without container restarts.

Endpoints:
    GET    /llm-configs           - List all LLM configurations
    GET    /llm-configs/{model}   - Get configuration for a specific model
    PUT    /llm-configs/{model}   - Create or update a model configuration
    PATCH  /llm-configs/{model}   - Partial update (e.g., enable/disable)
    DELETE /llm-configs/{model}   - Delete a model configuration
    POST   /llm-configs/{model}/test - Test API key validity

Security:
    - Restricted to internal Docker network only
    - API keys are masked in responses (only last 4 chars shown)

Supported models:
    - chatgpt (OpenAI)
    - gemini (Google)
    - claude (Anthropic)
    - deepseek (DeepSeek)

Usage:
    # Add/update ChatGPT configuration
    PUT /llm-configs/chatgpt
    {
        "api_key": "sk-...",
        "model_id": "gpt-4o",
        "enabled": true
    }

    # Test the API key
    POST /llm-configs/chatgpt/test

    # Disable a model
    PATCH /llm-configs/chatgpt
    {"enabled": false}
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import AuthContext, require_admin
from src.observability.logging import get_logger
from src.services.llm_config import LLMConfigService, get_llm_config_service
from src.services.llm_config.service import MODEL_PROVIDERS, DEFAULT_MODEL_IDS

logger = get_logger(__name__)

router = APIRouter()


# Request/Response schemas
class LLMConfigCreate(BaseModel):
    """Request schema for creating/updating LLM configuration."""

    api_key: str = Field(..., min_length=1, description="API key for the provider")
    model_id: Optional[str] = Field(None, description="Model identifier (e.g., gpt-4o). Uses default if not specified.")
    enabled: bool = Field(True, description="Whether the model is enabled")
    timeout_ms: int = Field(30000, ge=1000, le=120000, description="Request timeout in milliseconds")
    max_tokens: int = Field(1000, ge=100, le=8000, description="Maximum tokens for response")


class LLMConfigPatch(BaseModel):
    """Request schema for partial updates."""

    enabled: Optional[bool] = Field(None, description="Enable/disable the model")
    api_key: Optional[str] = Field(None, min_length=1, description="New API key")
    model_id: Optional[str] = Field(None, description="New model identifier")
    timeout_ms: Optional[int] = Field(None, ge=1000, le=120000)
    max_tokens: Optional[int] = Field(None, ge=100, le=8000)


class LLMConfigResponse(BaseModel):
    """Response schema for LLM configuration (API key masked)."""

    model_name: str
    provider: str
    model_id: str
    enabled: bool
    timeout_ms: int
    max_tokens: int
    prompt_path: Optional[str]
    api_key_masked: str = Field(..., description="Masked API key (last 4 chars only)")
    validation_status: Optional[str] = None
    last_validated_at: Optional[datetime] = None


class LLMConfigListResponse(BaseModel):
    """Response schema for listing configurations."""

    items: List[LLMConfigResponse]
    total: int


class LLMConfigTestResponse(BaseModel):
    """Response schema for API key test."""

    model_name: str
    success: bool
    message: str
    latency_ms: int


def _mask_api_key(api_key: str) -> str:
    """Mask API key, showing only last 4 characters."""
    if len(api_key) <= 4:
        return "****"
    return f"****{api_key[-4:]}"


def _get_service() -> LLMConfigService:
    """Get the LLM config service instance."""
    return get_llm_config_service()


@router.get(
    "",
    response_model=LLMConfigListResponse,
    summary="List all LLM configurations",
    description="Get all configured LLM providers with masked API keys.",
)
async def list_llm_configs(_auth: AuthContext = Depends(require_admin)):
    """List all LLM configurations."""
    service = _get_service()
    configs = await service.list_all()

    items = [
        LLMConfigResponse(
            model_name=c.model_name,
            provider=c.provider,
            model_id=c.model_id,
            enabled=c.enabled,
            timeout_ms=c.timeout_ms,
            max_tokens=c.max_tokens,
            prompt_path=c.prompt_path,
            api_key_masked=_mask_api_key(c.api_key),
        )
        for c in configs
    ]

    return LLMConfigListResponse(items=items, total=len(items))


@router.get(
    "/{model_name}",
    response_model=LLMConfigResponse,
    summary="Get LLM configuration",
    description="Get configuration for a specific model.",
)
async def get_llm_config(model_name: str, _auth: AuthContext = Depends(require_admin)):
    """Get configuration for a specific model."""
    service = _get_service()
    config = await service.get_config(model_name)

    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    return LLMConfigResponse(
        model_name=config.model_name,
        provider=config.provider,
        model_id=config.model_id,
        enabled=config.enabled,
        timeout_ms=config.timeout_ms,
        max_tokens=config.max_tokens,
        prompt_path=config.prompt_path,
        api_key_masked=_mask_api_key(config.api_key),
    )


@router.put(
    "/{model_name}",
    response_model=LLMConfigResponse,
    summary="Create or update LLM configuration",
    description="Create a new LLM configuration or update an existing one. Provider is determined automatically by model name.",
)
async def create_or_update_llm_config(
    model_name: str, request: LLMConfigCreate, _auth: AuthContext = Depends(require_admin)
):
    """Create or update an LLM configuration."""
    # Validate model name and get provider
    if model_name not in MODEL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model name. Must be one of: {', '.join(MODEL_PROVIDERS.keys())}"
        )

    # Use predefined provider (not user-editable)
    provider = MODEL_PROVIDERS[model_name]

    # Use default model_id if not specified
    model_id = request.model_id or DEFAULT_MODEL_IDS[model_name]

    service = _get_service()
    config = await service.create_or_update(
        model_name=model_name,
        provider=provider,
        api_key=request.api_key,
        model_id=model_id,
        enabled=request.enabled,
        timeout_ms=request.timeout_ms,
        max_tokens=request.max_tokens,
        prompt_path=None,
    )

    logger.info(f"LLM config updated for {model_name}")

    return LLMConfigResponse(
        model_name=config.model_name,
        provider=config.provider,
        model_id=config.model_id,
        enabled=config.enabled,
        timeout_ms=config.timeout_ms,
        max_tokens=config.max_tokens,
        prompt_path=config.prompt_path,
        api_key_masked=_mask_api_key(config.api_key),
    )


@router.patch(
    "/{model_name}",
    response_model=LLMConfigResponse,
    summary="Partial update LLM configuration",
    description="Partially update an LLM configuration (e.g., enable/disable).",
)
async def patch_llm_config(
    model_name: str, request: LLMConfigPatch, _auth: AuthContext = Depends(require_admin)
):
    """Partially update an LLM configuration."""
    service = _get_service()

    # Get existing config
    existing = await service.get_config(model_name)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    # Build update with existing values as defaults
    config = await service.create_or_update(
        model_name=model_name,
        provider=existing.provider,
        api_key=request.api_key if request.api_key else existing.api_key,
        model_id=request.model_id if request.model_id else existing.model_id,
        enabled=request.enabled if request.enabled is not None else existing.enabled,
        timeout_ms=request.timeout_ms if request.timeout_ms else existing.timeout_ms,
        max_tokens=request.max_tokens if request.max_tokens else existing.max_tokens,
        prompt_path=existing.prompt_path,
    )

    logger.info(f"LLM config patched for {model_name}")

    return LLMConfigResponse(
        model_name=config.model_name,
        provider=config.provider,
        model_id=config.model_id,
        enabled=config.enabled,
        timeout_ms=config.timeout_ms,
        max_tokens=config.max_tokens,
        prompt_path=config.prompt_path,
        api_key_masked=_mask_api_key(config.api_key),
    )


@router.delete(
    "/{model_name}",
    summary="Delete LLM configuration",
    description="Delete an LLM configuration. The model will fall back to environment variables if configured.",
)
async def delete_llm_config(model_name: str, _auth: AuthContext = Depends(require_admin)):
    """Delete an LLM configuration."""
    service = _get_service()
    deleted = await service.delete(model_name)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    logger.info(f"LLM config deleted for {model_name}")

    return {"status": "deleted", "model_name": model_name}


@router.post(
    "/{model_name}/test",
    response_model=LLMConfigTestResponse,
    summary="Test API key",
    description="Test if the API key is valid by making a minimal API call.",
)
async def test_llm_config(model_name: str, _auth: AuthContext = Depends(require_admin)):
    """Test if the API key is valid."""
    service = _get_service()

    # Check config exists
    config = await service.get_config(model_name)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    result = await service.test_api_key(model_name)

    return LLMConfigTestResponse(
        model_name=model_name,
        success=result["success"],
        message=result["message"],
        latency_ms=result["latency_ms"],
    )


@router.post(
    "/{model_name}/enable",
    response_model=LLMConfigResponse,
    summary="Enable a model",
    description="Enable a previously disabled model.",
)
async def enable_llm_config(model_name: str, _auth: AuthContext = Depends(require_admin)):
    """Enable a model."""
    service = _get_service()

    success = await service.set_enabled(model_name, True)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    config = await service.get_config(model_name)
    return LLMConfigResponse(
        model_name=config.model_name,
        provider=config.provider,
        model_id=config.model_id,
        enabled=config.enabled,
        timeout_ms=config.timeout_ms,
        max_tokens=config.max_tokens,
        prompt_path=config.prompt_path,
        api_key_masked=_mask_api_key(config.api_key),
    )


@router.post(
    "/{model_name}/disable",
    response_model=LLMConfigResponse,
    summary="Disable a model",
    description="Disable a model without deleting its configuration.",
)
async def disable_llm_config(model_name: str, _auth: AuthContext = Depends(require_admin)):
    """Disable a model."""
    service = _get_service()

    success = await service.set_enabled(model_name, False)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration not found for model: {model_name}"
        )

    # Get config (will return None because disabled, so fetch directly)
    async with get_llm_config_service()._cache_lock:
        pass  # Just to trigger refresh
    await service._refresh_cache()

    # Return the disabled config
    for c in await service.list_all():
        if c.model_name == model_name:
            return LLMConfigResponse(
                model_name=c.model_name,
                provider=c.provider,
                model_id=c.model_id,
                enabled=c.enabled,
                timeout_ms=c.timeout_ms,
                max_tokens=c.max_tokens,
                prompt_path=c.prompt_path,
                api_key_masked=_mask_api_key(c.api_key),
            )

    raise HTTPException(status_code=404, detail="Configuration not found after update")
