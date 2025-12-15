"""Hyperliquid market data provider."""

from datetime import datetime, timezone
from typing import List

import httpx

from src.core.config import settings
from src.core.exceptions import ProviderError
from src.services.providers.base import (
    FundingRate,
    MarketDataProvider,
    OHLCV,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    Ticker,
)


class HyperliquidProvider(MarketDataProvider):
    """Hyperliquid exchange data provider."""

    def __init__(self):
        self.base_url = settings.HYPERLIQUID_BASE_URL
        self.timeout = settings.PROVIDER_TIMEOUT_MS / 1000
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "hyperliquid"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post(self, endpoint: str, data: dict) -> dict:
        """Make POST request to Hyperliquid API."""
        client = await self._get_client()
        try:
            response = await client.post(endpoint, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                self.name, f"HTTP {e.response.status_code}: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise ProviderError(self.name, f"Request failed: {str(e)}")

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current ticker data from Hyperliquid."""
        # TODO: Implement actual Hyperliquid API call
        # This is a placeholder implementation
        data = await self._post("/info", {"type": "allMids"})

        # Parse response and find symbol
        # Hyperliquid uses different symbol format, may need mapping
        mid = float(data.get(symbol, 0))

        if mid == 0:
            raise ProviderError(self.name, f"Symbol not found: {symbol}")

        # Get order book for bid/ask
        book = await self.get_orderbook(symbol, depth=1)

        bid = book.bids[0].price if book.bids else mid
        ask = book.asks[0].price if book.asks else mid
        spread_bps = ((ask - bid) / mid) * 10000 if mid > 0 else 0

        return Ticker(
            symbol=symbol,
            mid=mid,
            bid=bid,
            ask=ask,
            spread_bps=spread_bps,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[OHLCV]:
        """Get historical OHLCV data from Hyperliquid."""
        # TODO: Implement actual Hyperliquid API call
        # Map timeframe to Hyperliquid format
        interval_map = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        interval = interval_map.get(timeframe, 3600)

        data = await self._post(
            "/info",
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": str(interval),
                    "startTime": 0,  # Will be calculated based on limit
                    "endTime": int(datetime.now(timezone.utc).timestamp() * 1000),
                },
            },
        )

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
        """Get L2 order book from Hyperliquid."""
        # TODO: Implement actual Hyperliquid API call
        data = await self._post("/info", {"type": "l2Book", "coin": symbol})

        bids = [
            OrderBookLevel(price=float(level["px"]), size=float(level["sz"]))
            for level in data.get("levels", [[]])[0][:depth]
        ]
        asks = [
            OrderBookLevel(price=float(level["px"]), size=float(level["sz"]))
            for level in data.get("levels", [[], []])[1][:depth]
        ]

        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate from Hyperliquid."""
        # TODO: Implement actual Hyperliquid API call
        data = await self._post("/info", {"type": "metaAndAssetCtxs"})

        # Find symbol in response
        rate = 0.0
        predicted = None

        for asset in data[1]:
            if asset.get("name") == symbol:
                rate = float(asset.get("funding", 0))
                predicted = float(asset.get("premium", 0))
                break

        return FundingRate(
            symbol=symbol,
            rate=rate,
            predicted_rate=predicted,
            next_funding_time=None,  # Calculate based on schedule
            timestamp=datetime.now(timezone.utc),
        )

    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """Get open interest data from Hyperliquid."""
        # TODO: Implement actual Hyperliquid API call
        data = await self._post("/info", {"type": "metaAndAssetCtxs"})

        oi_usd = 0.0
        for asset in data[1]:
            if asset.get("name") == symbol:
                oi_usd = float(asset.get("openInterest", 0))
                break

        return OpenInterest(
            symbol=symbol,
            oi_usd=oi_usd,
            oi_contracts=None,
            change_24h_pct=None,  # Would need historical data
            timestamp=datetime.now(timezone.utc),
        )
