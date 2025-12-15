"""Custom exceptions for SigmaPilot Lens."""

from typing import Any, Dict, List, Optional


class LensException(Exception):
    """Base exception for all Lens errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[List[Dict[str, Any]]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or []
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API response."""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(LensException):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class AuthenticationError(LensException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(message, code="UNAUTHORIZED")


class AuthorizationError(LensException):
    """Raised when user lacks permission."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, code="FORBIDDEN")


class NotFoundError(LensException):
    """Raised when a resource is not found."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="NOT_FOUND",
        )


class RateLimitError(LensException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int):
        super().__init__(
            message="Rate limit exceeded",
            code="RATE_LIMITED",
            details=[{"retry_after": retry_after}],
        )
        self.retry_after = retry_after


class QueueError(LensException):
    """Raised when queue operations fail."""

    def __init__(self, message: str, operation: str):
        super().__init__(
            message=message,
            code="QUEUE_ERROR",
            details=[{"operation": operation}],
        )


class ProviderError(LensException):
    """Raised when a data provider fails."""

    def __init__(self, provider: str, message: str):
        super().__init__(
            message=f"Provider error ({provider}): {message}",
            code="PROVIDER_ERROR",
            details=[{"provider": provider}],
        )


class ModelError(LensException):
    """Raised when AI model evaluation fails."""

    def __init__(self, model: str, message: str, error_code: str = "MODEL_ERROR"):
        super().__init__(
            message=f"Model error ({model}): {message}",
            code=error_code,
            details=[{"model": model}],
        )


class SchemaError(LensException):
    """Raised when model output doesn't match expected schema."""

    def __init__(self, model: str, message: str):
        super().__init__(
            message=f"Schema validation failed ({model}): {message}",
            code="SCHEMA_ERROR",
            details=[{"model": model}],
        )


class TimeoutError(LensException):
    """Raised when an operation times out."""

    def __init__(self, operation: str, timeout_ms: int):
        super().__init__(
            message=f"Operation timed out: {operation}",
            code="TIMEOUT",
            details=[{"operation": operation, "timeout_ms": timeout_ms}],
        )
