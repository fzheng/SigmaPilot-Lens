"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_signal() -> dict:
    """Sample trading signal for testing."""
    return {
        "event_type": "OPEN_SIGNAL",
        "symbol": "BTC",
        "signal_direction": "long",
        "entry_price": 42000.50,
        "size": 0.1,
        "liquidation_price": 38000.00,
        "ts_utc": "2024-01-15T10:30:00Z",
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


# TODO: Add fixtures for:
# - Database session
# - Redis client
# - FastAPI test client
# - Mocked AI model responses
# - Mocked provider responses
