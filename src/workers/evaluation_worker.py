"""Evaluation worker that processes enriched signals with AI models.

This worker consumes enriched signals from Redis and evaluates them using
configured AI models (ChatGPT, Gemini, Claude, DeepSeek).

Features:
    - Parallel model evaluation for performance
    - Output validation with fallback decisions
    - Per-model error isolation (one failure doesn't block others)
    - Token usage tracking
    - Prompt version tracking
    - Runtime LLM configuration via database (API key management without restart)

Configuration:
    USE_REAL_AI: Set to true for real AI evaluation, false for stub mode
    LLM configs: Managed via /api/v1/llm-configs endpoints or env vars (legacy)

Usage:
    worker = EvaluationWorker(redis_client, "worker-1")
    await worker.run()
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import settings
from src.models.database import get_db_context
from src.models.orm.decision import ModelDecision as ModelDecisionORM
from src.models.orm.event import Event, ProcessingTimeline
from src.models.schemas.decision import EntryPlan, ModelDecision, ModelMeta, RiskPlan
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.evaluation.models import (
    BaseModelAdapter,
    ModelResponse,
    ModelStatus,
    create_adapter,
    create_fallback_decision,
    normalize_decision_output,
    validate_decision_output,
)
from src.services.evaluation.prompt_loader import get_prompt_for_model
from src.services.llm_config import get_llm_config_service
from src.services.publisher.publisher import publisher
from src.services.queue import QueueConsumer, RedisClient

logger = get_logger(__name__)


class EvaluationWorker(QueueConsumer):
    """Worker that evaluates enriched signals using AI models.

    Supports two modes:
        1. Stub mode (default): Returns deterministic stub decisions
        2. Real mode: Calls actual AI models in parallel

    Set USE_REAL_AI=true in environment or config to enable real AI evaluation.

    Class Invariants:
        - Adapters are lazily initialized on first use
        - Model failures are isolated (don't affect other models)
        - All decisions have validated output schema
    """

    STREAM = "lens:signals:enriched"
    GROUP = "evaluation-workers"

    def __init__(self, redis_client: RedisClient, consumer_name: str):
        """Initialize evaluation worker.

        Args:
            redis_client: Redis client for queue operations
            consumer_name: Unique name for this consumer instance
        """
        super().__init__(
            redis_client=redis_client,
            stream=self.STREAM,
            group=self.GROUP,
            consumer_name=consumer_name,
        )
        self._adapters: Dict[str, BaseModelAdapter] = {}

    async def _get_adapter(self, model_name: str) -> Optional[BaseModelAdapter]:
        """Get or create adapter for a model (lazy initialization).

        Fetches configuration from LLM config service (database-backed with caching)
        and creates adapter. Falls back to environment variables if not in database.

        Args:
            model_name: Name of the model (e.g., 'chatgpt')

        Returns:
            Model adapter or None if creation fails or model not configured
        """
        if model_name not in self._adapters:
            try:
                # Get config from LLM config service (database-backed)
                llm_service = get_llm_config_service()
                config = await llm_service.get_config(model_name)

                # Create adapter with config (or fall back to env vars if None)
                adapter = create_adapter(model_name, config)
                if adapter.is_configured:
                    self._adapters[model_name] = adapter
                    logger.info(f"Initialized adapter for {model_name}")
                else:
                    logger.warning(f"Model {model_name} not configured (missing API key)")
                    return None
            except Exception as e:
                logger.error(f"Failed to create adapter for {model_name}: {e}")
                return None
        return self._adapters.get(model_name)

    async def process_message(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """Process an enriched signal and generate AI decisions.

        Evaluates the signal with all configured models in parallel,
        validates outputs, and persists decisions to database.

        Args:
            event_id: Unique event identifier
            payload: Enriched signal payload with market data and TA indicators

        Returns:
            True if at least one decision was generated, False otherwise
        """
        start_time = time.time()
        log_stage(logger, "EVALUATION", event_id, status="started")

        try:
            # Get enabled models from LLM config service (database-backed)
            llm_service = get_llm_config_service()
            models = await llm_service.get_enabled_models()

            if not models:
                # Fall back to settings if no models configured in database
                models = settings.ai_models_list
                logger.debug("No models in database, using settings.ai_models_list")

            if settings.use_real_ai:
                # Parallel evaluation with real AI models
                decisions = await self._evaluate_parallel(event_id, payload, models)
            else:
                # Sequential stub evaluation (Phase 1 compatibility)
                decisions = []
                for model_name in models:
                    decision = await self._evaluate_stub(event_id, payload, model_name)
                    if decision:
                        decisions.append((model_name, decision))

            if not decisions:
                logger.error(f"No decisions generated for {event_id}")
                return False

            # Persist and publish decisions
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
                        "mode": "real" if settings.use_real_ai else "stub",
                    },
                )
                db.add(timeline)
                await db.commit()

                # Publish decisions
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

    async def _evaluate_parallel(
        self,
        event_id: str,
        payload: Dict[str, Any],
        models: List[str],
    ) -> List[Tuple[str, ModelDecision]]:
        """Evaluate signal with multiple models in parallel.

        Args:
            event_id: Event identifier
            payload: Enriched signal payload
            models: List of model names to evaluate

        Returns:
            List of (model_name, decision) tuples for successful evaluations
        """
        # Create tasks for all models
        tasks = [
            self._evaluate_with_model(event_id, payload, model_name)
            for model_name in models
        ]

        # Run all evaluations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful decisions
        decisions = []
        for model_name, result in zip(models, results):
            if isinstance(result, Exception):
                logger.error(f"Model {model_name} raised exception: {result}")
                metrics.record_model_error(model_name, "exception")
            elif result is not None:
                decisions.append((model_name, result))

        return decisions

    async def _evaluate_with_model(
        self,
        event_id: str,
        payload: Dict[str, Any],
        model_name: str,
    ) -> Optional[ModelDecision]:
        """Evaluate a signal with a specific AI model.

        Args:
            event_id: Event identifier
            payload: Enriched signal payload
            model_name: Name of the model to use

        Returns:
            ModelDecision if successful, None on failure
        """
        start_time = time.time()

        try:
            # Get adapter (async - fetches config from database)
            adapter = await self._get_adapter(model_name)
            if adapter is None:
                logger.warning(f"No adapter available for {model_name}, skipping")
                return None

            # Render prompt
            constraints = payload.get("constraints", {})
            prompt, prompt_version, prompt_hash = get_prompt_for_model(
                model_name=model_name,
                enriched_event=payload,
                constraints=constraints,
            )

            # Call model
            response: ModelResponse = await adapter.evaluate(prompt)
            latency_ms = response.latency_ms

            # Handle errors
            if not response.is_success:
                logger.warning(
                    f"Model {model_name} returned error: {response.status.value} - {response.error_message}"
                )

                # Save error to database
                await self._save_error_decision(
                    event_id=event_id,
                    model_name=model_name,
                    response=response,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                )

                metrics.record_model_error(model_name, response.status.value)
                return None

            # Validate output schema
            is_valid, errors = validate_decision_output(response.parsed_response)
            if not is_valid:
                logger.warning(
                    f"Model {model_name} output validation failed: {errors}"
                )

                # Save with schema error
                await self._save_error_decision(
                    event_id=event_id,
                    model_name=model_name,
                    response=response,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                    error_code="VALIDATION_FAILED",
                    error_message="; ".join(errors),
                )

                metrics.record_model_error(model_name, "validation_error")
                return None

            # Normalize output
            decision_data = normalize_decision_output(response.parsed_response)

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
                    model_version=response.model_version,
                    latency_ms=latency_ms,
                    status="SUCCESS",
                    tokens_used=response.total_tokens,
                ),
            )

            # Save to database
            async with get_db_context() as db:
                decision_orm = ModelDecisionORM(
                    event_id=event_id,
                    model_name=model_name,
                    model_version=response.model_version,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                    decision=decision_data["decision"],
                    confidence=decision_data["confidence"],
                    entry_plan=decision_data.get("entry_plan"),
                    risk_plan=decision_data.get("risk_plan"),
                    size_pct=decision_data.get("size_pct"),
                    reasons=decision_data["reasons"],
                    decision_payload=decision_data,
                    latency_ms=latency_ms,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
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
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
            )

            logger.info(
                f"Model {model_name} decision: {decision_data['decision']} "
                f"(confidence={decision_data['confidence']:.2f}, latency={latency_ms}ms)"
            )

            return decision

        except Exception as e:
            logger.error(f"Model {model_name} failed for {event_id}: {e}")
            metrics.record_model_error(model_name, "evaluation_error")
            return None

    async def _save_error_decision(
        self,
        event_id: str,
        model_name: str,
        response: ModelResponse,
        prompt_version: str,
        prompt_hash: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Save a decision record for a failed evaluation.

        Args:
            event_id: Event identifier
            model_name: Model name
            response: Model response (may contain error info)
            prompt_version: Prompt version used
            prompt_hash: Hash of prompt content
            error_code: Override error code
            error_message: Override error message
        """
        try:
            async with get_db_context() as db:
                decision_orm = ModelDecisionORM(
                    event_id=event_id,
                    model_name=model_name,
                    model_version=response.model_version,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                    decision="IGNORE",
                    confidence=0.0,
                    reasons=["model_error"],
                    decision_payload=create_fallback_decision(model_name, "error"),
                    latency_ms=response.latency_ms,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    status=error_code or response.status.value,
                    error_code=error_code or response.error_code,
                    error_message=error_message or response.error_message,
                    raw_response=response.raw_response,
                )
                db.add(decision_orm)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save error decision: {e}")

    async def _evaluate_stub(
        self,
        event_id: str,
        payload: Dict[str, Any],
        model_name: str,
    ) -> Optional[ModelDecision]:
        """Evaluate using stub decision (Phase 1 compatibility mode).

        Args:
            event_id: Event identifier
            payload: Enriched signal payload
            model_name: Model name

        Returns:
            Stub ModelDecision
        """
        start_time = time.time()

        try:
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
            logger.error(f"Stub model {model_name} failed for {event_id}: {e}")
            metrics.record_model_error(model_name, "evaluation_error")
            return None

    def _create_stub_decision(
        self,
        payload: Dict[str, Any],
        model_name: str,
    ) -> Dict[str, Any]:
        """Create a stub decision for Phase 1.

        Simulates different model personalities with varying confidence/behavior.

        Args:
            payload: Signal payload
            model_name: Model name

        Returns:
            Decision data dict
        """
        signal_direction = payload.get("signal_direction", "LONG")

        # Simulate different model personalities
        model_configs = {
            "chatgpt": {"confidence": 0.75, "decision": "FOLLOW_ENTER", "style": "aggressive"},
            "gemini": {"confidence": 0.68, "decision": "FOLLOW_ENTER", "style": "balanced"},
            "claude": {"confidence": 0.72, "decision": "FOLLOW_ENTER", "style": "conservative"},
            "deepseek": {"confidence": 0.70, "decision": "FOLLOW_ENTER", "style": "analytical"},
        }

        config = model_configs.get(model_name, {"confidence": 0.60, "decision": "IGNORE", "style": "default"})
        confidence = config["confidence"]
        decision = config["decision"]
        style = config["style"]

        # Vary entry plan based on model style
        if style == "aggressive":
            entry_plan = {"type": "market"}
        elif style == "conservative":
            entry_plan = {"type": "limit", "offset_bps": -10}
        else:
            entry_plan = {"type": "limit", "offset_bps": -5}

        # Vary risk plan based on model style
        if style == "conservative":
            risk_plan = {"stop_method": "atr", "atr_multiple": 2.5}
        elif style == "aggressive":
            risk_plan = {"stop_method": "atr", "atr_multiple": 1.5}
        else:
            risk_plan = {"stop_method": "atr", "atr_multiple": 2.0}

        return {
            "decision": decision,
            "confidence": confidence,
            "entry_plan": entry_plan,
            "risk_plan": risk_plan,
            "size_pct": int(confidence * 20),
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
        """Publish a decision via WebSocket.

        Args:
            event_id: Event identifier
            symbol: Trading symbol
            event_type: Signal type
            model_name: Model that produced the decision
            decision: Decision to publish
            received_at: Original signal receipt time
        """
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
        return "evaluate"

    async def cleanup(self) -> None:
        """Clean up model adapters."""
        for model_name, adapter in self._adapters.items():
            try:
                await adapter.close()
            except Exception as e:
                logger.error(f"Error closing adapter {model_name}: {e}")
        self._adapters.clear()
