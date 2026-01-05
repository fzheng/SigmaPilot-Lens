"""Prompt management endpoints.

This module provides REST API endpoints for managing AI prompts
at runtime. Allows creating, updating, and versioning prompts
without container restarts.

Endpoints:
    GET    /prompts                    - List all prompts
    GET    /prompts/available          - Get available prompt versions
    GET    /prompts/{name}/{version}   - Get a specific prompt
    POST   /prompts                    - Create a new prompt
    PUT    /prompts/{name}/{version}   - Update a prompt
    PATCH  /prompts/{name}/{version}   - Partial update (e.g., activate/deactivate)
    DELETE /prompts/{name}/{version}   - Delete a prompt
    POST   /prompts/render             - Render a prompt with data

Security:
    - All endpoints require lens:admin scope

Prompt Types:
    - core: Shared decision logic (core_decision)
    - wrapper: Provider-specific formatting (chatgpt_wrapper, gemini_wrapper, etc.)

Usage:
    # Create a new core prompt version
    POST /prompts
    {
        "name": "core_decision",
        "version": "v2",
        "prompt_type": "core",
        "content": "# Trading Signal Decision Framework..."
    }

    # Update a wrapper prompt
    PUT /prompts/chatgpt_wrapper/v1
    {
        "content": "..."
    }

    # Deactivate a prompt version
    PATCH /prompts/core_decision/v1
    {"is_active": false}
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import AuthContext, require_admin
from src.observability.logging import get_logger
from src.services.prompt import PromptService, get_prompt_service

logger = get_logger(__name__)

router = APIRouter()


# Request/Response schemas
class PromptCreate(BaseModel):
    """Request schema for creating a prompt."""

    name: str = Field(..., min_length=1, max_length=100, description="Prompt name (e.g., core_decision, chatgpt_wrapper)")
    version: str = Field(..., min_length=1, max_length=20, description="Version string (e.g., v1, v2)")
    prompt_type: str = Field(..., description="Type: 'core' or 'wrapper'")
    content: str = Field(..., min_length=1, description="Prompt content")
    model_name: Optional[str] = Field(None, max_length=50, description="For wrapper prompts, which model this is for")
    description: Optional[str] = Field(None, description="Optional description")


class PromptUpdate(BaseModel):
    """Request schema for updating a prompt."""

    content: str = Field(..., min_length=1, description="New prompt content")
    description: Optional[str] = Field(None, description="Optional description")


class PromptPatch(BaseModel):
    """Request schema for partial updates."""

    content: Optional[str] = Field(None, min_length=1, description="New prompt content")
    description: Optional[str] = Field(None, description="New description")
    is_active: Optional[bool] = Field(None, description="Activate/deactivate")


class PromptResponse(BaseModel):
    """Response schema for a prompt."""

    id: str
    name: str
    version: str
    prompt_type: str
    model_name: Optional[str]
    content: str
    content_hash: str
    is_active: bool
    description: Optional[str]
    created_at: datetime


class PromptListResponse(BaseModel):
    """Response schema for listing prompts."""

    items: List[PromptResponse]
    total: int


class PromptAvailableResponse(BaseModel):
    """Response schema for available prompts."""

    core_versions: List[str]
    wrappers: dict


class PromptRenderRequest(BaseModel):
    """Request schema for rendering a prompt."""

    model_name: str = Field(..., description="Model name (chatgpt, gemini, claude, deepseek)")
    enriched_event: dict = Field(..., description="Enriched event data")
    constraints: dict = Field(..., description="Trading constraints")
    core_version: str = Field("v1", description="Core prompt version")
    wrapper_version: str = Field("v1", description="Wrapper prompt version")


class PromptRenderResponse(BaseModel):
    """Response schema for rendered prompt."""

    rendered_prompt: str
    prompt_version: str
    prompt_hash: str


def _get_service() -> PromptService:
    """Get the prompt service instance."""
    return get_prompt_service()


@router.get(
    "",
    response_model=PromptListResponse,
    summary="List all prompts",
    description="Get all prompts with optional filtering by type.",
)
async def list_prompts(
    prompt_type: Optional[str] = None,
    include_inactive: bool = False,
    _auth: AuthContext = Depends(require_admin),
):
    """List all prompts."""
    service = _get_service()

    if prompt_type and prompt_type not in ("core", "wrapper"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_TYPE", "message": "prompt_type must be 'core' or 'wrapper'"}},
        )

    prompts = await service.list_all(
        prompt_type=prompt_type,
        include_inactive=include_inactive,
    )

    items = [
        PromptResponse(
            id=p.id,
            name=p.name,
            version=p.version,
            prompt_type=p.prompt_type,
            model_name=p.model_name,
            content=p.content,
            content_hash=p.content_hash,
            is_active=p.is_active,
            description=p.description,
            created_at=p.created_at,
        )
        for p in prompts
    ]

    return PromptListResponse(items=items, total=len(items))


@router.get(
    "/available",
    response_model=PromptAvailableResponse,
    summary="Get available prompt versions",
    description="Get a summary of available prompt versions grouped by type.",
)
async def get_available_prompts(
    _auth: AuthContext = Depends(require_admin),
):
    """Get available prompt versions."""
    service = _get_service()
    available = await service.get_available_prompts()
    return PromptAvailableResponse(
        core_versions=available["core_versions"],
        wrappers=available["wrappers"],
    )


@router.get(
    "/{name}/{version}",
    response_model=PromptResponse,
    summary="Get a specific prompt",
    description="Get a prompt by name and version.",
)
async def get_prompt(
    name: str,
    version: str,
    _auth: AuthContext = Depends(require_admin),
):
    """Get a specific prompt."""
    service = _get_service()
    prompt = await service.get_prompt(name, version)

    if not prompt:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"Prompt {name} version {version} not found"}},
        )

    return PromptResponse(
        id=prompt.id,
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


@router.post(
    "",
    response_model=PromptResponse,
    status_code=201,
    summary="Create a new prompt",
    description="Create a new prompt. For wrapper prompts, model_name is required.",
)
async def create_prompt(
    prompt: PromptCreate,
    _auth: AuthContext = Depends(require_admin),
):
    """Create a new prompt."""
    service = _get_service()

    try:
        created = await service.create(
            name=prompt.name,
            version=prompt.version,
            prompt_type=prompt.prompt_type,
            content=prompt.content,
            model_name=prompt.model_name,
            description=prompt.description,
            created_by=_auth.subject,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "VALIDATION_ERROR", "message": str(e)}},
        )

    return PromptResponse(
        id=created.id,
        name=created.name,
        version=created.version,
        prompt_type=created.prompt_type,
        model_name=created.model_name,
        content=created.content,
        content_hash=created.content_hash,
        is_active=created.is_active,
        description=created.description,
        created_at=created.created_at,
    )


@router.put(
    "/{name}/{version}",
    response_model=PromptResponse,
    summary="Update a prompt",
    description="Update a prompt's content and description.",
)
async def update_prompt(
    name: str,
    version: str,
    prompt: PromptUpdate,
    _auth: AuthContext = Depends(require_admin),
):
    """Update a prompt."""
    service = _get_service()

    updated = await service.update(
        name=name,
        version=version,
        content=prompt.content,
        description=prompt.description,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"Prompt {name} version {version} not found"}},
        )

    return PromptResponse(
        id=updated.id,
        name=updated.name,
        version=updated.version,
        prompt_type=updated.prompt_type,
        model_name=updated.model_name,
        content=updated.content,
        content_hash=updated.content_hash,
        is_active=updated.is_active,
        description=updated.description,
        created_at=updated.created_at,
    )


@router.patch(
    "/{name}/{version}",
    response_model=PromptResponse,
    summary="Partial update a prompt",
    description="Partially update a prompt (e.g., activate/deactivate).",
)
async def patch_prompt(
    name: str,
    version: str,
    prompt: PromptPatch,
    _auth: AuthContext = Depends(require_admin),
):
    """Partially update a prompt."""
    service = _get_service()

    updated = await service.update(
        name=name,
        version=version,
        content=prompt.content,
        description=prompt.description,
        is_active=prompt.is_active,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"Prompt {name} version {version} not found"}},
        )

    return PromptResponse(
        id=updated.id,
        name=updated.name,
        version=updated.version,
        prompt_type=updated.prompt_type,
        model_name=updated.model_name,
        content=updated.content,
        content_hash=updated.content_hash,
        is_active=updated.is_active,
        description=updated.description,
        created_at=updated.created_at,
    )


@router.delete(
    "/{name}/{version}",
    status_code=204,
    summary="Delete a prompt",
    description="Delete a prompt by name and version.",
)
async def delete_prompt(
    name: str,
    version: str,
    _auth: AuthContext = Depends(require_admin),
):
    """Delete a prompt."""
    service = _get_service()

    deleted = await service.delete(name, version)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": f"Prompt {name} version {version} not found"}},
        )

    return None


@router.post(
    "/render",
    response_model=PromptRenderResponse,
    summary="Render a prompt with data",
    description="Render a complete prompt with enriched event data and constraints.",
)
async def render_prompt(
    request: PromptRenderRequest,
    _auth: AuthContext = Depends(require_admin),
):
    """Render a prompt with data."""
    service = _get_service()

    try:
        rendered, version, hash = await service.render_prompt(
            model_name=request.model_name,
            enriched_event=request.enriched_event,
            constraints=request.constraints,
            core_version=request.core_version,
            wrapper_version=request.wrapper_version,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "RENDER_ERROR", "message": str(e)}},
        )

    return PromptRenderResponse(
        rendered_prompt=rendered,
        prompt_version=version,
        prompt_hash=hash,
    )
