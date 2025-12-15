"""Evaluation worker that processes enriched signals with AI models."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.core.config import settings
from src.models.database import get_db_context
from src.models.orm.decision import ModelDecision as ModelDecisionORM
from src.models.orm.event import Event, ProcessingTimeline
from src.models.schemas.decision import EntryPlan, ModelDecision, ModelMeta, RiskPlan
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.publisher.publisher import publisher
from src.services.queue import QueueConsumer, RedisClient

logger = get_logger(__name__)


class EvaluationWorker(QueueConsumer):
    """
    Worker that evaluates enriched signals using AI models.

    For Phase 1 (E2E skeleton), this creates stub decisions.
    In later phases, this will call actual AI models (ChatGPT, Gemini).
    """

    STREAM = "lens:signals:enriched"
    GROUP = "evaluation-workers"

    def __init__(self, redis_client: RedisClient, consumer_name: str):
        super().__init__(
            redis_client=redis_client,
            stream=self.STREAM,
            group=self.GROUP,
            consumer_name=consumer_name,
        )

    async def process_message(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """
        Process an enriched signal and generate AI decisions.

        Args:
            event_id: Unique event identifier
            payload: Enriched signal payload

        Returns:
            True if evaluation succeeded, False otherwise
        """
        start_time = time.time()
        log_stage(logger, "EVALUATION", event_id, status="started")

        try:
            # Get models to evaluate
            models = settings.ai_models_list

            # Evaluate with each model (in parallel in Phase 2+, sequential for now)
            decisions = []
            for model_name in models:
                decision = await self._evaluate_with_model(event_id, payload, model_name)
                if decision:
                    decisions.append((model_name, decision))

            if not decisions:
                logger.error(f"No decisions generated for {event_id}")
                return False

            async with get_db_context() as db:
                # Update event status
                from sqlalchemy import select
                result = await db.execute(
                    select(Event).where(Event.event_id == event_id)
                )
                event = result.scalar_one_or_none()

                if event:
                    event.status = "evaluated"
                    event.evaluated_at = datetime.now(timezone.utc)

                # Add timeline entry
                timeline = ProcessingTimeline(
                    event_id=event_id,
                    status="EVALUATED",
                    details={
                        "models": [m for m, _ in decisions],
                        "duration_ms": int((time.time() - start_time) * 1000),
                    },
                )
                db.add(timeline)
                await db.commit()

                # Publish decisions and update event status
                for model_name, decision in decisions:
                    await self._publish_decision(
                        event_id=event_id,
                        symbol=payload.get("symbol", "unknown"),
                        event_type=payload.get("event_type", "OPEN_SIGNAL"),
                        model_name=model_name,
                        decision=decision,
                        received_at=event.received_at if event else None,
                    )

                # Mark as published
                if event:
                    event.status = "published"
                    event.published_at = datetime.now(timezone.utc)

                # Add published timeline entry
                timeline_pub = ProcessingTimeline(
                    event_id=event_id,
                    status="PUBLISHED",
                    details={"models": [m for m, _ in decisions]},
                )
                db.add(timeline_pub)
                await db.commit()

            metrics.update_worker_heartbeat("evaluation")
            log_stage(
                logger, "EVALUATION", event_id, status="completed",
                models=[m for m, _ in decisions],
            )

            return True

        except Exception as e:
            logger.error(f"Evaluation failed for {event_id}: {e}")
            log_stage(logger, "EVALUATION", event_id, status="failed", error=str(e))
            return False

    async def _evaluate_with_model(
        self,
        event_id: str,
        payload: Dict[str, Any],
        model_name: str,
    ) -> Optional[ModelDecision]:
        """
        Evaluate a signal with a specific AI model.

        For Phase 1, this returns stub decisions.
        """
        start_time = time.time()

        try:
            # Phase 1: Create stub decision
            decision_data = self._create_stub_decision(payload, model_name)
            latency_ms = int((time.time() - start_time) * 1000)

            # Create ModelDecision schema
            decision = ModelDecision(
                decision=decision_data["decision"],
                confidence=decision_data["confidence"],
                entry_plan=EntryPlan(**decision_data["entry_plan"]) if decision_data.get("entry_plan") else None,
                risk_plan=RiskPlan(**decision_data["risk_plan"]) if decision_data.get("risk_plan") else None,
                size_pct=decision_data.get("size_pct"),
                reasons=decision_data["reasons"],
                model_meta=ModelMeta(
                    model_name=model_name,
                    model_version="stub-v1",
                    latency_ms=latency_ms,
                    status="SUCCESS",
                    tokens_used=0,
                ),
            )

            # Save to database
            async with get_db_context() as db:
                decision_orm = ModelDecisionORM(
                    event_id=event_id,
                    model_name=model_name,
                    model_version="stub-v1",
                    prompt_version="core_decision_v1",
                    prompt_hash="stub",
                    decision=decision_data["decision"],
                    confidence=decision_data["confidence"],
                    entry_plan=decision_data.get("entry_plan"),
                    risk_plan=decision_data.get("risk_plan"),
                    size_pct=decision_data.get("size_pct"),
                    reasons=decision_data["reasons"],
                    decision_payload=decision_data,
                    latency_ms=latency_ms,
                    tokens_in=0,
                    tokens_out=0,
                    status="ok",
                )
                db.add(decision_orm)
                await db.commit()

            # Record metrics
            metrics.record_evaluation(
                model=model_name,
                symbol=payload.get("symbol", "unknown"),
                decision=decision_data["decision"],
                duration_seconds=time.time() - start_time,
                tokens_in=0,
                tokens_out=0,
            )

            return decision

        except Exception as e:
            logger.error(f"Model {model_name} failed for {event_id}: {e}")
            metrics.record_model_error(model_name, "evaluation_error")
            return None

    def _create_stub_decision(
        self,
        payload: Dict[str, Any],
        model_name: str,
    ) -> Dict[str, Any]:
        """
        Create a stub decision for Phase 1.

        This mimics the structure of real AI model output.
        """
        signal_direction = payload.get("signal_direction", "LONG")

        # Simulate different model personalities
        if model_name == "chatgpt":
            confidence = 0.75
            decision = "FOLLOW_ENTER"
        elif model_name == "gemini":
            confidence = 0.68
            decision = "FOLLOW_ENTER"
        else:
            confidence = 0.60
            decision = "IGNORE"

        return {
            "decision": decision,
            "confidence": confidence,
            "entry_plan": {
                "type": "limit",
                "offset_bps": -5,  # 5 bps below market for limit buy
            },
            "risk_plan": {
                "stop_method": "atr",
                "atr_multiple": 2.0,
            },
            "size_pct": int(confidence * 20),  # Scale size with confidence
            "reasons": [
                "bullish_trend" if signal_direction == "LONG" else "bearish_trend",
                "ema_bullish_stack" if signal_direction == "LONG" else "ema_bearish_stack",
                "funding_favorable",
                "good_rr_ratio",
            ],
        }

    async def _publish_decision(
        self,
        event_id: str,
        symbol: str,
        event_type: str,
        model_name: str,
        decision: ModelDecision,
        received_at: Optional[datetime] = None,
    ) -> None:
        """Publish a decision via WebSocket."""
        try:
            await publisher.publish_decision(
                event_id=event_id,
                symbol=symbol,
                event_type=event_type,
                model=model_name,
                decision=decision,
                received_at=received_at,
            )
        except Exception as e:
            logger.error(f"Failed to publish decision for {event_id}: {e}")

    def _get_stage_name(self) -> str:
        """Get the stage name for DLQ entries."""
        return "evaluation"
