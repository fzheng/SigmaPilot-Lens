"""Tests for the signal validator."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.core.exceptions import SignalRejectedError, ProviderError
from src.services.providers.base import Ticker


@pytest.fixture
def mock_ticker():
    """Create mock ticker at $50000."""
    return Ticker(
        symbol="BTC",
        mid=50000.0,
        bid=49990.0,
        ask=50010.0,
        spread_bps=4.0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_provider(mock_ticker):
    """Create mock provider."""
    provider = MagicMock()
    provider.get_ticker = AsyncMock(return_value=mock_ticker)
    provider.close = AsyncMock()
    return provider


@pytest.mark.unit
class TestSignalValidator:
    """Test signal validation logic."""

    @pytest.mark.asyncio
    async def test_valid_signal_within_drift_threshold(self, mock_provider):
        """Test signal with small drift passes validation."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Entry price within 2% of current ($50000)
        signal = {
            "symbol": "BTC",
            "entry_price": 49500.0,  # 1% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is True
        assert result.current_price == 50000.0
        assert result.drift_bps < 200  # Less than 2%
        assert result.rejection_reason is None

        await validator.close()

    @pytest.mark.asyncio
    async def test_signal_rejected_excessive_drift(self, mock_provider):
        """Test signal with >2% drift is rejected."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Entry price with >2% drift (current is $50000)
        signal = {
            "symbol": "BTC",
            "entry_price": 45000.0,  # ~11% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is False
        assert result.drift_bps > 200
        assert "drift" in result.rejection_reason.lower()

        await validator.close()

    @pytest.mark.asyncio
    async def test_signal_rejected_excessive_drift_raises(self, mock_provider):
        """Test signal rejection raises SignalRejectedError when configured."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC",
            "entry_price": 45000.0,  # >2% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        with pytest.raises(SignalRejectedError) as exc_info:
            await validator.validate(signal, raise_on_invalid=True)

        assert exc_info.value.symbol == "BTC"
        assert "drift" in exc_info.value.reason.lower()
        assert exc_info.value.details[0]["entry_price"] == 45000.0
        assert exc_info.value.details[0]["current_price"] == 50000.0

        await validator.close()

    @pytest.mark.asyncio
    async def test_signal_rejected_too_old(self, mock_provider):
        """Test signal older than threshold is rejected."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Signal from 10 minutes ago (default threshold is 5 minutes)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        signal = {
            "symbol": "BTC",
            "entry_price": 50000.0,  # No drift
            "ts_utc": old_time.isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is False
        assert result.signal_age_seconds > 300  # >5 minutes
        assert "old" in result.rejection_reason.lower()

        await validator.close()

    @pytest.mark.asyncio
    async def test_signal_age_check_before_price_fetch(self, mock_provider):
        """Test that old signals are rejected without fetching price (optimization)."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Signal from 10 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        signal = {
            "symbol": "BTC",
            "entry_price": 50000.0,
            "ts_utc": old_time.isoformat(),
        }

        with pytest.raises(SignalRejectedError):
            await validator.validate(signal, raise_on_invalid=True)

        # Price should NOT have been fetched (optimization)
        mock_provider.get_ticker.assert_not_called()

        await validator.close()

    @pytest.mark.asyncio
    async def test_fresh_signal_fetches_price(self, mock_provider):
        """Test that fresh signals fetch price for validation."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC",
            "entry_price": 49500.0,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        await validator.validate(signal, raise_on_invalid=True)

        # Price should have been fetched
        mock_provider.get_ticker.assert_called_once_with("BTC")

        await validator.close()

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self, mock_provider):
        """Test that provider errors are propagated."""
        from src.services.enrichment.signal_validator import SignalValidator

        mock_provider.get_ticker = AsyncMock(
            side_effect=ProviderError("hyperliquid", "API error")
        )
        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC",
            "entry_price": 50000.0,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        with pytest.raises(ProviderError):
            await validator.validate(signal, raise_on_invalid=True)

        await validator.close()

    @pytest.mark.asyncio
    async def test_missing_timestamp_still_validates_price(self, mock_provider):
        """Test signal without timestamp still validates price drift."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # No timestamp provided
        signal = {
            "symbol": "BTC",
            "entry_price": 49500.0,
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is True
        assert result.signal_age_seconds == 0.0  # No age calculated

        await validator.close()

    @pytest.mark.asyncio
    async def test_custom_thresholds(self, mock_provider):
        """Test custom drift and age thresholds."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)
        validator.max_drift_bps = 100  # 1% instead of 2%
        validator.max_signal_age = 60  # 1 minute instead of 5

        # 1.5% drift - would pass default but fail custom
        signal = {
            "symbol": "BTC",
            "entry_price": 49250.0,  # 1.5% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is False
        assert "drift" in result.rejection_reason.lower()

        await validator.close()

    @pytest.mark.asyncio
    async def test_drift_calculation_both_directions(self, mock_provider):
        """Test drift is calculated correctly for both up and down moves."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Entry below current (price went up)
        signal_below = {
            "symbol": "BTC",
            "entry_price": 48000.0,  # 4% below current
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        result_below = await validator.validate(signal_below, raise_on_invalid=False)
        assert result_below.valid is False  # >2% drift

        # Entry above current (price went down)
        signal_above = {
            "symbol": "BTC",
            "entry_price": 52000.0,  # 4% above current
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        result_above = await validator.validate(signal_above, raise_on_invalid=False)
        assert result_above.valid is False  # >2% drift

        await validator.close()

    @pytest.mark.asyncio
    async def test_zero_entry_price_skips_drift_check(self, mock_provider):
        """Test that zero entry price doesn't cause division error."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC",
            "entry_price": 0.0,  # Zero price
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        # Should be valid since drift can't be calculated
        assert result.valid is True
        assert result.drift_bps == 0.0

        await validator.close()

    @pytest.mark.asyncio
    async def test_exact_threshold_boundary(self, mock_provider):
        """Test signal at exactly 2% drift threshold."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # 2% drift = 200 bps exactly (current is $50000)
        # 2% of 50000 = 1000, so entry at 49000 is exactly 2%
        signal = {
            "symbol": "BTC",
            "entry_price": 49000.0,  # Exactly 2% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        # 2% is the threshold, so exactly 2% should be rejected (> not >=)
        # Actually drift is (50000-49000)/49000 = 2.04%, so rejected
        assert result.valid is False

        await validator.close()

    @pytest.mark.asyncio
    async def test_just_under_threshold(self, mock_provider):
        """Test signal just under 2% drift threshold passes."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # 1.5% drift should pass (current is $50000)
        # Entry at 49250 = (50000-49250)/49250 = 1.52%
        signal = {
            "symbol": "BTC",
            "entry_price": 49250.0,  # ~1.5% drift
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        assert result.valid is True
        assert result.drift_bps < 200

        await validator.close()

    @pytest.mark.asyncio
    async def test_signal_age_boundary(self, mock_provider):
        """Test signal at exactly 5 minute age threshold."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        # Signal exactly at 5 minute threshold (300s)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        signal = {
            "symbol": "BTC",
            "entry_price": 50000.0,
            "ts_utc": old_time.isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        # 301s > 300s threshold, so rejected
        assert result.valid is False
        assert "old" in result.rejection_reason.lower()

        await validator.close()


@pytest.mark.unit
class TestSignalValidatorEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_symbol(self, mock_provider):
        """Test handling of unusual symbol formats."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC-PERP",  # Should be normalized by provider
            "entry_price": 50000.0,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        # Should work - provider handles normalization
        assert result.valid is True

        await validator.close()

    @pytest.mark.asyncio
    async def test_empty_signal(self, mock_provider):
        """Test handling of empty signal dict."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {}  # Empty signal

        result = await validator.validate(signal, raise_on_invalid=False)

        # Should be valid since no entry price = no drift check
        assert result.valid is True
        assert result.entry_price == 0.0

        await validator.close()

    @pytest.mark.asyncio
    async def test_validation_result_contains_all_fields(self, mock_provider):
        """Test ValidationResult has all expected fields."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "BTC",
            "entry_price": 49500.0,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        result = await validator.validate(signal, raise_on_invalid=False)

        # Check all fields are present
        assert hasattr(result, "valid")
        assert hasattr(result, "current_price")
        assert hasattr(result, "entry_price")
        assert hasattr(result, "drift_bps")
        assert hasattr(result, "signal_age_seconds")
        assert hasattr(result, "rejection_reason")

        # Check values
        assert result.current_price == 50000.0
        assert result.entry_price == 49500.0
        assert result.drift_bps > 0
        assert result.signal_age_seconds >= 0

        await validator.close()

    @pytest.mark.asyncio
    async def test_rejection_error_details(self, mock_provider):
        """Test SignalRejectedError contains useful details."""
        from src.services.enrichment.signal_validator import SignalValidator

        validator = SignalValidator(provider=mock_provider)

        signal = {
            "symbol": "ETH",
            "entry_price": 40000.0,  # Way off from mock ($50000)
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        with pytest.raises(SignalRejectedError) as exc_info:
            await validator.validate(signal, raise_on_invalid=True)

        error = exc_info.value

        # Check error attributes
        assert error.symbol == "ETH"
        assert "drift" in error.reason.lower()

        # Check details dict
        assert len(error.details) > 0
        details = error.details[0]
        assert "entry_price" in details
        assert "current_price" in details
        assert "drift_bps" in details
        assert "max_drift_bps" in details

        await validator.close()
