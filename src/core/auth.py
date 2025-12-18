"""Authentication and authorization module.

This module provides 3-mode authentication:
    - none: No auth (development mode)
    - psk: Pre-shared key tokens (Docker Compose deployments)
    - jwt: JWT validation (portable/production deployments)

Scopes:
    - lens:submit: POST /signals
    - lens:read: GET events, decisions, DLQ
    - lens:admin: LLM configs, DLQ retry/resolve (includes all scopes)

Usage:
    # In route handlers, use the require_scope dependency:
    @router.post("/signals")
    async def submit_signal(
        auth: AuthContext = Depends(require_scope("lens:submit"))
    ):
        ...

    # For WebSocket, extract token from Sec-WebSocket-Protocol header:
    # Sec-WebSocket-Protocol: bearer,<token>
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from fastapi import Depends, Header, HTTPException, Request, WebSocket, status

from src.core.config import settings
from src.observability.logging import get_logger

logger = get_logger(__name__)


class Scope(str, Enum):
    """Authorization scopes."""

    SUBMIT = "lens:submit"
    READ = "lens:read"
    ADMIN = "lens:admin"


# Scope hierarchy: admin includes all other scopes
SCOPE_HIERARCHY = {
    Scope.ADMIN: {Scope.SUBMIT, Scope.READ, Scope.ADMIN},
    Scope.SUBMIT: {Scope.SUBMIT},
    Scope.READ: {Scope.READ},
}


@dataclass
class AuthContext:
    """Authentication context for a request."""

    authenticated: bool
    scopes: Set[Scope]
    token_type: Optional[str] = None  # "psk" or "jwt"
    subject: Optional[str] = None  # For JWT: sub claim

    def has_scope(self, scope: Scope) -> bool:
        """Check if context has the given scope (including via hierarchy)."""
        for granted_scope in self.scopes:
            if scope in SCOPE_HIERARCHY.get(granted_scope, {granted_scope}):
                return True
        return False


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _validate_psk_token(token: str) -> Optional[AuthContext]:
    """Validate a PSK token and return the auth context.

    Args:
        token: The token to validate

    Returns:
        AuthContext if valid, None if not
    """
    # Check admin token first (grants all scopes)
    if settings.AUTH_TOKEN_ADMIN and token == settings.AUTH_TOKEN_ADMIN:
        return AuthContext(
            authenticated=True,
            scopes={Scope.ADMIN},
            token_type="psk",
            subject="admin",
        )

    # Check submit token
    if settings.AUTH_TOKEN_SUBMIT and token == settings.AUTH_TOKEN_SUBMIT:
        return AuthContext(
            authenticated=True,
            scopes={Scope.SUBMIT},
            token_type="psk",
            subject="submit",
        )

    # Check read token
    if settings.AUTH_TOKEN_READ and token == settings.AUTH_TOKEN_READ:
        return AuthContext(
            authenticated=True,
            scopes={Scope.READ},
            token_type="psk",
            subject="read",
        )

    return None


def _validate_jwt_token(token: str) -> Optional[AuthContext]:
    """Validate a JWT token and return the auth context.

    Args:
        token: The JWT to validate

    Returns:
        AuthContext if valid, None if not

    Raises:
        HTTPException: If JWT validation fails with specific error
    """
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError:
        logger.error("PyJWT not installed. Install with: pip install PyJWT[crypto]")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "CONFIG_ERROR", "message": "JWT support not configured"}},
        )

    # Build verification options
    verify_options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "require": ["exp", "iat"],
    }

    # Get the public key
    public_key = None

    if settings.AUTH_JWT_JWKS_URL:
        # Use JWKS endpoint
        try:
            jwks_client = PyJWKClient(settings.AUTH_JWT_JWKS_URL)
            # Get the signing key from the token header
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            public_key = signing_key.key
        except Exception as e:
            logger.warning(f"Failed to get signing key from JWKS: {e}")
            return None
    elif settings.AUTH_JWT_PUBLIC_KEY:
        # Use provided public key
        public_key = settings.AUTH_JWT_PUBLIC_KEY
    else:
        logger.error("JWT mode enabled but no public key or JWKS URL configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "CONFIG_ERROR", "message": "JWT validation not configured"}},
        )

    # Decode and validate
    try:
        # Build decode options
        decode_options = {"verify_signature": True}

        # Add issuer validation if configured
        issuer = settings.AUTH_JWT_ISSUER if settings.AUTH_JWT_ISSUER else None

        # Add audience validation if configured
        audience = settings.AUTH_JWT_AUDIENCE if settings.AUTH_JWT_AUDIENCE else None

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256", "ES256", "HS256"],
            issuer=issuer,
            audience=audience,
            options=decode_options,
        )

        # Extract scopes from configured claim
        scope_claim = settings.AUTH_JWT_SCOPE_CLAIM
        raw_scopes = payload.get(scope_claim, "")

        # Scopes can be space-separated string or list
        if isinstance(raw_scopes, str):
            scope_strings = raw_scopes.split()
        elif isinstance(raw_scopes, list):
            scope_strings = raw_scopes
        else:
            scope_strings = []

        # Convert to Scope enum values
        scopes = set()
        for s in scope_strings:
            try:
                scopes.add(Scope(s))
            except ValueError:
                # Ignore unknown scopes
                pass

        if not scopes:
            logger.warning(f"JWT has no valid scopes: {scope_strings}")
            return None

        return AuthContext(
            authenticated=True,
            scopes=scopes,
            token_type="jwt",
            subject=payload.get("sub"),
        )

    except jwt.ExpiredSignatureError:
        logger.warning("JWT has expired")
        return None
    except jwt.InvalidIssuerError:
        logger.warning("JWT has invalid issuer")
        return None
    except jwt.InvalidAudienceError:
        logger.warning("JWT has invalid audience")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        return None


def get_auth_context(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency to extract and validate auth context.

    Args:
        authorization: Authorization header value

    Returns:
        AuthContext for the request
    """
    # Mode: none - allow everything
    if settings.AUTH_MODE == "none":
        return AuthContext(
            authenticated=True,
            scopes={Scope.ADMIN},  # Grant all scopes in dev mode
            token_type=None,
        )

    # Extract token from header
    token = _extract_bearer_token(authorization)

    if not token:
        return AuthContext(authenticated=False, scopes=set())

    # Mode: psk - validate against configured tokens
    if settings.AUTH_MODE == "psk":
        context = _validate_psk_token(token)
        if context:
            return context
        return AuthContext(authenticated=False, scopes=set())

    # Mode: jwt - validate JWT signature and claims
    if settings.AUTH_MODE == "jwt":
        context = _validate_jwt_token(token)
        if context:
            return context
        return AuthContext(authenticated=False, scopes=set())

    # Unknown mode (should be caught by validator, but defensive)
    logger.error(f"Unknown auth mode: {settings.AUTH_MODE}")
    return AuthContext(authenticated=False, scopes=set())


def require_scope(scope: Scope):
    """Create a dependency that requires a specific scope.

    Args:
        scope: The required scope

    Returns:
        FastAPI dependency function
    """

    def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        # In mode none, everything is allowed
        if settings.AUTH_MODE == "none":
            return auth

        # Check authentication
        if not auth.authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check scope
        if not auth.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"Insufficient permissions. Required scope: {scope.value}",
                    }
                },
            )

        return auth

    return dependency


async def get_websocket_auth_context(websocket: WebSocket) -> AuthContext:
    """Extract and validate auth context from WebSocket connection.

    WebSocket auth uses the Sec-WebSocket-Protocol header:
        Sec-WebSocket-Protocol: bearer,<token>

    The server should echo back "bearer" in the response protocol.

    Args:
        websocket: The WebSocket connection

    Returns:
        AuthContext for the connection
    """
    # Mode: none - allow everything
    if settings.AUTH_MODE == "none":
        return AuthContext(
            authenticated=True,
            scopes={Scope.ADMIN},
            token_type=None,
        )

    # Extract token from Sec-WebSocket-Protocol header
    # Format: bearer,<token>
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    token = None

    if protocols:
        parts = [p.strip() for p in protocols.split(",")]
        if len(parts) >= 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token:
        return AuthContext(authenticated=False, scopes=set())

    # Validate based on mode
    if settings.AUTH_MODE == "psk":
        context = _validate_psk_token(token)
        if context:
            return context
        return AuthContext(authenticated=False, scopes=set())

    if settings.AUTH_MODE == "jwt":
        context = _validate_jwt_token(token)
        if context:
            return context
        return AuthContext(authenticated=False, scopes=set())

    return AuthContext(authenticated=False, scopes=set())


# Convenience dependencies for common scope requirements
require_submit = require_scope(Scope.SUBMIT)
require_read = require_scope(Scope.READ)
require_admin = require_scope(Scope.ADMIN)
