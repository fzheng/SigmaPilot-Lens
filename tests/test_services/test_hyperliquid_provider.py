"""Tests for the Hyperliquid provider."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


@pytest.fixture
def mock_all_mids_response():
    """Mock response for allMids endpoint."""
    return {"BTC": "50000.0", "ETH": "3000.0", "SOL": "100.0"}


@pytest.fixture
def mock_l2_book_response():
    """Mock response for l2Book endpoint."""
    return {
        "coin": "BTC",
        "time": 1700000000000,
        "levels": [
            [{"px": "49990.0", "sz": "10.5", "n": 5}],  # bids
            [{"px": "50010.0", "sz": "8.2", "n": 3}],  # asks
        ],
    }


@pytest.fixture
def mock_candle_response():
    """Mock response for candleSnapshot endpoint."""
    base_ts = 1700000000000
    return [
        {
            "t": base_ts + i * 3600000,
            "T": base_ts + i * 3600000 + 3600000,
            "o": str(50000 + i * 10),
            "h": str(50020 + i * 10),
            "l": str(49980 + i * 10),
            "c": str(50010 + i * 10),
            "v": "100.5",
            "n": 50,
        }
        for i in range(100)
    ]


@pytest.fixture
def mock_meta_and_asset_ctxs_response():
    """Mock response for metaAndAssetCtxs endpoint."""
    return [
        {
            "universe": [
                {"name": "BTC", "szDecimals": 4, "maxLeverage": 50},
                {"name": "ETH", "szDecimals": 4, "maxLeverage": 50},
            ]
        },
        [
            {
                "funding": "0.0001",
                "openInterest": "10000.0",
                "markPx": "50005.0",
                "premium": "0.00015",
                "dayNtlVlm": "1000000000.0",
            },
            {
                "funding": "0.00008",
                "openInterest": "5000.0",
                "markPx": "3001.0",
                "premium": "0.0001",
                "dayNtlVlm": "500000000.0",
            },
        ],
    ]


@pytest.mark.unit
class TestHyperliquidProvider:
    """Test Hyperliquid provider methods."""

    def test_normalize_symbol(self):
        """Test symbol normalization."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        assert provider._normalize_symbol("BTC") == "BTC"
        assert provider._normalize_symbol("btc") == "BTC"
        assert provider._normalize_symbol("BTC-PERP") == "BTC"
        assert provider._normalize_symbol("BTCPERP") == "BTC"
        assert provider._normalize_symbol("BTC/USD") == "BTC"

    @pytest.mark.asyncio
    async def test_get_ticker(self, mock_all_mids_response, mock_l2_book_response):
        """Test get_ticker fetches and parses correctly."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        # Mock the _post method
        async def mock_post(data):
            if data.get("type") == "allMids":
                return mock_all_mids_response
            elif data.get("type") == "l2Book":
                return mock_l2_book_response
            return {}

        provider._post = mock_post

        ticker = await provider.get_ticker("BTC")

        assert ticker.symbol == "BTC"
        assert ticker.mid == 50000.0
        assert ticker.bid == 49990.0
        assert ticker.ask == 50010.0
        assert ticker.spread_bps > 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_ticker_symbol_not_found(self, mock_all_mids_response):
        """Test get_ticker raises error for unknown symbol."""
        from src.services.providers.hyperliquid import HyperliquidProvider
        from src.core.exceptions import ProviderError

        provider = HyperliquidProvider()

        async def mock_post(data):
            return mock_all_mids_response

        provider._post = mock_post

        with pytest.raises(ProviderError) as exc_info:
            await provider.get_ticker("UNKNOWN")

        assert "not found" in str(exc_info.value)
        await provider.close()

    @pytest.mark.asyncio
    async def test_get_orderbook(self, mock_l2_book_response):
        """Test get_orderbook fetches and parses correctly."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        async def mock_post(data):
            return mock_l2_book_response

        provider._post = mock_post

        book = await provider.get_orderbook("BTC", depth=5)

        assert book.symbol == "BTC"
        assert len(book.bids) > 0
        assert len(book.asks) > 0
        assert book.bids[0].price == 49990.0
        assert book.asks[0].price == 50010.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_ohlcv(self, mock_candle_response):
        """Test get_ohlcv fetches and parses correctly."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        async def mock_post(data):
            return mock_candle_response

        provider._post = mock_post

        candles = await provider.get_ohlcv("BTC", "1h", limit=50)

        assert len(candles) == 50
        assert candles[0].close > 0
        assert candles[0].timestamp is not None

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_funding_rate(self, mock_meta_and_asset_ctxs_response):
        """Test get_funding_rate fetches and parses correctly."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        async def mock_post(data):
            return mock_meta_and_asset_ctxs_response

        provider._post = mock_post

        funding = await provider.get_funding_rate("BTC")

        assert funding.symbol == "BTC"
        assert funding.rate == 0.0001
        assert funding.predicted_rate == 0.00015
        assert funding.next_funding_time is not None

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_open_interest(self, mock_meta_and_asset_ctxs_response):
        """Test get_open_interest fetches and parses correctly."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()

        async def mock_post(data):
            return mock_meta_and_asset_ctxs_response

        provider._post = mock_post

        oi = await provider.get_open_interest("BTC")

        assert oi.symbol == "BTC"
        assert oi.oi_contracts == 10000.0
        # OI USD = contracts * mark price
        assert oi.oi_usd == 10000.0 * 50005.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_asset_contexts_caching(self, mock_meta_and_asset_ctxs_response):
        """Test asset contexts are cached."""
        from src.services.providers.hyperliquid import HyperliquidProvider

        provider = HyperliquidProvider()
        call_count = 0

        async def mock_post(data):
            nonlocal call_count
            if data.get("type") == "metaAndAssetCtxs":
                call_count += 1
            return mock_meta_and_asset_ctxs_response

        provider._post = mock_post

        # Call twice
        await provider._get_asset_contexts()
        await provider._get_asset_contexts()

        # Should only fetch once due to caching
        assert call_count == 1

        await provider.close()


@pytest.mark.unit
class TestHyperliquidProviderErrors:
    """Test Hyperliquid provider error handling."""

    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test HTTP errors are converted to ProviderError."""
        from src.services.providers.hyperliquid import HyperliquidProvider
        from src.core.exceptions import ProviderError

        provider = HyperliquidProvider()

        # Create a mock response for HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        # Mock at the HTTP client level to test _post error handling
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
        )
        provider._client = mock_client

        with pytest.raises(ProviderError) as exc_info:
            await provider.get_ticker("BTC")

        assert "HTTP 500" in str(exc_info.value)
        await provider.close()

    @pytest.mark.asyncio
    async def test_request_error_handling(self):
        """Test network errors are converted to ProviderError."""
        from src.services.providers.hyperliquid import HyperliquidProvider
        from src.core.exceptions import ProviderError

        provider = HyperliquidProvider()

        # Mock at the HTTP client level to test _post error handling
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )
        provider._client = mock_client

        with pytest.raises(ProviderError) as exc_info:
            await provider.get_ticker("BTC")

        assert "Request failed" in str(exc_info.value)
        await provider.close()
