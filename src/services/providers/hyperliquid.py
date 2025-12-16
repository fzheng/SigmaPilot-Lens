"""Hyperliquid market data provider."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.core.config import settings
from src.core.exceptions import ProviderError
from src.observability.logging import get_logger
from src.services.providers.base import (
    FundingRate,
    MarketDataProvider,
    OHLCV,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    Ticker,
)

logger = get_logger(__name__)


class HyperliquidProvider(MarketDataProvider):
    """
    Hyperliquid exchange data provider.

    Uses the Hyperliquid Info API:
    - POST https://api.hyperliquid.xyz/info
    - All requests use JSON body with "type" field
    """

    # Timeframe mapping from standard format to Hyperliquid format
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    def __init__(self):
        self.base_url = settings.HYPERLIQUID_BASE_URL
        self.timeout = settings.PROVIDER_TIMEOUT_MS / 1000
        self._client: httpx.AsyncClient | None = None
        # Cache for asset metadata (refreshed periodically)
        self._asset_ctxs_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 5  # Refresh metadata every 5 seconds

    @property
    def name(self) -> str:
        return "hyperliquid"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post(self, data: dict) -> Any:
        """Make POST request to Hyperliquid Info API."""
        client = await self._get_client()
        try:
            response = await client.post("/info", json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Hyperliquid API error: {e.response.status_code} - {e.response.text}")
            raise ProviderError(
                self.name, f"HTTP {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Hyperliquid request failed: {str(e)}")
            raise ProviderError(self.name, f"Request failed: {str(e)}")

    async def _get_asset_contexts(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get cached asset contexts (metadata + funding + OI).

        Returns dict mapping symbol -> asset context data.
        """
        now = datetime.now(timezone.utc)

        # Check if cache is valid
        if (
            not force_refresh
            and self._asset_ctxs_cache is not None
            and self._cache_timestamp is not None
            and (now - self._cache_timestamp).total_seconds() < self._cache_ttl_seconds
        ):
            return self._asset_ctxs_cache

        # Fetch fresh data
        data = await self._post({"type": "metaAndAssetCtxs"})

        # Response is [meta, [assetCtx1, assetCtx2, ...]]
        # meta contains universe array with asset names
        meta = data[0]
        asset_ctxs = data[1]

        # Build lookup dict by symbol
        result = {}
        universe = meta.get("universe", [])
        for i, asset_info in enumerate(universe):
            symbol = asset_info.get("name", "")
            if i < len(asset_ctxs):
                result[symbol] = asset_ctxs[i]
                result[symbol]["_meta"] = asset_info

        self._asset_ctxs_cache = result
        self._cache_timestamp = now

        return result

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol to Hyperliquid format.

        Hyperliquid uses: BTC, ETH, SOL (no -PERP suffix)
        We accept: BTC, BTC-PERP, BTCPERP, BTC/USD
        """
        # Remove common suffixes (order matters - check longer suffixes first)
        normalized = symbol.upper()
        for suffix in ["-PERP", "PERP", "/USDT", "/USD", "-USD", "USD"]:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break  # Only remove one suffix
        return normalized

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current ticker data from Hyperliquid."""
        normalized = self._normalize_symbol(symbol)

        # Get mid price from allMids
        mids_data = await self._post({"type": "allMids"})

        mid = float(mids_data.get(normalized, 0))
        if mid == 0:
            raise ProviderError(self.name, f"Symbol not found: {normalized}")

        # Get order book for best bid/ask
        book = await self.get_orderbook(symbol, depth=1)

        bid = book.bids[0].price if book.bids else mid
        ask = book.asks[0].price if book.asks else mid
        spread_bps = ((ask - bid) / mid) * 10000 if mid > 0 else 0

        return Ticker(
            symbol=normalized,
            mid=mid,
            bid=bid,
            ask=ask,
            spread_bps=round(spread_bps, 2),
            timestamp=datetime.now(timezone.utc),
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[OHLCV]:
        """
        Get historical OHLCV data from Hyperliquid.

        Args:
            symbol: Trading symbol (e.g., BTC, ETH)
            timeframe: Candle interval (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles to fetch (max 5000)

        Returns:
            List of OHLCV candles (oldest to newest)
        """
        normalized = self._normalize_symbol(symbol)

        # Map timeframe to Hyperliquid format
        interval = self.TIMEFRAME_MAP.get(timeframe, "1h")

        # Calculate time range
        # Hyperliquid returns up to 5000 candles
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Calculate startTime based on interval and limit
        interval_ms = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }
        candle_ms = interval_ms.get(interval, 3_600_000)
        start_ms = now_ms - (candle_ms * min(limit, 5000))

        data = await self._post(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": normalized,
                    "interval": interval,
                    "startTime": start_ms,
                    "endTime": now_ms,
                },
            },
        )

        if not data:
            logger.warning(f"No candle data returned for {normalized} {interval}")
            return []

        candles = []
        for c in data[-limit:]:
            candles.append(
                OHLCV(
                    timestamp=datetime.fromtimestamp(c["t"] / 1000, tz=timezone.utc),
                    open=float(c["o"]),
                    high=float(c["h"]),
                    low=float(c["l"]),
                    close=float(c["c"]),
                    volume=float(c["v"]),
                )
            )
        return candles

    async def get_orderbook(self, symbol: str, depth: int = 10) -> OrderBook:
        """
        Get L2 order book from Hyperliquid.

        Args:
            symbol: Trading symbol
            depth: Number of levels per side (max 20)

        Returns:
            OrderBook with bids and asks
        """
        normalized = self._normalize_symbol(symbol)

        data = await self._post({"type": "l2Book", "coin": normalized})

        # Response: {"coin": "BTC", "time": 123..., "levels": [[bids], [asks]]}
        levels = data.get("levels", [[], []])
        timestamp_ms = data.get("time", int(datetime.now(timezone.utc).timestamp() * 1000))

        bids = [
            OrderBookLevel(price=float(level["px"]), size=float(level["sz"]))
            for level in (levels[0] if len(levels) > 0 else [])[:depth]
        ]
        asks = [
            OrderBookLevel(price=float(level["px"]), size=float(level["sz"]))
            for level in (levels[1] if len(levels) > 1 else [])[:depth]
        ]

        return OrderBook(
            symbol=normalized,
            bids=bids,
            asks=asks,
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
        )

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """
        Get current funding rate from Hyperliquid.

        Hyperliquid settles funding every hour.
        """
        normalized = self._normalize_symbol(symbol)
        asset_ctxs = await self._get_asset_contexts()

        if normalized not in asset_ctxs:
            raise ProviderError(self.name, f"Symbol not found: {normalized}")

        ctx = asset_ctxs[normalized]

        # funding is the current hourly funding rate
        rate = float(ctx.get("funding", 0))
        # premium can indicate predicted funding direction
        predicted = float(ctx.get("premium", 0)) if ctx.get("premium") else None

        # Calculate next funding time (top of the hour)
        now = datetime.now(timezone.utc)
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        if next_hour <= now:
            from datetime import timedelta
            next_hour = next_hour + timedelta(hours=1)

        return FundingRate(
            symbol=normalized,
            rate=rate,
            predicted_rate=predicted,
            next_funding_time=next_hour,
            timestamp=now,
        )

    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """
        Get open interest data from Hyperliquid.

        Returns OI in USD notional value.
        """
        normalized = self._normalize_symbol(symbol)
        asset_ctxs = await self._get_asset_contexts()

        if normalized not in asset_ctxs:
            raise ProviderError(self.name, f"Symbol not found: {normalized}")

        ctx = asset_ctxs[normalized]

        # openInterest is in contracts, multiply by mark price for USD
        oi_contracts = float(ctx.get("openInterest", 0))
        mark_price = float(ctx.get("markPx", 0))
        oi_usd = oi_contracts * mark_price

        return OpenInterest(
            symbol=normalized,
            oi_usd=oi_usd,
            oi_contracts=oi_contracts,
            change_24h_pct=None,  # Hyperliquid doesn't provide this directly
            timestamp=datetime.now(timezone.utc),
        )

    async def get_mark_price(self, symbol: str) -> float:
        """Get mark price for a symbol."""
        normalized = self._normalize_symbol(symbol)
        asset_ctxs = await self._get_asset_contexts()

        if normalized not in asset_ctxs:
            raise ProviderError(self.name, f"Symbol not found: {normalized}")

        return float(asset_ctxs[normalized].get("markPx", 0))

    async def get_24h_volume(self, symbol: str) -> float:
        """Get 24h notional volume for a symbol."""
        normalized = self._normalize_symbol(symbol)
        asset_ctxs = await self._get_asset_contexts()

        if normalized not in asset_ctxs:
            raise ProviderError(self.name, f"Symbol not found: {normalized}")

        return float(asset_ctxs[normalized].get("dayNtlVlm", 0))
