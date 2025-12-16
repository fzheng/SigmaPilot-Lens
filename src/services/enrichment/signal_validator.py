"""Signal validation before enrichment.

This module provides early signal validation to reject signals that should not
proceed to the expensive enrichment and AI evaluation stages.

Key features:
    - Price drift validation: Rejects signals where entry price differs >2% from current
    - Signal age validation: Rejects signals older than 5 minutes
    - Optimized ordering: Checks age first (no API call) before price (requires API)

Usage:
    validator = SignalValidator()
    try:
        result = await validator.validate(signal, raise_on_invalid=True)
    except SignalRejectedError as e:
        # Handle rejection
        pass

Contract:
    - validate() returns ValidationResult with validation details
    - If raise_on_invalid=True, raises SignalRejectedError for invalid signals
    - If raise_on_invalid=False, returns result with valid=False and rejection_reason
    - ProviderError is propagated if price fetch fails
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.config import settings
from src.core.exceptions import ProviderError, SignalRejectedError
from src.observability.logging import get_logger
from src.services.providers.hyperliquid import HyperliquidProvider

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """
    Result of signal pre-validation.

    Attributes:
        valid: Whether the signal passed validation
        current_price: Current market mid price (None if age check failed first)
        entry_price: Signal's entry price
        drift_bps: Price drift in basis points (100 bps = 1%)
        signal_age_seconds: Age of signal at validation time
        rejection_reason: Human-readable rejection reason (None if valid)
    """

    valid: bool
    current_price: Optional[float]
    entry_price: float
    drift_bps: float
    signal_age_seconds: float
    rejection_reason: Optional[str] = None


class SignalValidator:
    """
    Validates signals before expensive enrichment.

    This validator performs quick checks to reject signals early, saving:
    - API calls for market data enrichment (~1-2 seconds)
    - AI evaluation costs (~$0.01-0.10 per signal)

    Rejection reasons:
        1. Price drift > 2%: Entry price differs significantly from current market
           - Could indicate invalid signal data
           - Could indicate high volatility / slippage risk
           - Protects against trading in volatile conditions
        2. Signal age > 5 minutes: Signal is too old to act on
           - Market conditions may have changed
           - Prevents acting on stale information

    The validator checks age before price to avoid unnecessary API calls
    for signals that will be rejected anyway.

    Class Invariants:
        - max_drift_bps must be positive
        - max_signal_age must be positive
        - provider must be initialized before validate() is called
    """

    # Default thresholds (can be overridden via settings)
    MAX_PRICE_DRIFT_BPS = 200  # 2% max drift (200 basis points)
    MAX_SIGNAL_AGE_SECONDS = 300  # 5 minutes max signal age

    def __init__(self, provider: Optional[HyperliquidProvider] = None):
        """
        Initialize validator.

        Args:
            provider: Market data provider (defaults to HyperliquidProvider)
        """
        self.provider = provider or HyperliquidProvider()

        # Allow override from settings
        self.max_drift_bps = getattr(settings, "MAX_PRICE_DRIFT_BPS", self.MAX_PRICE_DRIFT_BPS)
        self.max_signal_age = getattr(settings, "MAX_SIGNAL_AGE_SECONDS", self.MAX_SIGNAL_AGE_SECONDS)

    async def close(self):
        """Close the provider connection."""
        await self.provider.close()

    async def validate(
        self,
        signal: Dict[str, Any],
        raise_on_invalid: bool = True,
    ) -> ValidationResult:
        """
        Validate a signal before enrichment.

        Performs quick price check and signal age validation.

        Args:
            signal: Raw signal data with symbol, entry_price, ts_utc
            raise_on_invalid: If True, raises SignalRejectedError on invalid signals

        Returns:
            ValidationResult with validation details

        Raises:
            SignalRejectedError: If signal is invalid and raise_on_invalid=True
            ProviderError: If price fetch fails
        """
        symbol = signal.get("symbol", "")
        entry_price = float(signal.get("entry_price", 0))
        signal_ts_str = signal.get("ts_utc", "")

        now = datetime.now(timezone.utc)

        # Calculate signal age
        signal_age_seconds = 0.0
        if signal_ts_str:
            try:
                signal_ts = datetime.fromisoformat(signal_ts_str.replace("Z", "+00:00"))
                signal_age_seconds = (now - signal_ts).total_seconds()
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse signal timestamp: {signal_ts_str}, error: {e}")

        # Check signal age first (no API call needed)
        if signal_age_seconds > self.max_signal_age:
            result = ValidationResult(
                valid=False,
                current_price=None,
                entry_price=entry_price,
                drift_bps=0,
                signal_age_seconds=signal_age_seconds,
                rejection_reason=f"Signal too old: {signal_age_seconds:.0f}s (max: {self.max_signal_age}s)",
            )
            if raise_on_invalid:
                raise SignalRejectedError(
                    reason=result.rejection_reason,
                    symbol=symbol,
                    details={
                        "signal_age_seconds": signal_age_seconds,
                        "max_signal_age_seconds": self.max_signal_age,
                    },
                )
            return result

        # Fetch current price (quick API call)
        try:
            ticker = await self.provider.get_ticker(symbol)
            current_price = ticker.mid
        except ProviderError as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            raise

        # Calculate drift
        drift_bps = 0.0
        if entry_price > 0 and current_price > 0:
            drift_bps = abs((current_price - entry_price) / entry_price) * 10000

        # Check drift threshold
        if drift_bps > self.max_drift_bps:
            drift_pct = drift_bps / 100
            result = ValidationResult(
                valid=False,
                current_price=current_price,
                entry_price=entry_price,
                drift_bps=drift_bps,
                signal_age_seconds=signal_age_seconds,
                rejection_reason=f"Price drift too high: {drift_pct:.2f}% (max: {self.max_drift_bps / 100:.1f}%)",
            )

            logger.warning(
                f"Signal rejected for {symbol}: entry={entry_price}, current={current_price}, "
                f"drift={drift_pct:.2f}%"
            )

            if raise_on_invalid:
                raise SignalRejectedError(
                    reason=result.rejection_reason,
                    symbol=symbol,
                    details={
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "drift_bps": round(drift_bps, 2),
                        "max_drift_bps": self.max_drift_bps,
                    },
                )
            return result

        # Signal is valid
        logger.info(
            f"Signal validated for {symbol}: entry={entry_price}, current={current_price}, "
            f"drift={drift_bps:.1f}bps, age={signal_age_seconds:.0f}s"
        )

        return ValidationResult(
            valid=True,
            current_price=current_price,
            entry_price=entry_price,
            drift_bps=drift_bps,
            signal_age_seconds=signal_age_seconds,
        )
