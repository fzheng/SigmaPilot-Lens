"""Technical analysis calculator for trading indicators.

Computes technical indicators from OHLCV data:
- EMA (Exponential Moving Average)
- SMA (Simple Moving Average)
- MACD (Moving Average Convergence Divergence)
- RSI (Relative Strength Index)
- ATR (Average True Range)
- Bollinger Bands (upper, lower, width, rating)
- ADX (Average Directional Index)
- Stochastic (K, D)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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
class BollingerBandsResult:
    """Bollinger Bands indicator result."""

    upper: float          # Upper band (SMA + 2*std)
    middle: float         # Middle band (SMA20)
    lower: float          # Lower band (SMA - 2*std)
    bbw: float            # Band width: (upper - lower) / middle
    rating: int           # Position rating: -3 to +3
    signal: str           # BUY, SELL, or NEUTRAL


@dataclass
class StochasticResult:
    """Stochastic oscillator result."""

    k: float              # %K (fast stochastic)
    d: float              # %D (slow stochastic, SMA of %K)
    signal: str           # OVERBOUGHT, OVERSOLD, or NEUTRAL


@dataclass
class TAResult:
    """Complete technical analysis result for a timeframe."""

    ema: Dict[str, float]  # e.g., {"ema_9": 42000.0, "ema_21": 41800.0}
    sma: Dict[str, float]  # e.g., {"sma_20": 41900.0}
    macd: MACDResult
    rsi: float
    atr: float
    bollinger: Optional[BollingerBandsResult] = None
    adx: Optional[float] = None
    stochastic: Optional[StochasticResult] = None
    volume: Optional[float] = None
    volume_sma: Optional[float] = None


class TACalculator:
    """
    Technical Analysis Calculator.

    Computes indicators from OHLCV data:
    - EMA (Exponential Moving Average)
    - SMA (Simple Moving Average)
    - MACD (Moving Average Convergence Divergence)
    - RSI (Relative Strength Index)
    - ATR (Average True Range)
    - Bollinger Bands (upper, lower, width, rating)
    - ADX (Average Directional Index)
    - Stochastic (K, D)
    """

    @staticmethod
    def calculate_sma(data: np.ndarray, period: int) -> float:
        """
        Calculate Simple Moving Average.

        Args:
            data: Array of values (oldest to newest)
            period: SMA period

        Returns:
            Current SMA value
        """
        if len(data) < period:
            return float(np.mean(data))
        return float(np.mean(data[-period:]))

    @staticmethod
    def calculate_sma_series(data: np.ndarray, period: int) -> np.ndarray:
        """
        Calculate SMA series for all values.

        Args:
            data: Array of values
            period: SMA period

        Returns:
            Array of SMA values
        """
        if len(data) < period:
            return np.full(len(data), np.nan)

        sma = np.zeros(len(data))
        sma[:period - 1] = np.nan

        for i in range(period - 1, len(data)):
            sma[i] = np.mean(data[i - period + 1:i + 1])

        return sma

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

    @staticmethod
    def calculate_bollinger_bands(
        closes: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> BollingerBandsResult:
        """
        Calculate Bollinger Bands.

        Args:
            closes: Array of closing prices
            period: SMA period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)

        Returns:
            BollingerBandsResult with upper, middle, lower, bbw, rating, signal
        """
        if len(closes) < period:
            current_price = closes[-1] if len(closes) > 0 else 0
            return BollingerBandsResult(
                upper=current_price,
                middle=current_price,
                lower=current_price,
                bbw=0.0,
                rating=0,
                signal="NEUTRAL",
            )

        # Calculate middle band (SMA)
        middle = float(np.mean(closes[-period:]))

        # Calculate standard deviation
        std = float(np.std(closes[-period:]))

        # Calculate upper and lower bands
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        # Calculate BBW (Band Width)
        bbw = (upper - lower) / middle if middle != 0 else 0

        # Calculate rating based on price position
        current_price = closes[-1]
        rating, signal = TACalculator._compute_bb_rating(
            current_price, upper, middle, lower
        )

        return BollingerBandsResult(
            upper=round(upper, 4),
            middle=round(middle, 4),
            lower=round(lower, 4),
            bbw=round(bbw, 4),
            rating=rating,
            signal=signal,
        )

    @staticmethod
    def _compute_bb_rating(
        close: float, bb_upper: float, bb_middle: float, bb_lower: float
    ) -> Tuple[int, str]:
        """
        Compute Bollinger Band rating and signal.

        Rating scale:
            +3: Strong Buy (price above upper band)
            +2: Buy (price in upper 50% of bands)
            +1: Weak Buy (price above middle line)
             0: Neutral (price at middle line)
            -1: Weak Sell (price below middle line)
            -2: Sell (price in lower 50% of bands)
            -3: Strong Sell (price below lower band)

        Args:
            close: Current closing price
            bb_upper: Upper Bollinger Band
            bb_middle: Middle Bollinger Band (SMA)
            bb_lower: Lower Bollinger Band

        Returns:
            Tuple of (rating, signal)
        """
        rating = 0
        if close > bb_upper:
            rating = 3
        elif close > bb_middle + ((bb_upper - bb_middle) / 2):
            rating = 2
        elif close > bb_middle:
            rating = 1
        elif close < bb_lower:
            rating = -3
        elif close < bb_middle - ((bb_middle - bb_lower) / 2):
            rating = -2
        elif close < bb_middle:
            rating = -1

        signal = "NEUTRAL"
        if rating >= 2:
            signal = "BUY"
        elif rating <= -2:
            signal = "SELL"

        return rating, signal

    @staticmethod
    def calculate_adx(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 14,
    ) -> float:
        """
        Calculate Average Directional Index (ADX).

        ADX measures trend strength (0-100):
            0-25: Weak or no trend
            25-50: Strong trend
            50-75: Very strong trend
            75-100: Extremely strong trend

        Args:
            highs: Array of high prices
            lows: Array of low prices
            closes: Array of closing prices
            period: ADX period (default 14)

        Returns:
            Current ADX value (0-100)
        """
        if len(closes) < period * 2:
            return 25.0  # Default to weak trend if not enough data

        # Calculate True Range
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]
        tr = np.maximum(
            highs - lows,
            np.maximum(
                np.abs(highs - prev_closes),
                np.abs(lows - prev_closes)
            )
        )

        # Calculate +DM and -DM
        prev_highs = np.roll(highs, 1)
        prev_lows = np.roll(lows, 1)
        prev_highs[0] = highs[0]
        prev_lows[0] = lows[0]

        plus_dm = np.where(
            (highs - prev_highs) > (prev_lows - lows),
            np.maximum(highs - prev_highs, 0),
            0
        )
        minus_dm = np.where(
            (prev_lows - lows) > (highs - prev_highs),
            np.maximum(prev_lows - lows, 0),
            0
        )

        # Smooth using Wilder's method
        def wilder_smooth(data: np.ndarray, period: int) -> np.ndarray:
            result = np.zeros(len(data))
            result[:period] = np.nan
            result[period - 1] = np.sum(data[:period])
            for i in range(period, len(data)):
                result[i] = result[i - 1] - (result[i - 1] / period) + data[i]
            return result

        atr_smooth = wilder_smooth(tr, period)
        plus_dm_smooth = wilder_smooth(plus_dm, period)
        minus_dm_smooth = wilder_smooth(minus_dm, period)

        # Calculate +DI and -DI
        plus_di = 100 * (plus_dm_smooth / atr_smooth)
        minus_di = 100 * (minus_dm_smooth / atr_smooth)

        # Calculate DX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)

        # Calculate ADX (smoothed DX)
        adx = wilder_smooth(dx[period - 1:], period)

        return round(float(adx[-1]), 2) if not np.isnan(adx[-1]) else 25.0

    @staticmethod
    def calculate_stochastic(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        k_period: int = 14,
        d_period: int = 3,
    ) -> StochasticResult:
        """
        Calculate Stochastic Oscillator.

        %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        %D = SMA of %K

        Interpretation:
            > 80: Overbought
            < 20: Oversold

        Args:
            highs: Array of high prices
            lows: Array of low prices
            closes: Array of closing prices
            k_period: %K period (default 14)
            d_period: %D smoothing period (default 3)

        Returns:
            StochasticResult with k, d, signal
        """
        if len(closes) < k_period:
            return StochasticResult(k=50.0, d=50.0, signal="NEUTRAL")

        # Calculate %K series
        k_values = np.zeros(len(closes))
        k_values[:k_period - 1] = np.nan

        for i in range(k_period - 1, len(closes)):
            highest_high = np.max(highs[i - k_period + 1:i + 1])
            lowest_low = np.min(lows[i - k_period + 1:i + 1])
            range_val = highest_high - lowest_low

            if range_val > 0:
                k_values[i] = ((closes[i] - lowest_low) / range_val) * 100
            else:
                k_values[i] = 50.0

        # Calculate %D (SMA of %K)
        valid_k = k_values[~np.isnan(k_values)]
        if len(valid_k) >= d_period:
            d_value = float(np.mean(valid_k[-d_period:]))
        else:
            d_value = float(valid_k[-1]) if len(valid_k) > 0 else 50.0

        k_value = float(k_values[-1])

        # Determine signal
        if k_value > 80:
            signal = "OVERBOUGHT"
        elif k_value < 20:
            signal = "OVERSOLD"
        else:
            signal = "NEUTRAL"

        return StochasticResult(
            k=round(k_value, 2),
            d=round(d_value, 2),
            signal=signal,
        )

    @classmethod
    def calculate_all(
        cls,
        candles: List[OHLCV],
        ema_periods: List[int] = None,
        sma_periods: List[int] = None,
        macd_params: Dict = None,
        rsi_period: int = 14,
        atr_period: int = 14,
        bollinger_params: Dict = None,
        adx_period: int = 14,
        stochastic_params: Dict = None,
        include_volume: bool = True,
    ) -> Optional[TAResult]:
        """
        Calculate all technical indicators from candle data.

        Args:
            candles: List of OHLCV candles (oldest to newest)
            ema_periods: List of EMA periods to calculate (default [9, 21, 50])
            sma_periods: List of SMA periods to calculate (default [20])
            macd_params: MACD parameters dict (fast, slow, signal)
            rsi_period: RSI period
            atr_period: ATR period
            bollinger_params: Bollinger Bands parameters dict (period, std_dev)
            adx_period: ADX period
            stochastic_params: Stochastic parameters dict (k_period, d_period)
            include_volume: Whether to include volume metrics

        Returns:
            TAResult with all indicators, or None if not enough data
        """
        if not candles or len(candles) < 2:
            return None

        if ema_periods is None:
            ema_periods = [9, 21, 50]

        if sma_periods is None:
            sma_periods = [20]

        if macd_params is None:
            macd_params = {"fast": 12, "slow": 26, "signal": 9}

        if bollinger_params is None:
            bollinger_params = {"period": 20, "std_dev": 2.0}

        if stochastic_params is None:
            stochastic_params = {"k_period": 14, "d_period": 3}

        # Convert candles to numpy arrays
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        volumes = np.array([c.volume for c in candles])

        # Calculate EMAs
        ema_results = {}
        for period in ema_periods:
            ema_value = cls.calculate_ema(closes, period)
            ema_results[f"ema_{period}"] = round(ema_value, 4)

        # Calculate SMAs
        sma_results = {}
        for period in sma_periods:
            sma_value = cls.calculate_sma(closes, period)
            sma_results[f"sma_{period}"] = round(sma_value, 4)

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

        # Calculate Bollinger Bands
        bollinger = cls.calculate_bollinger_bands(
            closes,
            period=bollinger_params.get("period", 20),
            std_dev=bollinger_params.get("std_dev", 2.0),
        )

        # Calculate ADX
        adx = cls.calculate_adx(highs, lows, closes, adx_period)

        # Calculate Stochastic
        stochastic = cls.calculate_stochastic(
            highs,
            lows,
            closes,
            k_period=stochastic_params.get("k_period", 14),
            d_period=stochastic_params.get("d_period", 3),
        )

        # Calculate Volume metrics
        current_volume = None
        volume_sma = None
        if include_volume and len(volumes) > 0:
            current_volume = float(volumes[-1])
            volume_sma = cls.calculate_sma(volumes, 20) if len(volumes) >= 20 else float(np.mean(volumes))

        return TAResult(
            ema=ema_results,
            sma=sma_results,
            macd=macd_result,
            rsi=rsi,
            atr=atr,
            bollinger=bollinger,
            adx=adx,
            stochastic=stochastic,
            volume=current_volume,
            volume_sma=round(volume_sma, 2) if volume_sma else None,
        )
