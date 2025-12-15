"""API dependencies for dependency injection."""

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthenticationError, RateLimitError
from src.core.rate_limit import get_rate_limiter
from src.core.security import hash_api_key, is_key_expired, verify_api_key


async def get_db() -> AsyncSession:
    """Get database session."""
    # TODO: Implement database session factory
    # async with async_session_maker() as session:
    #     yield session
    raise NotImplementedError("Database session not implemented yet")


async def get_api_key(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> str:
    """
    Extract and validate API key from request header.

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": AuthenticationError().to_dict()},
        )
    return x_api_key


async def verify_api_key_dep(
    api_key: Annotated[str, Depends(get_api_key)],
    # db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Verify API key and return key details.

    Returns:
        Dictionary with key_id, key_hash, and is_admin flag
    """
    # TODO: Look up API key in database
    # For now, just check against admin key
    if api_key == settings.API_KEY_ADMIN:
        return {
            "key_id": "admin",
            "key_hash": hash_api_key(api_key),
            "is_admin": True,
        }

    # TODO: Query database for API key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": AuthenticationError().to_dict()},
    )


async def require_admin(
    key_info: Annotated[dict, Depends(verify_api_key_dep)],
) -> dict:
    """
    Require admin API key.

    Raises:
        HTTPException: If the API key is not an admin key
    """
    if not key_info.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Admin access required"}},
        )
    return key_info


async def check_rate_limit(
    key_info: Annotated[dict, Depends(verify_api_key_dep)],
) -> dict:
    """
    Check rate limit for the API key.

    Raises:
        HTTPException: If rate limit is exceeded
    """
    if not settings.RATE_LIMIT_ENABLED:
        return key_info

    try:
        limiter = get_rate_limiter()
        is_allowed, remaining, retry_after = await limiter.is_allowed(key_info["key_hash"])

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": RateLimitError(retry_after).to_dict()},
                headers={"Retry-After": str(retry_after)},
            )

        # Add rate limit info to key_info for headers
        key_info["rate_limit_remaining"] = remaining
        return key_info

    except RuntimeError:
        # Rate limiter not initialized, skip check
        return key_info


# Type aliases for cleaner dependency injection
ApiKey = Annotated[str, Depends(get_api_key)]
VerifiedKey = Annotated[dict, Depends(verify_api_key_dep)]
AdminKey = Annotated[dict, Depends(require_admin)]
RateLimitedKey = Annotated[dict, Depends(check_rate_limit)]
