"""Abstract base class for AI model adapters.

This module defines the contract that all AI model implementations must follow.
Each model adapter (OpenAI, Google, Anthropic, DeepSeek) implements this interface
to provide consistent behavior across different AI providers.

Design Principles:
    - Uniform interface for all AI providers
    - Isolated failures (one model's error doesn't affect others)
    - Configurable timeouts and token limits
    - Structured output validation
    - Comprehensive error handling with specific error types

Usage:
    class OpenAIAdapter(BaseModelAdapter):
        async def evaluate(self, prompt: str) -> ModelResponse:
            # Implementation
            ...

Contract:
    - evaluate() must return ModelResponse within timeout_ms
    - evaluate() must not raise exceptions; errors go in ModelResponse.error
    - All implementations must handle rate limits gracefully
    - Token usage must be tracked and returned in response
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import json


class ModelStatus(str, Enum):
    """Status codes for model evaluation results.

    Attributes:
        SUCCESS: Model returned valid response
        TIMEOUT: Request exceeded timeout_ms
        RATE_LIMITED: Provider rate limit hit
        API_ERROR: Provider API returned error
        SCHEMA_ERROR: Response failed JSON/schema validation
        NETWORK_ERROR: Network connectivity issue
        INVALID_CONFIG: Model not properly configured
    """
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    API_ERROR = "API_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_CONFIG = "INVALID_CONFIG"


@dataclass
class ModelResponse:
    """Response from an AI model evaluation.

    This dataclass encapsulates all information about a model's response,
    whether successful or failed. Errors are captured in the response
    rather than raised as exceptions to support parallel evaluation.

    Attributes:
        model_name: Name of the model (e.g., 'chatgpt', 'gemini')
        model_version: Specific model version used (e.g., 'gpt-4o')
        status: Evaluation result status
        latency_ms: Time taken for evaluation in milliseconds
        raw_response: Raw text response from model (for debugging)
        parsed_response: Parsed JSON response (if successful)
        tokens_in: Input token count
        tokens_out: Output token count
        error_code: Error identifier (if status != SUCCESS)
        error_message: Human-readable error description
        timestamp: When the evaluation completed

    Invariants:
        - If status == SUCCESS, parsed_response must not be None
        - If status != SUCCESS, error_code and error_message should be set
        - latency_ms >= 0
        - tokens_in and tokens_out >= 0 when set
    """
    model_name: str
    model_version: str
    status: ModelStatus
    latency_ms: int
    raw_response: Optional[str] = None
    parsed_response: Optional[Dict[str, Any]] = None
    tokens_in: int = 0
    tokens_out: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        """Check if evaluation was successful."""
        return self.status == ModelStatus.SUCCESS

    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return self.tokens_in + self.tokens_out

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "raw_response": self.raw_response,
            "parsed_response": self.parsed_response,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ModelConfig:
    """Configuration for an AI model adapter.

    Attributes:
        model_name: Identifier for this model (e.g., 'chatgpt')
        provider: AI provider name (e.g., 'openai', 'google', 'anthropic')
        api_key: API key for authentication
        model_id: Specific model identifier (e.g., 'gpt-4o', 'gemini-1.5-pro')
        timeout_ms: Maximum time to wait for response (default 30000)
        max_tokens: Maximum output tokens (default 1000)
        temperature: Sampling temperature (default 0.1 for consistency)
        extra_params: Provider-specific additional parameters

    Invariants:
        - api_key must not be empty for real evaluations
        - timeout_ms > 0
        - max_tokens > 0
        - 0 <= temperature <= 2
    """
    model_name: str
    provider: str
    api_key: str
    model_id: str
    timeout_ms: int = 30000
    max_tokens: int = 1000
    temperature: float = 0.1
    extra_params: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        """Check if model has required configuration."""
        return bool(self.api_key and self.model_id)

    @property
    def timeout_seconds(self) -> float:
        """Get timeout in seconds."""
        return self.timeout_ms / 1000.0


class BaseModelAdapter(ABC):
    """Abstract base class for AI model adapters.

    This class defines the interface that all AI model implementations must follow.
    Subclasses implement provider-specific logic while maintaining a consistent
    interface for the evaluation worker.

    Design Contract:
        1. __init__ receives ModelConfig with all necessary parameters
        2. evaluate() is the main entry point, returns ModelResponse
        3. Errors are caught and returned in ModelResponse, not raised
        4. Each adapter is responsible for its own retry logic
        5. Adapters should cache clients where possible for efficiency

    Thread Safety:
        Adapters should be safe to use from multiple async tasks.

    Example:
        adapter = OpenAIAdapter(config)
        response = await adapter.evaluate(prompt)
        if response.is_success:
            decision = response.parsed_response
        else:
            log_error(response.error_message)
    """

    def __init__(self, config: ModelConfig):
        """Initialize the adapter with configuration.

        Args:
            config: Model configuration including API key and parameters

        Raises:
            ValueError: If config is missing required fields
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration.

        Override in subclasses for provider-specific validation.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.config.model_name:
            raise ValueError("model_name is required")
        if not self.config.provider:
            raise ValueError("provider is required")

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self.config.model_name

    @property
    def model_version(self) -> str:
        """Get the model version/ID."""
        return self.config.model_id

    @property
    def is_configured(self) -> bool:
        """Check if model is properly configured for real evaluations."""
        return self.config.is_configured

    @abstractmethod
    async def evaluate(self, prompt: str) -> ModelResponse:
        """Evaluate a prompt and return the model's response.

        This is the main entry point for model evaluation. Implementations
        should:
        1. Send the prompt to the AI provider
        2. Parse the JSON response
        3. Return ModelResponse with results or error info

        Args:
            prompt: The fully rendered prompt to send to the model

        Returns:
            ModelResponse containing either parsed results or error info

        Note:
            This method should NOT raise exceptions. All errors should be
            captured in the returned ModelResponse with appropriate status.
        """
        pass

    def _create_error_response(
        self,
        status: ModelStatus,
        error_code: str,
        error_message: str,
        latency_ms: int,
        raw_response: Optional[str] = None,
    ) -> ModelResponse:
        """Helper to create error responses.

        Args:
            status: Error status code
            error_code: Short error identifier
            error_message: Human-readable error description
            latency_ms: Time taken before error
            raw_response: Raw response text (if any)

        Returns:
            ModelResponse with error information
        """
        return ModelResponse(
            model_name=self.model_name,
            model_version=self.model_version,
            status=status,
            latency_ms=latency_ms,
            raw_response=raw_response,
            error_code=error_code,
            error_message=error_message,
        )

    def _create_success_response(
        self,
        parsed_response: Dict[str, Any],
        latency_ms: int,
        tokens_in: int,
        tokens_out: int,
        raw_response: Optional[str] = None,
    ) -> ModelResponse:
        """Helper to create success responses.

        Args:
            parsed_response: Parsed JSON response
            latency_ms: Time taken for evaluation
            tokens_in: Input token count
            tokens_out: Output token count
            raw_response: Raw response text

        Returns:
            ModelResponse with success data
        """
        return ModelResponse(
            model_name=self.model_name,
            model_version=self.model_version,
            status=ModelStatus.SUCCESS,
            latency_ms=latency_ms,
            raw_response=raw_response,
            parsed_response=parsed_response,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from model response text.

        Handles common issues like markdown code blocks around JSON.

        Args:
            text: Raw response text from model

        Returns:
            Parsed JSON dict or None if parsing fails
        """
        if not text:
            return None

        # Clean up common issues
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    async def close(self) -> None:
        """Clean up resources.

        Override in subclasses that need cleanup (e.g., HTTP clients).
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name}, version={self.model_version})"
