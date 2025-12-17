"""DeepSeek model adapter.

This module provides integration with DeepSeek's API for trading signal
evaluation. DeepSeek provides an OpenAI-compatible API endpoint.

Features:
    - OpenAI SDK compatible (uses openai package)
    - JSON output enforcement
    - Timeout handling
    - Token usage tracking

Configuration:
    Required environment variables:
    - MODEL_DEEPSEEK_API_KEY: DeepSeek API key
    - MODEL_DEEPSEEK_MODEL_ID: Model to use (default: deepseek-chat)
    - MODEL_DEEPSEEK_TIMEOUT_MS: Request timeout (default: 30000)
    - MODEL_DEEPSEEK_MAX_TOKENS: Max output tokens (default: 1000)

Usage:
    config = ModelConfig(
        model_name="deepseek",
        provider="deepseek",
        api_key="sk-...",
        model_id="deepseek-chat",
    )
    adapter = DeepSeekAdapter(config)
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

# DeepSeek API base URL (OpenAI-compatible)
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter(BaseModelAdapter):
    """DeepSeek API adapter.

    Uses the OpenAI SDK with a custom base URL since DeepSeek
    provides an OpenAI-compatible API.

    Class Invariants:
        - Client is lazily initialized on first evaluate() call
        - All errors are caught and returned in ModelResponse
        - Token usage is tracked for all successful requests

    Thread Safety:
        Safe for concurrent use from multiple async tasks.
    """

    def __init__(self, config: ModelConfig):
        """Initialize DeepSeek adapter.

        Args:
            config: Model configuration with API key and parameters
        """
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Get or create the OpenAI-compatible client (lazy initialization).

        Returns:
            AsyncOpenAI client configured for DeepSeek

        Raises:
            ImportError: If openai package is not installed
        """
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package required for DeepSeek adapter. "
                    "Install with: pip install openai"
                )

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=DEEPSEEK_BASE_URL,
                timeout=self.config.timeout_seconds,
            )
        return self._client

    async def evaluate(self, prompt: str) -> ModelResponse:
        """Evaluate prompt using DeepSeek API.

        Sends the prompt to DeepSeek and parses the JSON response.
        Uses JSON mode for structured output (if supported by model).

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
                error_message="DeepSeek API key not configured",
                latency_ms=0,
            )

        try:
            client = self._get_client()

            # Make API call
            # Note: DeepSeek may not support response_format, so we rely on
            # the system prompt to enforce JSON output
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self.config.model_id,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a trading signal evaluation assistant. Respond only with valid JSON. No markdown code blocks, no explanations, just the raw JSON object.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                ),
                timeout=self.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response content
            raw_response = response.choices[0].message.content
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0

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
                f"DeepSeek evaluation complete: model={self.config.model_id}, "
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
            logger.warning(f"DeepSeek request timed out after {latency_ms}ms")
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

            # Check for specific errors
            if "rate_limit" in error_msg or "RateLimitError" in error_type:
                logger.warning(f"DeepSeek rate limit hit: {e}")
                return self._create_error_response(
                    status=ModelStatus.RATE_LIMITED,
                    error_code="RATE_LIMITED",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            if "connection" in error_msg or "network" in error_msg:
                logger.error(f"DeepSeek connection error: {e}")
                return self._create_error_response(
                    status=ModelStatus.NETWORK_ERROR,
                    error_code="CONNECTION_ERROR",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            logger.error(f"DeepSeek API error: {error_type}: {e}")
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
