"""Tests for authentication and authorization module.

This module tests the 3-mode auth system:
- none: No auth (development mode)
- psk: Pre-shared key tokens
- jwt: JWT validation

Scope hierarchy tests:
- lens:admin includes all scopes
- lens:submit only allows signal submission
- lens:read only allows data reading
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from src.core.auth import (
    Scope,
    AuthContext,
    SCOPE_HIERARCHY,
    _extract_bearer_token,
    _validate_psk_token,
    get_auth_context,
    require_scope,
)


@pytest.mark.unit
class TestScope:
    """Tests for Scope enum."""

    def test_scope_values(self):
        """Test scope enum values match expected strings."""
        assert Scope.SUBMIT.value == "lens:submit"
        assert Scope.READ.value == "lens:read"
        assert Scope.ADMIN.value == "lens:admin"

    def test_scope_hierarchy_admin_includes_all(self):
        """Test that admin scope includes all other scopes."""
        admin_scopes = SCOPE_HIERARCHY[Scope.ADMIN]
        assert Scope.SUBMIT in admin_scopes
        assert Scope.READ in admin_scopes
        assert Scope.ADMIN in admin_scopes

    def test_scope_hierarchy_submit_only(self):
        """Test that submit scope only includes itself."""
        submit_scopes = SCOPE_HIERARCHY[Scope.SUBMIT]
        assert Scope.SUBMIT in submit_scopes
        assert Scope.READ not in submit_scopes
        assert Scope.ADMIN not in submit_scopes

    def test_scope_hierarchy_read_only(self):
        """Test that read scope only includes itself."""
        read_scopes = SCOPE_HIERARCHY[Scope.READ]
        assert Scope.READ in read_scopes
        assert Scope.SUBMIT not in read_scopes
        assert Scope.ADMIN not in read_scopes


@pytest.mark.unit
class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_create_authenticated_context(self):
        """Test creating an authenticated context."""
        ctx = AuthContext(
            authenticated=True,
            scopes={Scope.SUBMIT},
            token_type="psk",
            subject="test-user",
        )

        assert ctx.authenticated is True
        assert Scope.SUBMIT in ctx.scopes
        assert ctx.token_type == "psk"
        assert ctx.subject == "test-user"

    def test_create_unauthenticated_context(self):
        """Test creating an unauthenticated context."""
        ctx = AuthContext(authenticated=False, scopes=set())

        assert ctx.authenticated is False
        assert len(ctx.scopes) == 0

    def test_has_scope_direct(self):
        """Test has_scope for directly granted scope."""
        ctx = AuthContext(authenticated=True, scopes={Scope.SUBMIT})

        assert ctx.has_scope(Scope.SUBMIT) is True
        assert ctx.has_scope(Scope.READ) is False
        assert ctx.has_scope(Scope.ADMIN) is False

    def test_has_scope_via_admin(self):
        """Test that admin scope grants all permissions."""
        ctx = AuthContext(authenticated=True, scopes={Scope.ADMIN})

        assert ctx.has_scope(Scope.SUBMIT) is True
        assert ctx.has_scope(Scope.READ) is True
        assert ctx.has_scope(Scope.ADMIN) is True


@pytest.mark.unit
class TestExtractBearerToken:
    """Tests for bearer token extraction."""

    def test_extract_valid_bearer_token(self):
        """Test extracting a valid bearer token."""
        token = _extract_bearer_token("Bearer abc123")
        assert token == "abc123"

    def test_extract_bearer_case_insensitive(self):
        """Test that Bearer is case insensitive."""
        token = _extract_bearer_token("bearer abc123")
        assert token == "abc123"

        token = _extract_bearer_token("BEARER abc123")
        assert token == "abc123"

    def test_extract_none_when_missing(self):
        """Test that None is returned when header is missing."""
        token = _extract_bearer_token(None)
        assert token is None

    def test_extract_none_for_invalid_format(self):
        """Test that None is returned for invalid format."""
        # No space
        token = _extract_bearer_token("Bearerabc123")
        assert token is None

        # Wrong scheme
        token = _extract_bearer_token("Basic abc123")
        assert token is None

        # No token
        token = _extract_bearer_token("Bearer")
        assert token is None


@pytest.mark.unit
class TestPSKValidation:
    """Tests for PSK token validation."""

    def test_validate_admin_token(self):
        """Test validation of admin token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"

            ctx = _validate_psk_token("admin-secret")

            assert ctx is not None
            assert ctx.authenticated is True
            assert Scope.ADMIN in ctx.scopes
            assert ctx.token_type == "psk"
            assert ctx.subject == "admin"

    def test_validate_submit_token(self):
        """Test validation of submit token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"

            ctx = _validate_psk_token("submit-secret")

            assert ctx is not None
            assert ctx.authenticated is True
            assert Scope.SUBMIT in ctx.scopes
            assert ctx.token_type == "psk"
            assert ctx.subject == "submit"

    def test_validate_read_token(self):
        """Test validation of read token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"

            ctx = _validate_psk_token("read-secret")

            assert ctx is not None
            assert ctx.authenticated is True
            assert Scope.READ in ctx.scopes
            assert ctx.token_type == "psk"
            assert ctx.subject == "read"

    def test_validate_invalid_token(self):
        """Test that invalid token returns None."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"

            ctx = _validate_psk_token("wrong-token")
            assert ctx is None

    def test_validate_when_tokens_not_configured(self):
        """Test validation when tokens are not configured."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_TOKEN_ADMIN = None
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = None

            ctx = _validate_psk_token("any-token")
            assert ctx is None


@pytest.mark.unit
class TestGetAuthContext:
    """Tests for get_auth_context dependency."""

    def test_mode_none_grants_all(self):
        """Test that mode=none grants all scopes."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            ctx = get_auth_context(authorization=None)

            assert ctx.authenticated is True
            assert Scope.ADMIN in ctx.scopes

    def test_mode_psk_with_valid_token(self):
        """Test PSK mode with valid token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-token"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = None

            ctx = get_auth_context(authorization="Bearer admin-token")

            assert ctx.authenticated is True
            assert Scope.ADMIN in ctx.scopes

    def test_mode_psk_without_token(self):
        """Test PSK mode without token returns unauthenticated."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"

            ctx = get_auth_context(authorization=None)

            assert ctx.authenticated is False
            assert len(ctx.scopes) == 0

    def test_mode_psk_with_invalid_token(self):
        """Test PSK mode with invalid token returns unauthenticated."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-token"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = None

            ctx = get_auth_context(authorization="Bearer wrong-token")

            assert ctx.authenticated is False
            assert len(ctx.scopes) == 0


@pytest.mark.unit
class TestRequireScope:
    """Tests for require_scope dependency factory."""

    def test_mode_none_allows_all(self):
        """Test that mode=none allows all scopes."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            dependency = require_scope(Scope.ADMIN)
            # Create auth context for mode=none
            auth_ctx = AuthContext(authenticated=True, scopes={Scope.ADMIN})

            result = dependency(auth_ctx)
            assert result.authenticated is True

    def test_requires_authentication(self):
        """Test that unauthenticated requests are rejected."""
        from fastapi import HTTPException

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"

            dependency = require_scope(Scope.SUBMIT)
            auth_ctx = AuthContext(authenticated=False, scopes=set())

            with pytest.raises(HTTPException) as exc_info:
                dependency(auth_ctx)

            assert exc_info.value.status_code == 401

    def test_requires_correct_scope(self):
        """Test that incorrect scope is rejected."""
        from fastapi import HTTPException

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"

            dependency = require_scope(Scope.ADMIN)
            # Only has submit scope, not admin
            auth_ctx = AuthContext(authenticated=True, scopes={Scope.SUBMIT})

            with pytest.raises(HTTPException) as exc_info:
                dependency(auth_ctx)

            assert exc_info.value.status_code == 403

    def test_admin_scope_grants_all(self):
        """Test that admin scope satisfies any scope requirement."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"

            # Admin should satisfy submit requirement
            dependency = require_scope(Scope.SUBMIT)
            auth_ctx = AuthContext(authenticated=True, scopes={Scope.ADMIN})

            result = dependency(auth_ctx)
            assert result.authenticated is True

            # Admin should satisfy read requirement
            dependency = require_scope(Scope.READ)
            result = dependency(auth_ctx)
            assert result.authenticated is True


@pytest.mark.unit
class TestScopeMapping:
    """Tests for endpoint scope mapping (documented, not enforced here)."""

    def test_scope_assignments(self):
        """Document expected scope assignments for endpoints."""
        # This test documents the expected scope assignments
        # Actual enforcement is tested in integration tests
        scope_map = {
            "POST /signals": Scope.SUBMIT,
            "GET /events": Scope.READ,
            "GET /events/{id}": Scope.READ,
            "GET /events/{id}/status": Scope.READ,
            "GET /decisions": Scope.READ,
            "GET /decisions/{id}": Scope.READ,
            "GET /dlq": Scope.READ,
            "GET /dlq/{id}": Scope.READ,
            "POST /dlq/{id}/retry": Scope.ADMIN,
            "POST /dlq/{id}/resolve": Scope.ADMIN,
            "GET /llm-configs": Scope.ADMIN,
            "GET /llm-configs/{model}": Scope.ADMIN,
            "PUT /llm-configs/{model}": Scope.ADMIN,
            "PATCH /llm-configs/{model}": Scope.ADMIN,
            "DELETE /llm-configs/{model}": Scope.ADMIN,
            "POST /llm-configs/{model}/test": Scope.ADMIN,
            "WS /ws/stream": Scope.READ,
        }

        # Verify all expected scopes are valid
        for endpoint, scope in scope_map.items():
            assert isinstance(scope, Scope), f"Invalid scope for {endpoint}"
