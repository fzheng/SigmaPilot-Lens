"""API key management schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    """Request schema for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255, description="Name/description for the key")
    expires_at: Optional[datetime] = Field(None, description="Expiration datetime (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "executor-1",
                "expires_at": "2025-01-15T00:00:00Z",
            }
        }


class ApiKeyCreateResponse(BaseModel):
    """Response schema for API key creation."""

    id: str = Field(..., description="Key ID")
    name: str = Field(..., description="Key name")
    key: str = Field(..., description="Full API key (only shown once)")
    key_prefix: str = Field(..., description="Key prefix for display")
    expires_at: Optional[datetime] = Field(None, description="Expiration datetime")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "key-001",
                "name": "executor-1",
                "key": "lens_k1_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "key_prefix": "lens_k1_xxxx",
                "expires_at": "2025-01-15T00:00:00Z",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class ApiKeyListItem(BaseModel):
    """API key item for list responses."""

    id: str
    name: str
    key_prefix: str
    is_admin: bool = False
    expires_at: Optional[datetime] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    """Response schema for API key list endpoint."""

    items: List[ApiKeyListItem]


class ApiKeyUsage(BaseModel):
    """API key usage statistics."""

    requests_24h: int = Field(..., description="Requests in last 24 hours")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")


class ApiKeyDetailResponse(BaseModel):
    """Response schema for API key detail endpoint."""

    id: str
    name: str
    key_prefix: str
    is_admin: bool = False
    expires_at: Optional[datetime] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
    usage: Optional[ApiKeyUsage] = None
