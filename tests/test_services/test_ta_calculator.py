"""Tests for the technical analysis calculator."""

import pytest
import numpy as np

from src.services.providers.base import OHLCV
from datetime import datetime, timezone


@pytest.mark.unit
class TestTACalculator:
    """Test TA calculator functions."""

    def _make_candles(self, closes: list, spread: float = 0.01) -> list[OHLCV]:
        """Create OHLCV candles from close prices."""
        candles = []
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for i, close in enumerate(closes):
            candles.append(
                OHLCV(
                    timestamp=base_time.replace(hour=i % 24),
                    open=close * (1 - spread / 2),
                    high=close * (1 + spread),
                    low=close * (1 - spread),
                    close=close,
                    volume=1000.0,
                )
            )
        return candles

    def test_calculate_ema_basic(self):
        """Test EMA calculation with simple data."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Simple ascending prices
        closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        ema = TACalculator.calculate_ema(closes, period=5)

        # EMA should be less than the latest close for uptrend
        assert ema < 20.0
        assert ema > 15.0  # Should be weighted toward recent values

    def test_calculate_ema_not_enough_data(self):
        """Test EMA with insufficient data returns simple average."""
        from src.services.enrichment.ta_calculator import TACalculator

        closes = np.array([10.0, 11.0, 12.0])
        ema = TACalculator.calculate_ema(closes, period=5)

        # Should return simple average when period > data length
        assert ema == pytest.approx(11.0, rel=0.01)

    def test_calculate_macd_basic(self):
        """Test MACD calculation."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Create trending price data
        closes = np.array([float(100 + i * 0.5) for i in range(50)])
        macd = TACalculator.calculate_macd(closes)

        # In uptrend, MACD should be positive
        assert macd.macd_line > 0
        assert isinstance(macd.histogram, float)

    def test_calculate_macd_not_enough_data(self):
        """Test MACD with insufficient data returns zeros."""
        from src.services.enrichment.ta_calculator import TACalculator

        closes = np.array([10.0, 11.0, 12.0])
        macd = TACalculator.calculate_macd(closes)

        assert macd.macd_line == 0
        assert macd.signal_line == 0
        assert macd.histogram == 0

    def test_calculate_rsi_oversold(self):
        """Test RSI calculation in downtrend (should be low)."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Declining prices
        closes = np.array([float(100 - i) for i in range(30)])
        rsi = TACalculator.calculate_rsi(closes, period=14)

        # RSI should be low (oversold) in downtrend
        assert rsi < 30

    def test_calculate_rsi_overbought(self):
        """Test RSI calculation in uptrend (should be high)."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Rising prices
        closes = np.array([float(100 + i) for i in range(30)])
        rsi = TACalculator.calculate_rsi(closes, period=14)

        # RSI should be high (overbought) in uptrend
        assert rsi > 70

    def test_calculate_rsi_neutral(self):
        """Test RSI calculation with oscillating prices (no clear trend)."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Oscillating prices (no clear trend) - alternating up/down
        closes = np.array([100.0 + (i % 2) * 2 - 1 for i in range(30)])
        rsi = TACalculator.calculate_rsi(closes, period=14)

        # RSI should be roughly neutral for oscillating prices
        assert 30 < rsi < 70  # Somewhere in the middle range

    def test_calculate_rsi_not_enough_data(self):
        """Test RSI with insufficient data returns neutral."""
        from src.services.enrichment.ta_calculator import TACalculator

        closes = np.array([10.0, 11.0])
        rsi = TACalculator.calculate_rsi(closes, period=14)

        assert rsi == 50.0

    def test_calculate_atr_basic(self):
        """Test ATR calculation."""
        from src.services.enrichment.ta_calculator import TACalculator

        n = 30
        highs = np.array([float(105 + i * 0.1) for i in range(n)])
        lows = np.array([float(95 + i * 0.1) for i in range(n)])
        closes = np.array([float(100 + i * 0.1) for i in range(n)])

        atr = TACalculator.calculate_atr(highs, lows, closes, period=14)

        # ATR should be approximately the average range
        assert atr > 0
        assert atr < 20  # Should be reasonable

    def test_calculate_atr_volatile_market(self):
        """Test ATR is higher in volatile market."""
        from src.services.enrichment.ta_calculator import TACalculator

        n = 30
        # Low volatility
        highs_low = np.array([float(101 + i * 0.1) for i in range(n)])
        lows_low = np.array([float(99 + i * 0.1) for i in range(n)])
        closes_low = np.array([float(100 + i * 0.1) for i in range(n)])

        # High volatility
        highs_high = np.array([float(110 + i * 0.1) for i in range(n)])
        lows_high = np.array([float(90 + i * 0.1) for i in range(n)])
        closes_high = np.array([float(100 + i * 0.1) for i in range(n)])

        atr_low = TACalculator.calculate_atr(highs_low, lows_low, closes_low, period=14)
        atr_high = TACalculator.calculate_atr(highs_high, lows_high, closes_high, period=14)

        assert atr_high > atr_low

    def test_calculate_all_with_candles(self):
        """Test calculate_all with OHLCV candles."""
        from src.services.enrichment.ta_calculator import TACalculator

        # Create realistic candle data
        closes = [float(100 + i * 0.5 + np.random.normal(0, 1)) for i in range(100)]
        candles = self._make_candles(closes)

        result = TACalculator.calculate_all(
            candles=candles,
            ema_periods=[9, 21, 50],
            macd_params={"fast": 12, "slow": 26, "signal": 9},
            rsi_period=14,
            atr_period=14,
        )

        assert result is not None
        assert "ema_9" in result.ema
        assert "ema_21" in result.ema
        assert "ema_50" in result.ema
        assert result.macd is not None
        assert 0 <= result.rsi <= 100
        assert result.atr > 0

    def test_calculate_all_empty_candles(self):
        """Test calculate_all with empty candles returns None."""
        from src.services.enrichment.ta_calculator import TACalculator

        result = TACalculator.calculate_all(candles=[])
        assert result is None

    def test_calculate_all_single_candle(self):
        """Test calculate_all with single candle returns None."""
        from src.services.enrichment.ta_calculator import TACalculator

        candles = self._make_candles([100.0])
        result = TACalculator.calculate_all(candles=candles)
        assert result is None
