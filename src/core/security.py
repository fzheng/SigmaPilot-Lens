"""Security utilities for API key management."""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple


def generate_api_key(prefix: str = "lens_k1_") -> Tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (full_key, key_hash)
    """
    # Generate 32 random bytes, encode as base64-like string
    random_bytes = secrets.token_urlsafe(32)
    full_key = f"{prefix}{random_bytes}"
    key_hash = hash_api_key(full_key)
    return full_key, key_hash


def hash_api_key(key: str) -> str:
    """
    Hash an API key using SHA-256.

    Args:
        key: The full API key

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(key.encode()).hexdigest()


def get_key_prefix(key: str, length: int = 12) -> str:
    """
    Extract the prefix from an API key for display purposes.

    Args:
        key: The full API key
        length: Length of prefix to extract

    Returns:
        Key prefix (e.g., "lens_k1_xxxx")
    """
    return key[:length] if len(key) >= length else key


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """
    Verify an API key against its stored hash.

    Args:
        provided_key: The API key provided in the request
        stored_hash: The stored hash to compare against

    Returns:
        True if the key matches, False otherwise
    """
    provided_hash = hash_api_key(provided_key)
    return secrets.compare_digest(provided_hash, stored_hash)


def is_key_expired(expires_at: Optional[datetime]) -> bool:
    """
    Check if an API key has expired.

    Args:
        expires_at: Expiration datetime (None means never expires)

    Returns:
        True if expired, False otherwise
    """
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    # Ensure expires_at is timezone-aware
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now > expires_at
