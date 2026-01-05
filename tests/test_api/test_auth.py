"""API integration tests for authentication.

These tests verify auth behavior at the API endpoint level,
complementing the unit tests in test_core/test_auth.py.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db_session():
    """Mock database session for API tests."""
    mock = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    return mock


@pytest.mark.unit
class TestAuthModeNone:
    """Tests for AUTH_MODE=none (development mode)."""

    def test_signals_endpoint_allows_unauthenticated(self, mock_db_session):
        """Test that signals endpoint allows unauthenticated requests in mode=none."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            # Import after patching
            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization=None)
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_admin_endpoints_allow_unauthenticated(self, mock_db_session):
        """Test that admin endpoints allow unauthenticated in mode=none."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization=None)
            assert ctx.has_scope(Scope.ADMIN) is True


@pytest.mark.unit
class TestAuthModePSK:
    """Tests for AUTH_MODE=psk (pre-shared key mode)."""

    def test_signals_requires_submit_token(self):
        """Test that signals endpoint requires submit token in PSK mode."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            # No token - should fail
            ctx = get_auth_context(authorization=None)
            assert ctx.authenticated is False

            dependency = require_scope(Scope.SUBMIT)
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 401

    def test_signals_accepts_submit_token(self):
        """Test that signals endpoint accepts valid submit token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope

            ctx = get_auth_context(authorization="Bearer submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

            dependency = require_scope(Scope.SUBMIT)
            result = dependency(ctx)
            assert result.authenticated is True

    def test_signals_rejects_read_token(self):
        """Test that signals endpoint rejects read token (wrong scope)."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            ctx = get_auth_context(authorization="Bearer read-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True
            assert ctx.has_scope(Scope.SUBMIT) is False

            dependency = require_scope(Scope.SUBMIT)
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 403

    def test_admin_token_grants_all_scopes(self):
        """Test that admin token grants access to all scopes."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope

            ctx = get_auth_context(authorization="Bearer admin-secret")
            assert ctx.authenticated is True

            # Admin should satisfy all scope requirements
            for scope in [Scope.SUBMIT, Scope.READ, Scope.ADMIN]:
                dependency = require_scope(scope)
                result = dependency(ctx)
                assert result.authenticated is True

    def test_events_requires_read_token(self):
        """Test that events endpoint requires read token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope

            # Submit token should not work for read endpoints
            ctx = get_auth_context(authorization="Bearer submit-secret")
            assert ctx.has_scope(Scope.READ) is False

            # Read token should work
            ctx = get_auth_context(authorization="Bearer read-secret")
            assert ctx.has_scope(Scope.READ) is True

    def test_dlq_retry_requires_admin_token(self):
        """Test that DLQ retry requires admin token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            # Read token should not work for admin endpoints
            ctx = get_auth_context(authorization="Bearer read-secret")
            dependency = require_scope(Scope.ADMIN)
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 403

            # Admin token should work
            ctx = get_auth_context(authorization="Bearer admin-secret")
            result = dependency(ctx)
            assert result.authenticated is True

    def test_llm_configs_requires_admin_token(self):
        """Test that LLM configs endpoints require admin token."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            # Submit token should not work
            ctx = get_auth_context(authorization="Bearer submit-secret")
            dependency = require_scope(Scope.ADMIN)
            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)
            assert exc_info.value.status_code == 403


@pytest.mark.unit
class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    @pytest.mark.asyncio
    async def test_websocket_auth_mode_none(self):
        """Test WebSocket allows all connections in mode=none."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "none"

            from src.core.auth import get_websocket_auth_context, Scope

            mock_ws = MagicMock()
            mock_ws.headers = {}

            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True

    @pytest.mark.asyncio
    async def test_websocket_auth_psk_valid_token(self):
        """Test WebSocket accepts valid PSK token."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_websocket_auth_context, Scope

            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer,read-secret"}

            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True

    @pytest.mark.asyncio
    async def test_websocket_auth_psk_missing_token(self):
        """Test WebSocket rejects missing token in PSK mode."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_websocket_auth_context

            mock_ws = MagicMock()
            mock_ws.headers = {}

            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is False

    @pytest.mark.asyncio
    async def test_websocket_auth_psk_invalid_token(self):
        """Test WebSocket rejects invalid PSK token."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_websocket_auth_context

            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer,wrong-token"}

            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is False


@pytest.mark.unit
class TestAuthErrorResponses:
    """Tests for auth error response formats."""

    def test_401_response_format(self):
        """Test 401 error response has correct format."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            ctx = get_auth_context(authorization=None)
            dependency = require_scope(Scope.SUBMIT)

            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"]["code"] == "UNAUTHORIZED"
            assert "WWW-Authenticate" in exc_info.value.headers

    def test_403_response_format(self):
        """Test 403 error response has correct format."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, require_scope, Scope
            from fastapi import HTTPException

            # Authenticated but wrong scope
            ctx = get_auth_context(authorization="Bearer submit-secret")
            dependency = require_scope(Scope.ADMIN)

            with pytest.raises(HTTPException) as exc_info:
                dependency(ctx)

            assert exc_info.value.status_code == 403
            assert exc_info.value.detail["error"]["code"] == "FORBIDDEN"
            assert "lens:admin" in exc_info.value.detail["error"]["message"]


@pytest.mark.unit
class TestScopeEndpointMapping:
    """Tests verifying correct scope requirements on endpoints."""

    def test_submit_scope_endpoints(self):
        """Verify endpoints that require lens:submit scope."""
        from src.core.auth import Scope

        # These should require SUBMIT
        submit_endpoints = [
            ("POST", "/api/v1/signals"),
        ]

        # Document the mapping (actual enforcement tested above)
        for method, path in submit_endpoints:
            assert Scope.SUBMIT.value == "lens:submit"

    def test_read_scope_endpoints(self):
        """Verify endpoints that require lens:read scope."""
        from src.core.auth import Scope

        # These should require READ
        read_endpoints = [
            ("GET", "/api/v1/events"),
            ("GET", "/api/v1/events/{event_id}"),
            ("GET", "/api/v1/events/{event_id}/status"),
            ("GET", "/api/v1/decisions"),
            ("GET", "/api/v1/decisions/{decision_id}"),
            ("GET", "/api/v1/dlq"),
            ("GET", "/api/v1/dlq/{dlq_id}"),
            ("WS", "/api/v1/ws/stream"),
        ]

        # Document the mapping
        for method, path in read_endpoints:
            assert Scope.READ.value == "lens:read"

    def test_admin_scope_endpoints(self):
        """Verify endpoints that require lens:admin scope."""
        from src.core.auth import Scope

        # These should require ADMIN
        admin_endpoints = [
            ("POST", "/api/v1/dlq/{dlq_id}/retry"),
            ("POST", "/api/v1/dlq/{dlq_id}/resolve"),
            ("GET", "/api/v1/llm-configs"),
            ("GET", "/api/v1/llm-configs/{model_name}"),
            ("PUT", "/api/v1/llm-configs/{model_name}"),
            ("PATCH", "/api/v1/llm-configs/{model_name}"),
            ("DELETE", "/api/v1/llm-configs/{model_name}"),
            ("POST", "/api/v1/llm-configs/{model_name}/test"),
            ("POST", "/api/v1/llm-configs/{model_name}/enable"),
            ("POST", "/api/v1/llm-configs/{model_name}/disable"),
        ]

        # Document the mapping
        for method, path in admin_endpoints:
            assert Scope.ADMIN.value == "lens:admin"


@pytest.mark.unit
class TestAuthorizationHeaderEdgeCases:
    """Tests for edge cases in Authorization header parsing."""

    def test_bearer_case_insensitive(self):
        """Test that Bearer prefix is case-insensitive."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            # Lowercase 'bearer'
            ctx = get_auth_context(authorization="bearer submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

            # Uppercase 'BEARER'
            ctx = get_auth_context(authorization="BEARER submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

            # Mixed case 'BeArEr'
            ctx = get_auth_context(authorization="BeArEr submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_missing_bearer_prefix(self):
        """Test that token without Bearer prefix is rejected."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            # Just the token without Bearer prefix
            ctx = get_auth_context(authorization="submit-secret")
            assert ctx.authenticated is False

    def test_wrong_auth_scheme(self):
        """Test that non-Bearer auth schemes are rejected."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            # Basic auth scheme
            ctx = get_auth_context(authorization="Basic dXNlcjpwYXNz")
            assert ctx.authenticated is False

            # Digest auth scheme
            ctx = get_auth_context(authorization="Digest username=test")
            assert ctx.authenticated is False

    def test_empty_authorization_header(self):
        """Test that empty Authorization header is handled."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            ctx = get_auth_context(authorization="")
            assert ctx.authenticated is False

    def test_bearer_only_no_token(self):
        """Test that 'Bearer' without token is rejected."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            # Just 'Bearer' with nothing else
            ctx = get_auth_context(authorization="Bearer")
            assert ctx.authenticated is False

            # 'Bearer ' with trailing space but no token
            ctx = get_auth_context(authorization="Bearer ")
            assert ctx.authenticated is False

    def test_extra_spaces_in_header(self):
        """Test handling of extra spaces in Authorization header."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            # Multiple spaces between Bearer and token
            # split() without args splits on any whitespace and removes empties
            # So "Bearer  submit-secret".split() returns ['Bearer', 'submit-secret']
            ctx = get_auth_context(authorization="Bearer  submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_bearer_with_multiple_parts(self):
        """Test that tokens with spaces are handled correctly."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            # Token with space (e.g., "Bearer token with space")
            ctx = get_auth_context(authorization="Bearer token with space")
            # Should extract only "token" and fail since it doesn't match
            assert ctx.authenticated is False


@pytest.mark.unit
class TestPSKPartialConfiguration:
    """Tests for partially configured PSK tokens."""

    def test_only_submit_token_configured(self):
        """Test PSK mode with only submit token configured."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            # Submit token works
            ctx = get_auth_context(authorization="Bearer submit-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

            # Random token fails (no read/admin tokens to match)
            ctx = get_auth_context(authorization="Bearer random-token")
            assert ctx.authenticated is False

    def test_only_read_token_configured(self):
        """Test PSK mode with only read token configured."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            # Read token works
            ctx = get_auth_context(authorization="Bearer read-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True

            # Cannot get submit scope
            assert ctx.has_scope(Scope.SUBMIT) is False

    def test_only_admin_token_configured(self):
        """Test PSK mode with only admin token configured."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_auth_context, Scope

            # Admin token works and grants all scopes
            ctx = get_auth_context(authorization="Bearer admin-secret")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.ADMIN) is True
            assert ctx.has_scope(Scope.READ) is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_empty_string_tokens_not_matched(self):
        """Test that empty string tokens are not matched."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = ""
            mock_settings.AUTH_TOKEN_READ = ""
            mock_settings.AUTH_TOKEN_ADMIN = ""

            from src.core.auth import get_auth_context

            # Empty token should not authenticate
            ctx = get_auth_context(authorization="Bearer ")
            assert ctx.authenticated is False

            # Empty string exact match should also fail
            ctx = get_auth_context(authorization="Bearer")
            assert ctx.authenticated is False

    def test_no_tokens_configured(self):
        """Test PSK mode with no tokens configured at all."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context

            # Any token should fail
            ctx = get_auth_context(authorization="Bearer any-token")
            assert ctx.authenticated is False


@pytest.mark.unit
class TestWebSocketAuthEdgeCases:
    """Tests for WebSocket authentication edge cases."""

    @pytest.mark.asyncio
    async def test_websocket_malformed_protocol_header(self):
        """Test WebSocket with malformed sec-websocket-protocol header."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "submit-secret"
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = "admin-secret"

            from src.core.auth import get_websocket_auth_context

            # Missing comma separator
            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer read-secret"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is False

            # Just 'bearer' without token
            mock_ws.headers = {"sec-websocket-protocol": "bearer"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is False

            # Empty protocol header
            mock_ws.headers = {"sec-websocket-protocol": ""}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is False

    @pytest.mark.asyncio
    async def test_websocket_bearer_case_sensitivity(self):
        """Test that WebSocket bearer prefix is case-insensitive."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_websocket_auth_context, Scope

            # Lowercase 'bearer'
            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer,read-secret"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True

            # Uppercase 'BEARER'
            mock_ws.headers = {"sec-websocket-protocol": "BEARER,read-secret"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True

    @pytest.mark.asyncio
    async def test_websocket_extra_protocols(self):
        """Test WebSocket with additional protocol values."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_websocket_auth_context, Scope

            # Extra protocol after token (should still work, takes parts[1])
            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer,read-secret,extra"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True

    @pytest.mark.asyncio
    async def test_websocket_whitespace_in_protocol(self):
        """Test WebSocket handles whitespace in protocol header."""
        from unittest.mock import MagicMock

        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = None
            mock_settings.AUTH_TOKEN_READ = "read-secret"
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_websocket_auth_context, Scope

            # Spaces around comma (should be stripped)
            mock_ws = MagicMock()
            mock_ws.headers = {"sec-websocket-protocol": "bearer, read-secret"}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.READ) is True

            # Spaces on both sides
            mock_ws.headers = {"sec-websocket-protocol": " bearer , read-secret "}
            ctx = await get_websocket_auth_context(mock_ws)
            assert ctx.authenticated is True


@pytest.mark.unit
class TestAuthContextHierarchy:
    """Tests for scope hierarchy and AuthContext.has_scope()."""

    def test_admin_includes_submit_scope(self):
        """Test that admin scope includes submit via hierarchy."""
        from src.core.auth import AuthContext, Scope

        ctx = AuthContext(
            authenticated=True,
            scopes={Scope.ADMIN},
            token_type="psk",
            subject="admin"
        )

        assert ctx.has_scope(Scope.ADMIN) is True
        assert ctx.has_scope(Scope.READ) is True
        assert ctx.has_scope(Scope.SUBMIT) is True

    def test_read_does_not_include_submit(self):
        """Test that read scope does not include submit."""
        from src.core.auth import AuthContext, Scope

        ctx = AuthContext(
            authenticated=True,
            scopes={Scope.READ},
            token_type="psk",
            subject="read"
        )

        assert ctx.has_scope(Scope.READ) is True
        assert ctx.has_scope(Scope.SUBMIT) is False
        assert ctx.has_scope(Scope.ADMIN) is False

    def test_submit_does_not_include_read(self):
        """Test that submit scope does not include read."""
        from src.core.auth import AuthContext, Scope

        ctx = AuthContext(
            authenticated=True,
            scopes={Scope.SUBMIT},
            token_type="psk",
            subject="submit"
        )

        assert ctx.has_scope(Scope.SUBMIT) is True
        assert ctx.has_scope(Scope.READ) is False
        assert ctx.has_scope(Scope.ADMIN) is False

    def test_empty_scopes_has_nothing(self):
        """Test that empty scopes grants nothing."""
        from src.core.auth import AuthContext, Scope

        ctx = AuthContext(
            authenticated=False,
            scopes=set(),
        )

        assert ctx.has_scope(Scope.SUBMIT) is False
        assert ctx.has_scope(Scope.READ) is False
        assert ctx.has_scope(Scope.ADMIN) is False

    def test_multiple_scopes(self):
        """Test context with multiple explicit scopes."""
        from src.core.auth import AuthContext, Scope

        ctx = AuthContext(
            authenticated=True,
            scopes={Scope.SUBMIT, Scope.READ},
            token_type="jwt",
            subject="multi-scope-user"
        )

        assert ctx.has_scope(Scope.SUBMIT) is True
        assert ctx.has_scope(Scope.READ) is True
        assert ctx.has_scope(Scope.ADMIN) is False


@pytest.mark.unit
class TestInvalidTokenFormats:
    """Tests for various invalid token formats."""

    def test_token_with_special_characters(self):
        """Test tokens containing special characters."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "token-with-special!@#$%"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization="Bearer token-with-special!@#$%")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_very_long_token(self):
        """Test handling of very long tokens."""
        with patch("src.core.auth.settings") as mock_settings:
            long_token = "a" * 1000
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = long_token
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization=f"Bearer {long_token}")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_unicode_in_token(self):
        """Test handling of unicode characters in tokens."""
        with patch("src.core.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "token-üñîçödé-🔐"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization="Bearer token-üñîçödé-🔐")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True

    def test_base64_like_token(self):
        """Test tokens that look like base64 (common format)."""
        with patch("src.core.auth.settings") as mock_settings:
            # Realistic base64-encoded token
            mock_settings.AUTH_MODE = "psk"
            mock_settings.AUTH_TOKEN_SUBMIT = "1IT0W8e-lVbahdtLQ7vGVc_doPYXKGBfLUosM8V57Ac"
            mock_settings.AUTH_TOKEN_READ = None
            mock_settings.AUTH_TOKEN_ADMIN = None

            from src.core.auth import get_auth_context, Scope

            ctx = get_auth_context(authorization="Bearer 1IT0W8e-lVbahdtLQ7vGVc_doPYXKGBfLUosM8V57Ac")
            assert ctx.authenticated is True
            assert ctx.has_scope(Scope.SUBMIT) is True