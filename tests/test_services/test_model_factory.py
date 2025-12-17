"""Tests for AI model adapter factory and output validation.

This module tests the factory pattern used to create AI model adapters
and the validation logic that ensures AI responses conform to the
expected decision schema.

Key test scenarios:
- Factory creates correct adapter types for each provider
- Invalid providers raise appropriate errors
- Decision output validation catches all schema violations
- Fallback decision generation for error cases
- Output normalization clamps values to valid ranges
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestAdapterFactory:
    """Tests for model adapter factory functions."""

    def test_get_adapter_class_openai(self):
        """Test factory returns OpenAI adapter for openai provider."""
        from src.services.evaluation.models.factory import get_adapter_class
        from src.services.evaluation.models.openai_adapter import OpenAIAdapter

        adapter_class = get_adapter_class("openai")
        assert adapter_class is OpenAIAdapter

    def test_get_adapter_class_google(self):
        """Test factory returns Google adapter for google provider."""
        from src.services.evaluation.models.factory import get_adapter_class
        from src.services.evaluation.models.google_adapter import GoogleAdapter

        adapter_class = get_adapter_class("google")
        assert adapter_class is GoogleAdapter

    def test_get_adapter_class_anthropic(self):
        """Test factory returns Anthropic adapter for anthropic provider."""
        from src.services.evaluation.models.factory import get_adapter_class
        from src.services.evaluation.models.anthropic_adapter import AnthropicAdapter

        adapter_class = get_adapter_class("anthropic")
        assert adapter_class is AnthropicAdapter

    def test_get_adapter_class_deepseek(self):
        """Test factory returns DeepSeek adapter for deepseek provider."""
        from src.services.evaluation.models.factory import get_adapter_class
        from src.services.evaluation.models.deepseek_adapter import DeepSeekAdapter

        adapter_class = get_adapter_class("deepseek")
        assert adapter_class is DeepSeekAdapter

    def test_get_adapter_class_case_insensitive(self):
        """Test that provider name matching is case-insensitive."""
        from src.services.evaluation.models.factory import get_adapter_class
        from src.services.evaluation.models.openai_adapter import OpenAIAdapter

        # Should work with different cases
        assert get_adapter_class("OpenAI") is OpenAIAdapter
        assert get_adapter_class("OPENAI") is OpenAIAdapter
        assert get_adapter_class("openai") is OpenAIAdapter

    def test_get_adapter_class_unknown_provider(self):
        """Test that unknown provider raises ValueError."""
        from src.services.evaluation.models.factory import get_adapter_class

        with pytest.raises(ValueError, match="Unsupported provider"):
            get_adapter_class("unknown_provider")


@pytest.mark.unit
class TestDecisionValidation:
    """Tests for AI decision output validation."""

    def test_valid_decision_passes(self):
        """Test that a valid decision passes validation."""
        from src.services.evaluation.models.factory import validate_decision_output

        valid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.78,
            "reasons": ["bullish_trend", "good_rr_ratio"],
            "entry_plan": {"type": "limit", "offset_bps": -5},
            "risk_plan": {"stop_method": "atr", "atr_multiple": 2.0},
            "size_pct": 15,
        }

        is_valid, errors = validate_decision_output(valid_output)

        assert is_valid is True
        assert len(errors) == 0

    def test_missing_required_field_fails(self):
        """Test that missing required fields are caught."""
        from src.services.evaluation.models.factory import validate_decision_output

        # Missing 'decision' field
        invalid_output = {
            "confidence": 0.78,
            "reasons": ["test"],
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("Missing required field: decision" in e for e in errors)

    def test_invalid_decision_value_fails(self):
        """Test that invalid decision values are caught."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "INVALID_DECISION",
            "confidence": 0.78,
            "reasons": ["test"],
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("Invalid decision" in e for e in errors)

    @pytest.mark.parametrize(
        "decision",
        ["FOLLOW_ENTER", "IGNORE", "FOLLOW_EXIT", "HOLD", "TIGHTEN_STOP"],
    )
    def test_all_valid_decisions(self, decision):
        """Test that all valid decision types pass validation."""
        from src.services.evaluation.models.factory import validate_decision_output

        output = {
            "decision": decision,
            "confidence": 0.5,
            "reasons": ["test"],
        }

        is_valid, errors = validate_decision_output(output)
        assert is_valid is True

    def test_confidence_out_of_range_fails(self):
        """Test that confidence outside 0-1 range fails."""
        from src.services.evaluation.models.factory import validate_decision_output

        # Confidence > 1
        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 1.5,
            "reasons": ["test"],
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("confidence must be between 0 and 1" in e for e in errors)

        # Confidence < 0
        invalid_output["confidence"] = -0.5
        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False

    def test_reasons_must_be_array(self):
        """Test that reasons must be an array."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": "not_an_array",
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("reasons must be an array" in e for e in errors)

    def test_reasons_must_be_non_empty(self):
        """Test that reasons array cannot be empty."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": [],
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("reasons must have at least one element" in e for e in errors)

    def test_invalid_entry_plan_type_fails(self):
        """Test that invalid entry_plan.type fails."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            "entry_plan": {"type": "invalid_type"},
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("Invalid entry_plan.type" in e for e in errors)

    def test_invalid_stop_method_fails(self):
        """Test that invalid risk_plan.stop_method fails."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            "risk_plan": {"stop_method": "invalid_method"},
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("Invalid risk_plan.stop_method" in e for e in errors)

    def test_atr_multiple_range_validation(self):
        """Test ATR multiple must be between 0.5 and 10."""
        from src.services.evaluation.models.factory import validate_decision_output

        # Too low
        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            "risk_plan": {"stop_method": "atr", "atr_multiple": 0.1},
        }

        is_valid, errors = validate_decision_output(invalid_output)
        assert is_valid is False
        assert any("atr_multiple must be between 0.5 and 10" in e for e in errors)

        # Too high
        invalid_output["risk_plan"]["atr_multiple"] = 15
        is_valid, errors = validate_decision_output(invalid_output)
        assert is_valid is False

    def test_size_pct_range_validation(self):
        """Test size_pct must be between 0 and 100."""
        from src.services.evaluation.models.factory import validate_decision_output

        invalid_output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            "size_pct": 150,  # > 100
        }

        is_valid, errors = validate_decision_output(invalid_output)

        assert is_valid is False
        assert any("size_pct must be between 0 and 100" in e for e in errors)


@pytest.mark.unit
class TestFallbackDecision:
    """Tests for fallback decision generation."""

    def test_fallback_decision_structure(self):
        """Test that fallback decision has correct structure."""
        from src.services.evaluation.models.factory import create_fallback_decision

        fallback = create_fallback_decision("chatgpt", "API timeout")

        assert fallback["decision"] == "IGNORE"
        assert fallback["confidence"] == 0.0
        assert fallback["size_pct"] == 0
        assert "model_error_chatgpt" in fallback["reasons"]
        assert "fallback_decision" in fallback["reasons"]

    def test_fallback_includes_model_name(self):
        """Test that fallback decision includes the failing model name."""
        from src.services.evaluation.models.factory import create_fallback_decision

        fallback = create_fallback_decision("gemini", "Rate limited")

        assert any("gemini" in reason for reason in fallback["reasons"])


@pytest.mark.unit
class TestOutputNormalization:
    """Tests for decision output normalization."""

    def test_normalize_clamps_confidence(self):
        """Test that normalization clamps confidence to 0-1."""
        from src.services.evaluation.models.factory import normalize_decision_output

        output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 1.5,  # Will be clamped to 1.0
            "reasons": ["test"],
        }

        normalized = normalize_decision_output(output)

        assert normalized["confidence"] == 1.0

        # Test clamping to 0
        output["confidence"] = -0.5
        normalized = normalize_decision_output(output)
        assert normalized["confidence"] == 0.0

    def test_normalize_clamps_size_pct(self):
        """Test that normalization clamps size_pct to 0-100."""
        from src.services.evaluation.models.factory import normalize_decision_output

        output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            "size_pct": 150,  # Will be clamped to 100
        }

        normalized = normalize_decision_output(output)

        assert normalized["size_pct"] == 100

    def test_normalize_provides_defaults(self):
        """Test that normalization provides defaults for missing optional fields."""
        from src.services.evaluation.models.factory import normalize_decision_output

        output = {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.5,
            "reasons": ["test"],
            # Missing entry_plan, risk_plan, size_pct
        }

        normalized = normalize_decision_output(output)

        assert normalized["entry_plan"] is None
        assert normalized["risk_plan"] is None
        assert normalized["size_pct"] is None
