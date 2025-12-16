"""Technical analysis calculator for trading indicators."""

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from src.services.providers.base import OHLCV


@dataclass
class EMAResult:
    """Exponential Moving Average result."""

    period: int
    value: float


@dataclass
class MACDResult:
    """MACD indicator result."""

    macd_line: float
    signal_line: float
    histogram: float


@dataclass
class TAResult:
    """Complete technical analysis result for a timeframe."""

    ema: Dict[str, float]  # e.g., {"ema_9": 42000.0, "ema_21": 41800.0}
    macd: MACDResult
    rsi: float
    atr: float


class TACalculator:
    """
    Technical Analysis Calculator.

    Computes indicators from OHLCV data:
    - EMA (Exponential Moving Average)
    - MACD (Moving Average Convergence Divergence)
    - RSI (Relative Strength Index)
    - ATR (Average True Range)
    """

    @staticmethod
    def calculate_ema(closes: np.ndarray, period: int) -> float:
        """
        Calculate Exponential Moving Average.

        Args:
            closes: Array of closing prices (oldest to newest)
            period: EMA period

        Returns:
            Current EMA value
        """
        if len(closes) < period:
            # Not enough data, return simple average
            return float(np.mean(closes))

        # EMA multiplier
        multiplier = 2 / (period + 1)

        # Start with SMA for first EMA value
        ema = np.mean(closes[:period])

        # Calculate EMA for remaining values
        for close in closes[period:]:
            ema = (close - ema) * multiplier + ema

        return float(ema)

    @staticmethod
    def calculate_ema_series(closes: np.ndarray, period: int) -> np.ndarray:
        """
        Calculate EMA series for all values.

        Args:
            closes: Array of closing prices
            period: EMA period

        Returns:
            Array of EMA values
        """
        if len(closes) < period:
            return np.full(len(closes), np.nan)

        multiplier = 2 / (period + 1)
        ema = np.zeros(len(closes))
        ema[:period] = np.nan

        # First EMA is SMA
        ema[period - 1] = np.mean(closes[:period])

        # Calculate remaining EMAs
        for i in range(period, len(closes)):
            ema[i] = (closes[i] - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    @staticmethod
    def calculate_macd(
        closes: np.ndarray,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> MACDResult:
        """
        Calculate MACD (Moving Average Convergence Divergence).

        Args:
            closes: Array of closing prices
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line period (default 9)

        Returns:
            MACDResult with macd_line, signal_line, histogram
        """
        if len(closes) < slow_period + signal_period:
            return MACDResult(macd_line=0, signal_line=0, histogram=0)

        # Calculate fast and slow EMAs as series
        fast_ema = TACalculator.calculate_ema_series(closes, fast_period)
        slow_ema = TACalculator.calculate_ema_series(closes, slow_period)

        # MACD line = fast EMA - slow EMA
        macd_line = fast_ema - slow_ema

        # Signal line = EMA of MACD line
        # Get valid MACD values (after slow_period)
        valid_macd = macd_line[slow_period - 1 :]
        signal_ema = TACalculator.calculate_ema_series(valid_macd, signal_period)

        # Current values
        current_macd = float(macd_line[-1])
        current_signal = float(signal_ema[-1]) if len(signal_ema) > 0 else 0
        histogram = current_macd - current_signal

        return MACDResult(
            macd_line=round(current_macd, 4),
            signal_line=round(current_signal, 4),
            histogram=round(histogram, 4),
        )

    @staticmethod
    def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
        """
        Calculate Relative Strength Index.

        Args:
            closes: Array of closing prices
            period: RSI period (default 14)

        Returns:
            RSI value (0-100)
        """
        if len(closes) < period + 1:
            return 50.0  # Neutral if not enough data

        # Calculate price changes
        deltas = np.diff(closes)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gain/loss using Wilder's smoothing (EMA)
        # First average is simple average
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        # Smooth using Wilder's method
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(float(rsi), 2)

    @staticmethod
    def calculate_atr(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 14,
    ) -> float:
        """
        Calculate Average True Range.

        Args:
            highs: Array of high prices
            lows: Array of low prices
            closes: Array of closing prices
            period: ATR period (default 14)

        Returns:
            Current ATR value
        """
        if len(closes) < period + 1:
            # Not enough data, return simple range
            return float(np.mean(highs - lows))

        # True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]

        tr1 = highs - lows
        tr2 = np.abs(highs - prev_closes)
        tr3 = np.abs(lows - prev_closes)

        true_range = np.maximum(tr1, np.maximum(tr2, tr3))

        # ATR is EMA of True Range (Wilder's smoothing)
        atr = np.mean(true_range[:period])
        for i in range(period, len(true_range)):
            atr = (atr * (period - 1) + true_range[i]) / period

        return round(float(atr), 4)

    @classmethod
    def calculate_all(
        cls,
        candles: List[OHLCV],
        ema_periods: List[int] = None,
        macd_params: Dict = None,
        rsi_period: int = 14,
        atr_period: int = 14,
    ) -> Optional[TAResult]:
        """
        Calculate all technical indicators from candle data.

        Args:
            candles: List of OHLCV candles (oldest to newest)
            ema_periods: List of EMA periods to calculate (default [9, 21, 50])
            macd_params: MACD parameters dict (fast, slow, signal)
            rsi_period: RSI period
            atr_period: ATR period

        Returns:
            TAResult with all indicators, or None if not enough data
        """
        if not candles or len(candles) < 2:
            return None

        if ema_periods is None:
            ema_periods = [9, 21, 50]

        if macd_params is None:
            macd_params = {"fast": 12, "slow": 26, "signal": 9}

        # Convert candles to numpy arrays
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])

        # Calculate EMAs
        ema_results = {}
        for period in ema_periods:
            ema_value = cls.calculate_ema(closes, period)
            ema_results[f"ema_{period}"] = round(ema_value, 4)

        # Calculate MACD
        macd_result = cls.calculate_macd(
            closes,
            fast_period=macd_params.get("fast", 12),
            slow_period=macd_params.get("slow", 26),
            signal_period=macd_params.get("signal", 9),
        )

        # Calculate RSI
        rsi = cls.calculate_rsi(closes, rsi_period)

        # Calculate ATR
        atr = cls.calculate_atr(highs, lows, closes, atr_period)

        return TAResult(
            ema=ema_results,
            macd=macd_result,
            rsi=rsi,
            atr=atr,
        )
