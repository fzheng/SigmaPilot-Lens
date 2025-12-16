"""Enrichment service that fetches market data and computes TA indicators."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

from src.core.config import settings
from src.core.exceptions import ProviderError
from src.observability.logging import get_logger
from src.services.enrichment.ta_calculator import TACalculator
from src.services.providers.base import OHLCV
from src.services.providers.hyperliquid import HyperliquidProvider

logger = get_logger(__name__)


@dataclass
class QualityFlags:
    """Data quality flags for enrichment."""

    stale: List[str]  # Data sources that are stale
    missing: List[str]  # Missing data points
    out_of_range: List[str]  # Values outside expected range
    provider_errors: List[str]  # Provider fetch errors


@dataclass
class EnrichmentResult:
    """Result of enrichment process."""

    success: bool
    market_data: Optional[Dict[str, Any]]
    ta_data: Optional[Dict[str, Any]]
    derivs_data: Optional[Dict[str, Any]]
    levels_data: Optional[Dict[str, Any]]
    constraints: Dict[str, Any]
    data_timestamps: Dict[str, str]
    quality_flags: QualityFlags
    enriched_payload: Dict[str, Any]
    signal_age_seconds: float = 0.0  # Age of signal at enrichment time
    error: Optional[str] = None


class EnrichmentService:
    """
    Service for enriching trading signals with market data.

    Fetches data from Hyperliquid and computes technical indicators
    based on the configured feature profile.
    """

    # Default constraints (can be overridden by profile)
    DEFAULT_CONSTRAINTS = {
        "max_position_size_pct": 20,
        "min_hold_minutes": 30,
        "max_trades_per_hour": 4,
        "max_leverage": 10,
    }

    # Staleness thresholds in seconds
    STALENESS_THRESHOLDS = {
        "ticker": 10,  # 10 seconds
        "candles": 300,  # 5 minutes
        "orderbook": 5,  # 5 seconds
        "funding": 60,  # 1 minute
    }

    def __init__(self, provider: Optional[HyperliquidProvider] = None):
        """
        Initialize enrichment service.

        Args:
            provider: Market data provider (defaults to HyperliquidProvider)
        """
        self.provider = provider or HyperliquidProvider()
        self._profile_config: Optional[Dict] = None

    async def close(self):
        """Close the provider connection."""
        await self.provider.close()

    def _load_profile_config(self, profile_name: str) -> Dict:
        """Load feature profile configuration."""
        if self._profile_config is not None:
            return self._profile_config

        try:
            with open("config/feature_profiles.yaml", "r") as f:
                profiles = yaml.safe_load(f)

            config = profiles.get(profile_name, {})

            # Handle profile inheritance (extends)
            if "extends" in config:
                parent = profiles.get(config["extends"], {})
                # Merge parent into config (config overrides)
                merged = {**parent, **config}
                # Merge nested dicts
                for key in ["indicators", "market_data"]:
                    if key in parent and key in config:
                        if isinstance(parent[key], list) and isinstance(config[key], list):
                            merged[key] = parent[key] + config[key]
                config = merged

            self._profile_config = config
            return config

        except Exception as e:
            logger.warning(f"Failed to load profile config: {e}, using defaults")
            return {}

    def _check_staleness(
        self,
        data_timestamps: Dict[str, str],
        now: datetime,
        quality_flags: QualityFlags,
    ) -> None:
        """
        Check data freshness against staleness thresholds.

        Adds stale data sources to quality_flags.stale.
        """
        for ts_key, ts_value in data_timestamps.items():
            try:
                # Parse timestamp
                if isinstance(ts_value, str):
                    ts = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
                else:
                    ts = ts_value

                # Determine threshold based on data type
                age_seconds = (now - ts).total_seconds()

                if "candles" in ts_key:
                    threshold = self.STALENESS_THRESHOLDS["candles"]
                elif "funding" in ts_key:
                    threshold = self.STALENESS_THRESHOLDS["funding"]
                elif "mid" in ts_key or "ticker" in ts_key:
                    threshold = self.STALENESS_THRESHOLDS["ticker"]
                else:
                    threshold = self.STALENESS_THRESHOLDS.get("orderbook", 10)

                if age_seconds > threshold:
                    quality_flags.stale.append(f"{ts_key}: {int(age_seconds)}s old (threshold: {threshold}s)")
                    logger.warning(f"Stale data detected: {ts_key} is {age_seconds:.1f}s old")

            except Exception as e:
                logger.warning(f"Failed to check staleness for {ts_key}: {e}")

    def _validate_market_data(
        self,
        market_data: Optional[Dict[str, Any]],
        quality_flags: QualityFlags,
    ) -> None:
        """
        Validate market data values are within expected ranges.

        Adds out-of-range values to quality_flags.out_of_range.
        """
        if not market_data:
            return

        # Check spread is reasonable (< 1%)
        spread_bps = market_data.get("spread_bps", 0)
        if spread_bps > 100:  # 1% spread
            quality_flags.out_of_range.append(f"spread_bps: {spread_bps} (>100 bps)")

        # Check bid/ask sanity
        bid = market_data.get("bid", 0)
        ask = market_data.get("ask", 0)
        mid = market_data.get("mid_price", 0)

        if bid > 0 and ask > 0:
            if bid > ask:
                quality_flags.out_of_range.append(f"bid ({bid}) > ask ({ask})")
            if mid > 0 and (mid < bid * 0.99 or mid > ask * 1.01):
                quality_flags.out_of_range.append(f"mid ({mid}) outside bid/ask")

    def _validate_ta_data(
        self,
        ta_data: Optional[Dict[str, Any]],
        quality_flags: QualityFlags,
    ) -> None:
        """
        Validate technical analysis data is within expected ranges.

        Adds out-of-range values to quality_flags.out_of_range.
        """
        if not ta_data or "timeframes" not in ta_data:
            return

        for tf, indicators in ta_data.get("timeframes", {}).items():
            # RSI should be 0-100
            rsi = indicators.get("rsi", 50)
            if rsi < 0 or rsi > 100:
                quality_flags.out_of_range.append(f"{tf}_rsi: {rsi} (should be 0-100)")

            # ATR should be positive
            atr = indicators.get("atr", 0)
            if atr < 0:
                quality_flags.out_of_range.append(f"{tf}_atr: {atr} (should be positive)")

    async def enrich(
        self,
        event_id: str,
        signal: Dict[str, Any],
        profile: str = None,
    ) -> EnrichmentResult:
        """
        Enrich a trading signal with market data and technical indicators.

        Args:
            event_id: Unique event identifier
            signal: Raw signal data
            profile: Feature profile name (defaults to settings.FEATURE_PROFILE)

        Returns:
            EnrichmentResult with all enriched data
        """
        profile = profile or settings.FEATURE_PROFILE
        symbol = signal.get("symbol", "BTC")
        entry_price = float(signal.get("entry_price", 0))
        signal_ts_str = signal.get("ts_utc", "")

        now = datetime.now(timezone.utc)
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])
        data_timestamps: Dict[str, str] = {}

        # Calculate signal age
        signal_age_seconds = 0.0
        if signal_ts_str:
            try:
                signal_ts = datetime.fromisoformat(signal_ts_str.replace("Z", "+00:00"))
                signal_age_seconds = (now - signal_ts).total_seconds()
                data_timestamps["signal_ts"] = signal_ts_str
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse signal timestamp: {signal_ts_str}, error: {e}")

        # Load profile config
        config = self._load_profile_config(profile)
        timeframes = config.get("timeframes", ["1h"])
        requires_derivs = config.get("requires_derivs", False)

        # Fetch market data
        market_data = await self._fetch_market_data(symbol, entry_price, quality_flags, data_timestamps)

        # Fetch and compute TA for each timeframe
        ta_data = await self._compute_ta(symbol, timeframes, config, quality_flags, data_timestamps)

        # Fetch derivatives data if required
        derivs_data = None
        if requires_derivs:
            derivs_data = await self._fetch_derivs_data(symbol, quality_flags, data_timestamps)

        # Get constraints from profile or defaults
        constraints = config.get("constraints", self.DEFAULT_CONSTRAINTS)

        # Validate data quality
        self._check_staleness(data_timestamps, now, quality_flags)
        self._validate_market_data(market_data, quality_flags)
        self._validate_ta_data(ta_data, quality_flags)

        # Build enriched payload for AI evaluation
        enriched_payload = self._build_payload(
            event_id=event_id,
            signal=signal,
            market_data=market_data,
            ta_data=ta_data,
            derivs_data=derivs_data,
            constraints=constraints,
        )

        # Success if no provider errors and we have market data
        # Stale/out-of-range warnings don't prevent success
        success = len(quality_flags.provider_errors) == 0 and market_data is not None

        return EnrichmentResult(
            success=success,
            market_data=market_data,
            ta_data=ta_data,
            derivs_data=derivs_data,
            levels_data=None,  # TODO: Implement S/R levels
            constraints=constraints,
            data_timestamps=data_timestamps,
            quality_flags=quality_flags,
            enriched_payload=enriched_payload,
            signal_age_seconds=signal_age_seconds,
        )

    async def _fetch_market_data(
        self,
        symbol: str,
        entry_price: float,
        quality_flags: QualityFlags,
        data_timestamps: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Fetch current market data (ticker + orderbook)."""
        try:
            ticker = await self.provider.get_ticker(symbol)
            data_timestamps["mid_ts"] = ticker.timestamp.isoformat()

            # Calculate price drift from entry
            price_drift_bps = 0
            if entry_price > 0:
                price_drift_bps = ((ticker.mid - entry_price) / entry_price) * 10000

            market_data = {
                "mid_price": ticker.mid,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "spread_bps": ticker.spread_bps,
                "price_drift_from_entry_bps": round(price_drift_bps, 2),
            }

            # Fetch 24h volume
            try:
                volume = await self.provider.get_24h_volume(symbol)
                market_data["volume_24h"] = volume
            except Exception:
                quality_flags.missing.append("volume_24h")

            return market_data

        except ProviderError as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e}")
            quality_flags.provider_errors.append(f"ticker: {str(e)}")
            return None

    async def _compute_ta(
        self,
        symbol: str,
        timeframes: List[str],
        config: Dict,
        quality_flags: QualityFlags,
        data_timestamps: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Fetch candles and compute TA indicators for each timeframe."""
        ta_data: Dict[str, Any] = {"timeframes": {}}

        # Get indicator config
        indicators = config.get("indicators", [])
        ema_periods = [9, 21, 50]  # Default
        macd_params = {"fast": 12, "slow": 26, "signal": 9}  # Default
        rsi_period = 14
        atr_period = 14

        for ind in indicators:
            if ind["name"] == "ema":
                ema_periods = ind.get("params", {}).get("periods", ema_periods)
            elif ind["name"] == "macd":
                params = ind.get("params", {})
                macd_params = {
                    "fast": params.get("fast", 12),
                    "slow": params.get("slow", 26),
                    "signal": params.get("signal", 9),
                }
            elif ind["name"] == "rsi":
                rsi_period = ind.get("params", {}).get("period", 14)
            elif ind["name"] == "atr":
                atr_period = ind.get("params", {}).get("period", 14)

        # Need enough candles for the longest period
        max_period = max(max(ema_periods), macd_params["slow"] + macd_params["signal"], rsi_period, atr_period)
        candle_limit = max_period + 50  # Extra buffer

        for tf in timeframes:
            try:
                candles = await self.provider.get_ohlcv(symbol, tf, limit=candle_limit)

                if candles:
                    data_timestamps[f"candles_{tf}_ts"] = candles[-1].timestamp.isoformat()

                    # Compute TA
                    ta_result = TACalculator.calculate_all(
                        candles=candles,
                        ema_periods=ema_periods,
                        macd_params=macd_params,
                        rsi_period=rsi_period,
                        atr_period=atr_period,
                    )

                    if ta_result:
                        ta_data["timeframes"][tf] = {
                            "ema": ta_result.ema,
                            "macd": {
                                "macd_line": ta_result.macd.macd_line,
                                "signal_line": ta_result.macd.signal_line,
                                "histogram": ta_result.macd.histogram,
                            },
                            "rsi": ta_result.rsi,
                            "atr": ta_result.atr,
                        }
                else:
                    quality_flags.missing.append(f"candles_{tf}")

            except ProviderError as e:
                logger.error(f"Failed to fetch {tf} candles for {symbol}: {e}")
                quality_flags.provider_errors.append(f"candles_{tf}: {str(e)}")

        return ta_data if ta_data["timeframes"] else None

    async def _fetch_derivs_data(
        self,
        symbol: str,
        quality_flags: QualityFlags,
        data_timestamps: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Fetch perpetual derivatives data (funding, OI, mark price)."""
        derivs_data: Dict[str, Any] = {}

        try:
            # Funding rate
            funding = await self.provider.get_funding_rate(symbol)
            data_timestamps["funding_ts"] = funding.timestamp.isoformat()
            derivs_data["funding_rate"] = funding.rate
            derivs_data["predicted_funding"] = funding.predicted_rate
            derivs_data["funding_interval_h"] = 1  # Hyperliquid uses 1h funding

            # Open interest
            oi = await self.provider.get_open_interest(symbol)
            derivs_data["open_interest"] = oi.oi_usd
            derivs_data["oi_contracts"] = oi.oi_contracts

            # Mark price
            mark_price = await self.provider.get_mark_price(symbol)
            derivs_data["mark_price"] = mark_price

        except ProviderError as e:
            logger.error(f"Failed to fetch derivs data for {symbol}: {e}")
            quality_flags.provider_errors.append(f"derivs: {str(e)}")
            return None

        return derivs_data

    def _build_payload(
        self,
        event_id: str,
        signal: Dict[str, Any],
        market_data: Optional[Dict],
        ta_data: Optional[Dict],
        derivs_data: Optional[Dict],
        constraints: Dict,
    ) -> Dict[str, Any]:
        """Build compact enriched payload for AI evaluation."""
        return {
            "event_id": event_id,
            "symbol": signal.get("symbol", ""),
            "signal_direction": signal.get("signal_direction", ""),
            "entry_price": float(signal.get("entry_price", 0)),
            "size": float(signal.get("size", 0)),
            "ts_utc": signal.get("ts_utc", ""),
            "source": signal.get("source", ""),
            "event_type": signal.get("event_type", ""),
            "market": market_data or {},
            "ta": ta_data or {},
            "derivs": derivs_data or {},
            "constraints": constraints,
        }
