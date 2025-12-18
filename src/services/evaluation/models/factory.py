"""Model adapter factory and output validation.

This module provides:
    1. Factory function to create model adapters from configuration
    2. Output validation to ensure AI responses match expected schema
    3. Fallback decision generation for error cases

Usage:
    # Create adapter from LLMConfigData (from database)
    from src.services.llm_config import LLMConfigData
    config_data = LLMConfigData(...)
    adapter = create_adapter("chatgpt", config_data)

    # Validate model output
    is_valid, errors = validate_decision_output(response.parsed_response)
"""

from typing import Dict, List, Optional, Tuple, Type, Any, TYPE_CHECKING

from src.observability.logging import get_logger
from src.services.evaluation.models.base import (
    BaseModelAdapter,
    ModelConfig,
    ModelResponse,
    ModelStatus,
)

if TYPE_CHECKING:
    from src.services.llm_config import LLMConfigData

logger = get_logger(__name__)

# Valid decision values
VALID_DECISIONS = {"FOLLOW_ENTER", "IGNORE", "FOLLOW_EXIT", "HOLD", "TIGHTEN_STOP"}

# Valid entry plan types
VALID_ENTRY_TYPES = {"market", "limit"}

# Valid stop methods
VALID_STOP_METHODS = {"fixed", "atr", "trailing"}


def get_adapter_class(provider: str) -> Type[BaseModelAdapter]:
    """Get the adapter class for a provider.

    Args:
        provider: Provider name (openai, google, anthropic, deepseek)

    Returns:
        Adapter class for the provider

    Raises:
        ValueError: If provider is not supported
    """
    # Import here to avoid circular imports
    from src.services.evaluation.models.openai_adapter import OpenAIAdapter
    from src.services.evaluation.models.google_adapter import GoogleAdapter
    from src.services.evaluation.models.anthropic_adapter import AnthropicAdapter
    from src.services.evaluation.models.deepseek_adapter import DeepSeekAdapter

    adapters = {
        "openai": OpenAIAdapter,
        "google": GoogleAdapter,
        "anthropic": AnthropicAdapter,
        "deepseek": DeepSeekAdapter,
    }

    provider_lower = provider.lower()
    if provider_lower not in adapters:
        raise ValueError(
            f"Unsupported provider: {provider}. "
            f"Supported: {list(adapters.keys())}"
        )

    return adapters[provider_lower]


def create_adapter(
    model_name: str,
    config_data: Optional["LLMConfigData"] = None,
) -> BaseModelAdapter:
    """Create a model adapter from configuration.

    Args:
        model_name: Name of the model (e.g., 'chatgpt', 'gemini', 'claude')
        config_data: LLMConfigData from database. Required for configured adapters.

    Returns:
        Configured model adapter instance

    Raises:
        ValueError: If config_data is not provided
    """
    if not config_data:
        raise ValueError(
            f"No configuration provided for model '{model_name}'. "
            f"Configure it via /api/v1/llm-configs/{model_name}"
        )

    # Use provided config data (from database)
    config = ModelConfig(
        model_name=model_name,
        provider=config_data.provider,
        api_key=config_data.api_key,
        model_id=config_data.model_id,
        timeout_ms=config_data.timeout_ms,
        max_tokens=config_data.max_tokens,
    )
    adapter_class = get_adapter_class(config_data.provider)
    return adapter_class(config)


def validate_decision_output(
    output: Dict[str, Any],
    strict: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate AI model output against expected schema.

    Checks that the output contains all required fields with valid values.

    Args:
        output: Parsed JSON output from model
        strict: If True, fail on unexpected fields

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if not isinstance(output, dict):
        return False, ["Output must be a JSON object"]

    # Required fields
    required_fields = ["decision", "confidence", "reasons"]
    for field in required_fields:
        if field not in output:
            errors.append(f"Missing required field: {field}")

    # Validate decision
    decision = output.get("decision")
    if decision and decision not in VALID_DECISIONS:
        errors.append(
            f"Invalid decision '{decision}'. "
            f"Must be one of: {', '.join(VALID_DECISIONS)}"
        )

    # Validate confidence
    confidence = output.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)):
            errors.append("confidence must be a number")
        elif not (0 <= confidence <= 1):
            errors.append(f"confidence must be between 0 and 1, got {confidence}")

    # Validate reasons
    reasons = output.get("reasons")
    if reasons is not None:
        if not isinstance(reasons, list):
            errors.append("reasons must be an array")
        elif len(reasons) == 0:
            errors.append("reasons must have at least one element")
        elif not all(isinstance(r, str) for r in reasons):
            errors.append("All reasons must be strings")

    # Validate entry_plan (optional)
    entry_plan = output.get("entry_plan")
    if entry_plan is not None:
        if not isinstance(entry_plan, dict):
            errors.append("entry_plan must be an object")
        else:
            entry_type = entry_plan.get("type")
            if entry_type and entry_type not in VALID_ENTRY_TYPES:
                errors.append(
                    f"Invalid entry_plan.type '{entry_type}'. "
                    f"Must be one of: {', '.join(VALID_ENTRY_TYPES)}"
                )
            offset = entry_plan.get("offset_bps")
            if offset is not None and not isinstance(offset, (int, float)):
                errors.append("entry_plan.offset_bps must be a number")

    # Validate risk_plan (optional)
    risk_plan = output.get("risk_plan")
    if risk_plan is not None:
        if not isinstance(risk_plan, dict):
            errors.append("risk_plan must be an object")
        else:
            stop_method = risk_plan.get("stop_method")
            if stop_method and stop_method not in VALID_STOP_METHODS:
                errors.append(
                    f"Invalid risk_plan.stop_method '{stop_method}'. "
                    f"Must be one of: {', '.join(VALID_STOP_METHODS)}"
                )

            atr_mult = risk_plan.get("atr_multiple")
            if atr_mult is not None:
                if not isinstance(atr_mult, (int, float)):
                    errors.append("risk_plan.atr_multiple must be a number")
                elif not (0.5 <= atr_mult <= 10):
                    errors.append(
                        f"risk_plan.atr_multiple must be between 0.5 and 10, got {atr_mult}"
                    )

            trail_pct = risk_plan.get("trail_pct")
            if trail_pct is not None:
                if not isinstance(trail_pct, (int, float)):
                    errors.append("risk_plan.trail_pct must be a number")
                elif not (0 <= trail_pct <= 100):
                    errors.append(
                        f"risk_plan.trail_pct must be between 0 and 100, got {trail_pct}"
                    )

    # Validate size_pct (optional)
    size_pct = output.get("size_pct")
    if size_pct is not None:
        if not isinstance(size_pct, (int, float)):
            errors.append("size_pct must be a number")
        elif not (0 <= size_pct <= 100):
            errors.append(f"size_pct must be between 0 and 100, got {size_pct}")

    return len(errors) == 0, errors


def create_fallback_decision(
    model_name: str,
    error_reason: str,
) -> Dict[str, Any]:
    """Create a fallback decision when model evaluation fails.

    Used when a model fails to produce valid output to ensure
    downstream systems always receive a decision.

    Args:
        model_name: Name of the model that failed
        error_reason: Description of the failure

    Returns:
        Fallback decision dict with IGNORE recommendation
    """
    return {
        "decision": "IGNORE",
        "confidence": 0.0,
        "entry_plan": None,
        "risk_plan": None,
        "size_pct": 0,
        "reasons": [
            f"model_error_{model_name}",
            "fallback_decision",
        ],
    }


def normalize_decision_output(output: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and clean up model output.

    Ensures all optional fields are present (with None values if missing)
    and values are within expected ranges.

    Args:
        output: Raw parsed output from model

    Returns:
        Normalized output dict
    """
    normalized = {
        "decision": output.get("decision", "IGNORE"),
        "confidence": output.get("confidence", 0.5),
        "entry_plan": output.get("entry_plan"),
        "risk_plan": output.get("risk_plan"),
        "size_pct": output.get("size_pct"),
        "reasons": output.get("reasons", ["unknown"]),
    }

    # Clamp confidence to valid range
    if normalized["confidence"] is not None:
        normalized["confidence"] = max(0.0, min(1.0, float(normalized["confidence"])))

    # Clamp size_pct to valid range
    if normalized["size_pct"] is not None:
        normalized["size_pct"] = max(0, min(100, int(normalized["size_pct"])))

    return normalized
