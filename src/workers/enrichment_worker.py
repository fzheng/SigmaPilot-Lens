"""Enrichment worker that processes raw signals."""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from src.core.config import settings
from src.core.exceptions import SignalRejectedError
from src.models.database import get_db_context
from src.models.orm.event import EnrichedEvent, Event, ProcessingTimeline
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.enrichment.enrichment_service import EnrichmentService
from src.services.enrichment.signal_validator import SignalValidator
from src.services.queue import QueueConsumer, QueueProducer, RedisClient

logger = get_logger(__name__)


class EnrichmentWorker(QueueConsumer):
    """
    Worker that validates and enriches raw trading signals with market data.

    Process:
        1. Validates signal age (max 5 minutes) and price drift (max 2%)
        2. Rejects invalid signals early to save downstream AI costs
        3. Fetches real-time market data from Hyperliquid
        4. Computes technical indicators based on the configured feature profile
        5. Enqueues enriched payload for AI evaluation

    Invalid signals are marked as 'rejected' in the database and acknowledged
    (not retried). Partial enrichment failures are marked as 'enrichment_partial'
    but still forwarded to evaluation.
    """

    STREAM = "lens:signals:pending"
    GROUP = "enrichment-workers"

    def __init__(self, redis_client: RedisClient, producer: QueueProducer, consumer_name: str):
        super().__init__(
            redis_client=redis_client,
            stream=self.STREAM,
            group=self.GROUP,
            consumer_name=consumer_name,
        )
        self.producer = producer
        self.enrichment_service = EnrichmentService()
        self.signal_validator = SignalValidator(provider=self.enrichment_service.provider)

    async def cleanup(self):
        """Cleanup resources when worker stops."""
        await self.enrichment_service.close()
        # validator shares provider with enrichment service, no need to close separately

    async def process_message(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """
        Process a raw signal and enrich it with market data.

        Performs early price validation to reject signals with excessive drift
        (>2%) before expensive enrichment, saving AI costs.

        Args:
            event_id: Unique event identifier
            payload: Raw signal payload

        Returns:
            True if enrichment succeeded, False otherwise
        """
        start_time = time.time()
        log_stage(logger, "ENRICHMENT", event_id, status="started")

        try:
            # Early validation: check price drift and signal age
            try:
                validation_result = await self.signal_validator.validate(
                    signal=payload,
                    raise_on_invalid=True,
                )
                logger.info(
                    f"Signal validated for {event_id}: drift={validation_result.drift_bps:.1f}bps, "
                    f"age={validation_result.signal_age_seconds:.0f}s"
                )
            except SignalRejectedError as e:
                # Signal rejected - update status and skip enrichment
                await self._mark_rejected(event_id, e)
                log_stage(
                    logger, "ENRICHMENT", event_id, status="rejected",
                    reason=e.reason,
                )
                # Return True to acknowledge the message (don't retry rejected signals)
                return True

            async with get_db_context() as db:
                # Get the event from database
                from sqlalchemy import select
                result = await db.execute(
                    select(Event).where(Event.event_id == event_id)
                )
                event = result.scalar_one_or_none()

                if not event:
                    logger.error(f"Event not found: {event_id}")
                    return False

                # Enrich using real market data
                enrichment_result = await self.enrichment_service.enrich(
                    event_id=event_id,
                    signal=payload,
                    profile=settings.FEATURE_PROFILE,
                )

                now = datetime.now(timezone.utc)
                duration_ms = int((time.time() - start_time) * 1000)

                # Convert quality flags to dict
                quality_flags_dict = {
                    "stale": enrichment_result.quality_flags.stale,
                    "missing": enrichment_result.quality_flags.missing,
                    "out_of_range": enrichment_result.quality_flags.out_of_range,
                    "provider_errors": enrichment_result.quality_flags.provider_errors,
                }

                # Create enriched event record
                enriched_event = EnrichedEvent(
                    event_id=event_id,
                    feature_profile=settings.FEATURE_PROFILE,
                    provider="hyperliquid",
                    provider_version="v1",
                    market_data=enrichment_result.market_data,
                    ta_data=enrichment_result.ta_data,
                    levels_data=enrichment_result.levels_data,
                    derivs_data=enrichment_result.derivs_data,
                    constraints=enrichment_result.constraints,
                    data_timestamps=enrichment_result.data_timestamps,
                    quality_flags=quality_flags_dict,
                    enriched_payload=enrichment_result.enriched_payload,
                    enriched_at=now,
                    enrichment_duration_ms=duration_ms,
                )
                db.add(enriched_event)

                # Update event status
                if enrichment_result.success:
                    event.status = "enriched"
                else:
                    event.status = "enrichment_partial"
                    logger.warning(
                        f"Enrichment completed with issues for {event_id}: "
                        f"errors={quality_flags_dict['provider_errors']}, "
                        f"missing={quality_flags_dict['missing']}"
                    )
                event.enriched_at = now

                # Add timeline entry
                timeline = ProcessingTimeline(
                    event_id=event_id,
                    status="ENRICHED",
                    details={
                        "duration_ms": duration_ms,
                        "profile": settings.FEATURE_PROFILE,
                        "success": enrichment_result.success,
                        "quality_flags": quality_flags_dict,
                    },
                )
                db.add(timeline)

                await db.commit()

                # Enqueue for evaluation even if partial (let evaluator decide)
                await self.producer.enqueue_enriched(event_id, enrichment_result.enriched_payload)

            # Record metrics
            duration_seconds = time.time() - start_time
            metrics.record_enrichment(
                profile=settings.FEATURE_PROFILE,
                symbol=payload.get("symbol", "unknown"),
                duration_seconds=duration_seconds,
            )
            metrics.update_worker_heartbeat("enrichment")

            log_stage(
                logger, "ENRICHMENT", event_id, status="completed",
                duration_ms=int(duration_seconds * 1000),
                success=enrichment_result.success,
            )

            return True

        except Exception as e:
            logger.error(f"Enrichment failed for {event_id}: {e}", exc_info=True)
            log_stage(logger, "ENRICHMENT", event_id, status="failed", error=str(e))
            return False

    def _get_stage_name(self) -> str:
        """Get the stage name for DLQ entries."""
        return "enrich"

    async def _mark_rejected(self, event_id: str, error: SignalRejectedError) -> None:
        """
        Mark an event as rejected due to validation failure.

        Args:
            event_id: Event to mark as rejected
            error: The rejection error with details
        """
        async with get_db_context() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Event).where(Event.event_id == event_id)
            )
            event = result.scalar_one_or_none()

            if event:
                event.status = "rejected"
                event.enriched_at = datetime.now(timezone.utc)

                # Add timeline entry for rejection
                timeline = ProcessingTimeline(
                    event_id=event_id,
                    status="REJECTED",
                    details={
                        "reason": error.reason,
                        "symbol": error.symbol,
                        "details": error.details[0] if error.details else {},
                    },
                )
                db.add(timeline)

                await db.commit()

                # Record rejection metric
                metrics.record_signal_rejected(
                    symbol=error.symbol,
                    reason=error.reason,
                )

                logger.warning(f"Signal rejected for {event_id}: {error.reason}")
