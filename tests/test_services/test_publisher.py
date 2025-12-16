"""Tests for publisher service."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.unit
def test_decision_schema():
    """Test decision schema."""
    from src.models.schemas.decision import ModelDecision, ModelMeta

    meta = ModelMeta(
        model_name="chatgpt",
        model_version="gpt-4o",
        latency_ms=100,
        status="SUCCESS",
    )

    decision = ModelDecision(
        decision="FOLLOW_ENTER",
        confidence=0.75,
        reasons=["bullish_trend"],
        model_meta=meta,
    )

    assert decision.decision == "FOLLOW_ENTER"
    assert decision.confidence == 0.75
    assert "bullish_trend" in decision.reasons


@pytest.mark.unit
def test_decision_types():
    """Test all decision types are valid."""
    from src.models.schemas.decision import ModelDecision, ModelMeta

    valid_decisions = [
        "FOLLOW_ENTER",
        "IGNORE",
        "FOLLOW_EXIT",
        "HOLD",
        "TIGHTEN_STOP",
    ]

    meta = ModelMeta(
        model_name="test",
        latency_ms=100,
        status="SUCCESS",
    )

    for decision_type in valid_decisions:
        decision = ModelDecision(
            decision=decision_type,
            confidence=0.5,
            reasons=["test"],
            model_meta=meta,
        )
        assert decision.decision == decision_type


@pytest.mark.unit
async def test_ws_manager_subscription():
    """Test WebSocket manager subscription handling."""
    from src.services.publisher.ws_server import WebSocketManager

    manager = WebSocketManager()

    # Mock WebSocket
    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()

    # Test connect
    sub_id = await manager.connect(mock_ws)
    assert sub_id is not None
    assert sub_id in manager.subscriptions

    # Test disconnect
    await manager.disconnect(sub_id)
    assert sub_id not in manager.subscriptions


@pytest.mark.unit
def test_entry_plan_schema():
    """Test entry plan schema."""
    from src.models.schemas.decision import EntryPlan

    plan = EntryPlan(type="limit", offset_bps=-5.0)
    assert plan.type == "limit"
    assert plan.offset_bps == -5.0


@pytest.mark.unit
def test_risk_plan_schema():
    """Test risk plan schema."""
    from src.models.schemas.decision import RiskPlan

    plan = RiskPlan(stop_method="atr", atr_multiple=2.0)
    assert plan.stop_method == "atr"
    assert plan.atr_multiple == 2.0
