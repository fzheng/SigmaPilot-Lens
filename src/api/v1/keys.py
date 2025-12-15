"""API key management endpoints (admin only)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, status

from src.api.deps import AdminKey
from src.core.security import generate_api_key, get_key_prefix
from src.models.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyDetailResponse,
)

router = APIRouter()


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key",
    description="Create a new API key. Admin only.",
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    admin_key: AdminKey,
):
    """
    Create a new API key.

    The full key is only returned once on creation.
    Store it securely as it cannot be retrieved later.
    """
    full_key, key_hash = generate_api_key()
    key_prefix = get_key_prefix(full_key)

    # TODO: Persist to database

    return ApiKeyCreateResponse(
        id="key-placeholder",
        name=request.name,
        key=full_key,
        key_prefix=key_prefix,
        expires_at=request.expires_at,
        created_at=datetime.utcnow(),
    )


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys",
    description="List all API keys. Admin only.",
)
async def list_api_keys(
    admin_key: AdminKey,
    include_expired: bool = Query(False, description="Include expired keys"),
    include_deleted: bool = Query(False, description="Include deleted keys"),
):
    """
    List all API keys.

    Optionally include expired and deleted keys.
    """
    # TODO: Implement database query
    return ApiKeyListResponse(items=[])


@router.get(
    "/{key_id}",
    response_model=ApiKeyDetailResponse,
    summary="Get API key details",
    description="Get details of a specific API key. Admin only.",
)
async def get_api_key(
    key_id: str,
    admin_key: AdminKey,
):
    """
    Get details of an API key.

    Includes usage statistics.
    """
    # TODO: Implement database query
    raise NotImplementedError("API key query not implemented yet")


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete API key",
    description="Revoke an API key. Admin only.",
)
async def delete_api_key(
    key_id: str,
    admin_key: AdminKey,
):
    """
    Revoke an API key.

    The key will be soft-deleted and can no longer be used.
    """
    # TODO: Implement soft delete
    pass
