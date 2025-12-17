"""Anthropic (Claude) model adapter.

This module provides integration with Anthropic's API for trading signal
evaluation using Claude models.

Features:
    - Async HTTP client for performance
    - JSON output enforcement via system prompt
    - Timeout handling
    - Token usage tracking

Configuration:
    Required environment variables:
    - MODEL_CLAUDE_API_KEY: Anthropic API key
    - MODEL_CLAUDE_MODEL_ID: Model to use (default: claude-sonnet-4-20250514)
    - MODEL_CLAUDE_TIMEOUT_MS: Request timeout (default: 30000)
    - MODEL_CLAUDE_MAX_TOKENS: Max output tokens (default: 1000)

Usage:
    config = ModelConfig(
        model_name="claude",
        provider="anthropic",
        api_key="sk-ant-...",
        model_id="claude-sonnet-4-20250514",
    )
    adapter = AnthropicAdapter(config)
    response = await adapter.evaluate(prompt)
"""

import asyncio
import time
from typing import Optional

from src.observability.logging import get_logger
from src.services.evaluation.models.base import (
    BaseModelAdapter,
    ModelConfig,
    ModelResponse,
    ModelStatus,
)

logger = get_logger(__name__)


class AnthropicAdapter(BaseModelAdapter):
    """Anthropic API adapter for Claude models.

    Uses the official anthropic SDK with async support.
    Configured for JSON output via system instructions.

    Class Invariants:
        - Client is lazily initialized on first evaluate() call
        - All errors are caught and returned in ModelResponse
        - Token usage is tracked for all successful requests

    Thread Safety:
        Safe for concurrent use from multiple async tasks.
    """

    def __init__(self, config: ModelConfig):
        """Initialize Anthropic adapter.

        Args:
            config: Model configuration with API key and parameters
        """
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Get or create the Anthropic client (lazy initialization).

        Returns:
            AsyncAnthropic client instance

        Raises:
            ImportError: If anthropic package is not installed
        """
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "anthropic package required for Anthropic adapter. "
                    "Install with: pip install anthropic"
                )

            self._client = AsyncAnthropic(
                api_key=self.config.api_key,
                timeout=self.config.timeout_seconds,
            )
        return self._client

    async def evaluate(self, prompt: str) -> ModelResponse:
        """Evaluate prompt using Anthropic API.

        Sends the prompt to Claude and parses the JSON response.
        Uses system prompt to enforce JSON output.

        Args:
            prompt: Fully rendered prompt to evaluate

        Returns:
            ModelResponse with evaluation results or error info
        """
        start_time = time.time()

        # Check configuration
        if not self.is_configured:
            return self._create_error_response(
                status=ModelStatus.INVALID_CONFIG,
                error_code="MISSING_API_KEY",
                error_message="Anthropic API key not configured",
                latency_ms=0,
            )

        try:
            client = self._get_client()

            # Make API call
            response = await asyncio.wait_for(
                client.messages.create(
                    model=self.config.model_id,
                    max_tokens=self.config.max_tokens,
                    system="You are a trading signal evaluation assistant. Respond only with valid JSON. No markdown, no explanations, just the JSON object.",
                    messages=[
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.config.temperature,
                ),
                timeout=self.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response content
            raw_response = ""
            if response.content and len(response.content) > 0:
                raw_response = response.content[0].text

            # Get token counts
            tokens_in = response.usage.input_tokens if response.usage else 0
            tokens_out = response.usage.output_tokens if response.usage else 0

            # Parse JSON response
            parsed = self._parse_json_response(raw_response)
            if parsed is None:
                return self._create_error_response(
                    status=ModelStatus.SCHEMA_ERROR,
                    error_code="JSON_PARSE_ERROR",
                    error_message="Failed to parse JSON from response",
                    latency_ms=latency_ms,
                    raw_response=raw_response,
                )

            logger.info(
                f"Claude evaluation complete: model={self.config.model_id}, "
                f"latency={latency_ms}ms, tokens={tokens_in}+{tokens_out}"
            )

            return self._create_success_response(
                parsed_response=parsed,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                raw_response=raw_response,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Claude request timed out after {latency_ms}ms")
            return self._create_error_response(
                status=ModelStatus.TIMEOUT,
                error_code="TIMEOUT",
                error_message=f"Request timed out after {self.config.timeout_ms}ms",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_type = type(e).__name__
            error_msg = str(e).lower()

            # Check for specific Anthropic errors
            if "rate_limit" in error_msg or "RateLimitError" in error_type:
                logger.warning(f"Claude rate limit hit: {e}")
                return self._create_error_response(
                    status=ModelStatus.RATE_LIMITED,
                    error_code="RATE_LIMITED",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            if "APIConnectionError" in error_type or "connection" in error_msg:
                logger.error(f"Claude connection error: {e}")
                return self._create_error_response(
                    status=ModelStatus.NETWORK_ERROR,
                    error_code="CONNECTION_ERROR",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            logger.error(f"Claude API error: {error_type}: {e}")
            return self._create_error_response(
                status=ModelStatus.API_ERROR,
                error_code=error_type,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
