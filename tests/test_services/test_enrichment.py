"""Tests for the enrichment service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.providers.base import (
    FundingRate,
    OHLCV,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    Ticker,
)


@pytest.fixture
def mock_ticker():
    """Create mock ticker data."""
    return Ticker(
        symbol="BTC",
        mid=50000.0,
        bid=49990.0,
        ask=50010.0,
        spread_bps=4.0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_candles():
    """Create mock OHLCV candles."""
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(100):
        price = 50000 + i * 10
        candles.append(
            OHLCV(
                timestamp=base_time.replace(hour=i % 24, day=1 + i // 24),
                open=price - 5,
                high=price + 20,
                low=price - 20,
                close=price,
                volume=1000.0,
            )
        )
    return candles


@pytest.fixture
def mock_funding():
    """Create mock funding rate data."""
    return FundingRate(
        symbol="BTC",
        rate=0.0001,
        predicted_rate=0.00015,
        next_funding_time=datetime.now(timezone.utc),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_oi():
    """Create mock open interest data."""
    return OpenInterest(
        symbol="BTC",
        oi_usd=500000000.0,
        oi_contracts=10000.0,
        change_24h_pct=2.5,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_provider(mock_ticker, mock_candles, mock_funding, mock_oi):
    """Create mock provider with all methods."""
    provider = MagicMock()
    provider.get_ticker = AsyncMock(return_value=mock_ticker)
    provider.get_ohlcv = AsyncMock(return_value=mock_candles)
    provider.get_funding_rate = AsyncMock(return_value=mock_funding)
    provider.get_open_interest = AsyncMock(return_value=mock_oi)
    provider.get_mark_price = AsyncMock(return_value=50005.0)
    provider.get_24h_volume = AsyncMock(return_value=1000000000.0)
    provider.close = AsyncMock()
    return provider


@pytest.mark.unit
class TestEnrichmentService:
    """Test enrichment service."""

    @pytest.mark.asyncio
    async def test_enrich_basic(self, mock_provider, test_signal):
        """Test basic enrichment flow."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
            profile="trend_follow_v1",
        )

        assert result.success
        assert result.market_data is not None
        assert result.market_data["mid_price"] == 50000.0
        assert result.ta_data is not None
        assert "timeframes" in result.ta_data
        assert len(result.quality_flags.provider_errors) == 0

    @pytest.mark.asyncio
    async def test_enrich_calculates_price_drift(self, mock_provider, test_signal):
        """Test price drift calculation from entry."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        # Signal entry price is different from current mid
        test_signal["entry_price"] = 49000.0  # Entry below current

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert result.success
        # Price drifted up from entry
        drift = result.market_data["price_drift_from_entry_bps"]
        assert drift > 0  # Current price (50000) > entry (49000)

    @pytest.mark.asyncio
    async def test_enrich_handles_provider_error(self, mock_provider, test_signal):
        """Test enrichment handles provider errors gracefully."""
        from src.services.enrichment.enrichment_service import EnrichmentService
        from src.core.exceptions import ProviderError

        mock_provider.get_ticker = AsyncMock(side_effect=ProviderError("test", "API error"))

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert not result.success
        assert result.market_data is None
        assert len(result.quality_flags.provider_errors) > 0
        assert "ticker" in result.quality_flags.provider_errors[0]

    @pytest.mark.asyncio
    async def test_enrich_builds_payload(self, mock_provider, test_signal):
        """Test enriched payload structure."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        payload = result.enriched_payload
        assert payload["event_id"] == "test-123"
        assert payload["symbol"] == test_signal["symbol"]
        assert "market" in payload
        assert "ta" in payload
        assert "constraints" in payload

    @pytest.mark.asyncio
    async def test_enrich_tracks_timestamps(self, mock_provider, test_signal):
        """Test data timestamps are tracked."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert "mid_ts" in result.data_timestamps
        # Should have candle timestamps for configured timeframes
        assert any("candles" in key for key in result.data_timestamps.keys())


@pytest.mark.unit
class TestQualityValidation:
    """Test data quality validation."""

    def test_validate_market_data_spread_too_high(self):
        """Test spread validation."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        market_data = {"spread_bps": 150, "bid": 100, "ask": 101, "mid_price": 100.5}
        service._validate_market_data(market_data, quality_flags)

        assert len(quality_flags.out_of_range) > 0
        assert "spread_bps" in quality_flags.out_of_range[0]

    def test_validate_market_data_bid_ask_inverted(self):
        """Test bid/ask sanity check."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        market_data = {"spread_bps": 10, "bid": 101, "ask": 100, "mid_price": 100.5}
        service._validate_market_data(market_data, quality_flags)

        assert len(quality_flags.out_of_range) > 0
        assert "bid" in quality_flags.out_of_range[0]

    def test_validate_ta_data_rsi_out_of_range(self):
        """Test RSI validation."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        ta_data = {"timeframes": {"1h": {"rsi": 150, "atr": 100}}}
        service._validate_ta_data(ta_data, quality_flags)

        assert len(quality_flags.out_of_range) > 0
        assert "rsi" in quality_flags.out_of_range[0]

    def test_validate_ta_data_negative_atr(self):
        """Test ATR validation."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        ta_data = {"timeframes": {"1h": {"rsi": 50, "atr": -100}}}
        service._validate_ta_data(ta_data, quality_flags)

        assert len(quality_flags.out_of_range) > 0
        assert "atr" in quality_flags.out_of_range[0]

    def test_check_staleness_old_data(self):
        """Test staleness detection."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags
        from datetime import timedelta

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=60)  # 60 seconds old

        data_timestamps = {"mid_ts": old_time.isoformat()}
        service._check_staleness(data_timestamps, now, quality_flags)

        # mid_ts has 10s threshold, so 60s should be stale
        assert len(quality_flags.stale) > 0
        assert "mid_ts" in quality_flags.stale[0]

    def test_check_staleness_fresh_data(self):
        """Test fresh data is not flagged."""
        from src.services.enrichment.enrichment_service import EnrichmentService, QualityFlags
        from datetime import timedelta

        service = EnrichmentService()
        quality_flags = QualityFlags(stale=[], missing=[], out_of_range=[], provider_errors=[])

        now = datetime.now(timezone.utc)
        fresh_time = now - timedelta(seconds=2)  # 2 seconds old

        data_timestamps = {"mid_ts": fresh_time.isoformat()}
        service._check_staleness(data_timestamps, now, quality_flags)

        # 2s is within 10s threshold
        assert len(quality_flags.stale) == 0


@pytest.mark.unit
class TestEnrichmentSignalAge:
    """Test signal age tracking in enrichment."""

    @pytest.mark.asyncio
    async def test_enrich_tracks_signal_age(self, mock_provider, test_signal):
        """Test signal age is calculated and included in result."""
        from src.services.enrichment.enrichment_service import EnrichmentService
        from datetime import timedelta

        service = EnrichmentService(provider=mock_provider)

        # Set signal timestamp to 30 seconds ago
        signal_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        test_signal["ts_utc"] = signal_time.isoformat()

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert result.success
        # Signal age should be approximately 30 seconds (allow some tolerance)
        assert 25 < result.signal_age_seconds < 35

    @pytest.mark.asyncio
    async def test_enrich_handles_missing_timestamp(self, mock_provider, test_signal):
        """Test enrichment handles missing signal timestamp gracefully."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        # Remove timestamp from signal
        test_signal.pop("ts_utc", None)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert result.success
        assert result.signal_age_seconds == 0.0  # Default when no timestamp

    @pytest.mark.asyncio
    async def test_enrich_handles_invalid_timestamp(self, mock_provider, test_signal):
        """Test enrichment handles invalid timestamp format gracefully."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        # Set invalid timestamp
        test_signal["ts_utc"] = "not-a-valid-timestamp"

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        assert result.success  # Should not fail due to bad timestamp
        assert result.signal_age_seconds == 0.0


@pytest.mark.unit
class TestEnrichmentPayloadStructure:
    """Test enriched payload structure and content."""

    @pytest.mark.asyncio
    async def test_payload_contains_all_required_fields(self, mock_provider, test_signal):
        """Test enriched payload has all required fields for AI evaluation."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
        )

        payload = result.enriched_payload

        # Required top-level fields
        assert "event_id" in payload
        assert "symbol" in payload
        assert "signal_direction" in payload
        assert "entry_price" in payload
        assert "market" in payload
        assert "ta" in payload
        assert "constraints" in payload

        # Market data fields
        assert "mid_price" in payload["market"]
        assert "bid" in payload["market"]
        assert "ask" in payload["market"]
        assert "spread_bps" in payload["market"]

    @pytest.mark.asyncio
    async def test_payload_ta_contains_all_timeframes(self, mock_provider, test_signal):
        """Test TA data includes all configured timeframes."""
        from src.services.enrichment.enrichment_service import EnrichmentService

        service = EnrichmentService(provider=mock_provider)

        result = await service.enrich(
            event_id="test-123",
            signal=test_signal,
            profile="trend_follow_v1",
        )

        ta = result.enriched_payload["ta"]
        assert "timeframes" in ta

        # Each timeframe should have indicators
        for tf, indicators in ta["timeframes"].items():
            assert "ema" in indicators
            assert "macd" in indicators
            assert "rsi" in indicators
            assert "atr" in indicators
