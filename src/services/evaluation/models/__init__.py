"""AI model implementations.

This package provides adapters for various AI providers:
    - OpenAI (ChatGPT): openai_adapter.py
    - Google (Gemini): google_adapter.py
    - Anthropic (Claude): anthropic_adapter.py
    - DeepSeek: deepseek_adapter.py

All adapters implement the BaseModelAdapter interface defined in base.py.

Usage:
    from src.services.evaluation.models import create_adapter, validate_decision_output

    # Create adapter from environment config
    adapter = create_adapter("chatgpt")

    # Evaluate a prompt
    response = await adapter.evaluate(prompt)

    # Validate output
    is_valid, errors = validate_decision_output(response.parsed_response)
"""

from src.services.evaluation.models.base import (
    BaseModelAdapter,
    ModelConfig,
    ModelResponse,
    ModelStatus,
)
from src.services.evaluation.models.factory import (
    create_adapter,
    get_adapter_class,
    validate_decision_output,
    create_fallback_decision,
    normalize_decision_output,
)

__all__ = [
    # Base classes
    "BaseModelAdapter",
    "ModelConfig",
    "ModelResponse",
    "ModelStatus",
    # Factory functions
    "create_adapter",
    "get_adapter_class",
    "validate_decision_output",
    "create_fallback_decision",
    "normalize_decision_output",
]
