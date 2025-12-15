"""Base market data provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class Ticker:
    """Current market ticker data."""

    symbol: str
    mid: float
    bid: float
    ask: float
    spread_bps: float
    timestamp: datetime


@dataclass
class OHLCV:
    """Candlestick data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderBookLevel:
    """Single level in the order book."""

    price: float
    size: float


@dataclass
class OrderBook:
    """L2 order book data."""

    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: datetime


@dataclass
class FundingRate:
    """Perpetual funding rate data."""

    symbol: str
    rate: float
    predicted_rate: Optional[float]
    next_funding_time: Optional[datetime]
    timestamp: datetime


@dataclass
class OpenInterest:
    """Open interest data."""

    symbol: str
    oi_usd: float
    oi_contracts: Optional[float]
    change_24h_pct: Optional[float]
    timestamp: datetime


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get current ticker data.

        Args:
            symbol: Trading symbol

        Returns:
            Ticker data
        """
        pass

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[OHLCV]:
        """
        Get historical OHLCV data.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe (e.g., '15m', '1h', '4h')
            limit: Number of candles to fetch

        Returns:
            List of OHLCV candles (newest last)
        """
        pass

    @abstractmethod
    async def get_orderbook(self, symbol: str, depth: int = 10) -> OrderBook:
        """
        Get L2 order book.

        Args:
            symbol: Trading symbol
            depth: Number of levels per side

        Returns:
            Order book data
        """
        pass

    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """
        Get current funding rate.

        Args:
            symbol: Trading symbol

        Returns:
            Funding rate data
        """
        pass

    @abstractmethod
    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """
        Get open interest data.

        Args:
            symbol: Trading symbol

        Returns:
            Open interest data
        """
        pass

    async def health_check(self) -> bool:
        """
        Check provider connectivity.

        Returns:
            True if provider is healthy
        """
        try:
            # Try to get ticker for a common symbol
            await self.get_ticker("BTC")
            return True
        except Exception:
            return False
