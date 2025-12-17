"""Pytest configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Set testing environment before importing app
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["USE_REAL_AI"] = "false"  # Use stub decisions in tests


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# App and Client Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def app() -> FastAPI:
    """Create FastAPI app for testing."""
    from src.main import app as fastapi_app
    return fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock Redis client."""
    redis = MagicMock()
    redis.lpush = AsyncMock(return_value=1)
    redis.rpop = AsyncMock(return_value=None)
    redis.brpop = AsyncMock(return_value=None)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.ping = AsyncMock(return_value=True)
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Mock database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock()
    session.close = AsyncMock()
    return session


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def test_signal() -> dict:
    """Sample trading signal for testing."""
    return {
        "event_type": "OPEN_SIGNAL",
        "symbol": "BTC",
        "signal_direction": "long",
        "entry_price": 42000.50,
        "size": 0.1,
        "ts_utc": "2024-01-15T10:30:00Z",
        "source": "test_strategy",
    }


@pytest.fixture
def test_signal_close() -> dict:
    """Sample close signal for testing."""
    return {
        "event_type": "CLOSE_SIGNAL",
        "symbol": "ETH",
        "signal_direction": "short",
        "entry_price": 2500.00,
        "size": 1.0,
        "ts_utc": "2024-01-15T11:00:00Z",
        "source": "test_strategy",
    }


@pytest.fixture
def test_enriched_signal(test_signal: dict) -> dict:
    """Sample enriched signal for testing."""
    return {
        "event_id": "test-event-123",
        "original": test_signal,
        "market": {
            "mid": 42050.25,
            "bid": 42049.00,
            "ask": 42051.50,
            "spread_bps": 0.59,
            "price_drift_bps_from_entry": 11.84,
            "fetched_at": "2024-01-15T10:30:01Z",
        },
        "ta": {
            "timeframes": {
                "1h": {
                    "ema": {"ema_9": 41950.0, "ema_21": 41800.5, "ema_50": 41500.0},
                    "macd": {"macd_line": 120.5, "signal_line": 95.2, "histogram": 25.3},
                    "rsi": 62.1,
                    "atr": 350.2,
                }
            }
        },
        "constraints": {
            "min_hold_minutes": 15,
            "one_direction_only": True,
            "max_trades_per_hour": 4,
            "max_position_size_pct": 25,
        },
        "quality_flags": {
            "missing_data": [],
            "stale_data": [],
            "out_of_range": [],
            "provider_errors": [],
        },
        "enriched_at": "2024-01-15T10:30:02Z",
    }


@pytest.fixture
def test_decision() -> dict:
    """Sample model decision for testing."""
    return {
        "decision": "FOLLOW_ENTER",
        "confidence": 0.78,
        "entry_plan": {"type": "limit", "offset_bps": -5},
        "risk_plan": {"stop_method": "atr", "atr_multiple": 2.0},
        "size_pct": 15,
        "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
        "model_meta": {
            "model_name": "chatgpt",
            "model_version": "gpt-4o",
            "latency_ms": 1850,
            "status": "SUCCESS",
            "tokens_used": 1250,
        },
    }


@pytest.fixture
def invalid_signals() -> list[dict]:
    """Collection of invalid signals for validation testing."""
    return [
        # Missing required field
        {
            "event_type": "OPEN_SIGNAL",
            "symbol": "BTC",
            # missing signal_direction
            "entry_price": 42000.50,
            "size": 0.1,
            "ts_utc": "2024-01-15T10:30:00Z",
            "source": "test",
        },
        # Invalid event_type
        {
            "event_type": "INVALID_TYPE",
            "symbol": "BTC",
            "signal_direction": "long",
            "entry_price": 42000.50,
            "size": 0.1,
            "ts_utc": "2024-01-15T10:30:00Z",
            "source": "test",
        },
        # Negative price
        {
            "event_type": "OPEN_SIGNAL",
            "symbol": "BTC",
            "signal_direction": "long",
            "entry_price": -100.0,
            "size": 0.1,
            "ts_utc": "2024-01-15T10:30:00Z",
            "source": "test",
        },
        # Zero size
        {
            "event_type": "OPEN_SIGNAL",
            "symbol": "BTC",
            "signal_direction": "long",
            "entry_price": 42000.50,
            "size": 0,
            "ts_utc": "2024-01-15T10:30:00Z",
            "source": "test",
        },
    ]
