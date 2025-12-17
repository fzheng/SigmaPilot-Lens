"""Google (Gemini) model adapter.

This module provides integration with Google's Generative AI API for trading
signal evaluation using Gemini models.

Features:
    - JSON output enforcement via generation config
    - Timeout handling
    - Token usage tracking
    - Safety settings configured for trading content

Configuration:
    Required environment variables:
    - MODEL_GEMINI_API_KEY: Google AI API key
    - MODEL_GEMINI_MODEL_ID: Model to use (default: gemini-1.5-pro)
    - MODEL_GEMINI_TIMEOUT_MS: Request timeout (default: 30000)
    - MODEL_GEMINI_MAX_TOKENS: Max output tokens (default: 1000)

Usage:
    config = ModelConfig(
        model_name="gemini",
        provider="google",
        api_key="AI...",
        model_id="gemini-1.5-pro",
    )
    adapter = GoogleAdapter(config)
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


class GoogleAdapter(BaseModelAdapter):
    """Google Generative AI adapter for Gemini models.

    Uses the official google-generativeai SDK.
    Configured for JSON output with appropriate safety settings.

    Class Invariants:
        - Model is configured on first evaluate() call
        - All errors are caught and returned in ModelResponse
        - Thread-safe for concurrent async usage

    Note:
        The Google GenAI SDK uses a synchronous API, so we run it
        in an executor for async compatibility.
    """

    def __init__(self, config: ModelConfig):
        """Initialize Google adapter.

        Args:
            config: Model configuration with API key and parameters
        """
        super().__init__(config)
        self._configured = False
        self._model = None

    def _configure(self):
        """Configure the Google GenAI SDK (lazy initialization).

        Raises:
            ImportError: If google-generativeai package is not installed
        """
        if self._configured:
            return

        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai package required for Google adapter. "
                "Install with: pip install google-generativeai"
            )

        genai.configure(api_key=self.config.api_key)

        # Configure generation settings
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            response_mime_type="application/json",
        )

        # Configure safety settings to allow trading/financial content
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        self._model = genai.GenerativeModel(
            model_name=self.config.model_id,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        self._configured = True

    async def evaluate(self, prompt: str) -> ModelResponse:
        """Evaluate prompt using Google Gemini API.

        Sends the prompt to Gemini and parses the JSON response.
        Uses JSON mime type for structured output.

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
                error_message="Google AI API key not configured",
                latency_ms=0,
            )

        try:
            self._configure()

            # Run in executor since Google SDK is sync
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._model.generate_content(prompt),
                ),
                timeout=self.config.timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Check for blocked response
            if not response.candidates:
                return self._create_error_response(
                    status=ModelStatus.API_ERROR,
                    error_code="NO_CANDIDATES",
                    error_message="Response was blocked or empty",
                    latency_ms=latency_ms,
                )

            # Extract response content
            raw_response = response.text

            # Get token counts if available
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, 'prompt_token_count', 0)
                tokens_out = getattr(response.usage_metadata, 'candidates_token_count', 0)

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
                f"Gemini evaluation complete: model={self.config.model_id}, "
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
            logger.warning(f"Gemini request timed out after {latency_ms}ms")
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

            # Check for specific Google API errors
            if "quota" in error_msg or "rate" in error_msg:
                logger.warning(f"Gemini rate limit/quota hit: {e}")
                return self._create_error_response(
                    status=ModelStatus.RATE_LIMITED,
                    error_code="RATE_LIMITED",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            if "connection" in error_msg or "network" in error_msg:
                logger.error(f"Gemini connection error: {e}")
                return self._create_error_response(
                    status=ModelStatus.NETWORK_ERROR,
                    error_code="CONNECTION_ERROR",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            logger.error(f"Gemini API error: {error_type}: {e}")
            return self._create_error_response(
                status=ModelStatus.API_ERROR,
                error_code=error_type,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def close(self) -> None:
        """Clean up resources (no-op for Google SDK)."""
        self._model = None
        self._configured = False
