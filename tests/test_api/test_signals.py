"""Tests for signal submission endpoint."""

import pytest


@pytest.mark.unit
def test_signal_schema_validation(test_signal: dict):
    """Test signal schema validation with pydantic."""
    from src.models.schemas.signal import TradingSignalEvent

    # Valid signal should parse
    signal = TradingSignalEvent(**test_signal)
    assert signal.event_type == "OPEN_SIGNAL"
    assert signal.symbol == "BTC"
    assert signal.signal_direction == "long"


@pytest.mark.unit
def test_signal_schema_rejects_missing_field():
    """Test signal schema rejects missing required field."""
    from pydantic import ValidationError
    from src.models.schemas.signal import TradingSignalEvent

    incomplete = {
        "event_type": "OPEN_SIGNAL",
        "symbol": "BTC",
        # missing signal_direction, entry_price, size, liquidation_price, ts_utc, source
    }

    with pytest.raises(ValidationError):
        TradingSignalEvent(**incomplete)


@pytest.mark.unit
def test_signal_schema_rejects_invalid_event_type():
    """Test signal schema rejects invalid event_type."""
    from pydantic import ValidationError
    from src.models.schemas.signal import TradingSignalEvent

    invalid = {
        "event_type": "INVALID_TYPE",
        "symbol": "BTC",
        "signal_direction": "long",
        "entry_price": 42000.50,
        "size": 0.1,
        "ts_utc": "2024-01-15T10:30:00Z",
        "source": "test",
    }

    with pytest.raises(ValidationError):
        TradingSignalEvent(**invalid)


@pytest.mark.unit
def test_signal_schema_rejects_negative_price():
    """Test signal schema rejects negative prices."""
    from pydantic import ValidationError
    from src.models.schemas.signal import TradingSignalEvent

    invalid = {
        "event_type": "OPEN_SIGNAL",
        "symbol": "BTC",
        "signal_direction": "long",
        "entry_price": -100.0,
        "size": 0.1,
        "ts_utc": "2024-01-15T10:30:00Z",
        "source": "test",
    }

    with pytest.raises(ValidationError):
        TradingSignalEvent(**invalid)


@pytest.mark.unit
def test_signal_schema_rejects_zero_size():
    """Test signal schema rejects zero size."""
    from pydantic import ValidationError
    from src.models.schemas.signal import TradingSignalEvent

    invalid = {
        "event_type": "OPEN_SIGNAL",
        "symbol": "BTC",
        "signal_direction": "long",
        "entry_price": 42000.50,
        "size": 0,
        "ts_utc": "2024-01-15T10:30:00Z",
        "source": "test",
    }

    with pytest.raises(ValidationError):
        TradingSignalEvent(**invalid)


@pytest.mark.unit
def test_signal_response_schema():
    """Test signal response schema."""
    from datetime import datetime, timezone
    from src.models.schemas.signal import SignalSubmitResponse

    response = SignalSubmitResponse(
        event_id="test-123",
        status="ENQUEUED",
        received_at=datetime.now(timezone.utc),
    )

    assert response.event_id == "test-123"
    assert response.status == "ENQUEUED"
