"""Enrichment worker that processes raw signals."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict

from src.core.config import settings
from src.models.database import get_db_context
from src.models.orm.event import EnrichedEvent, Event, ProcessingTimeline
from src.observability.logging import get_logger, log_stage
from src.observability.metrics import metrics
from src.services.queue import QueueConsumer, QueueProducer, RedisClient

logger = get_logger(__name__)


class EnrichmentWorker(QueueConsumer):
    """
    Worker that enriches raw trading signals with market data.

    For Phase 1 (E2E skeleton), this creates stub enriched data.
    In later phases, this will fetch real data from Hyperliquid.
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

    async def process_message(self, event_id: str, payload: Dict[str, Any]) -> bool:
        """
        Process a raw signal and enrich it with market data.

        Args:
            event_id: Unique event identifier
            payload: Raw signal payload

        Returns:
            True if enrichment succeeded, False otherwise
        """
        start_time = time.time()
        log_stage(logger, "ENRICHMENT", event_id, status="started")

        try:
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

                # Phase 1: Create stub enriched data
                now = datetime.now(timezone.utc)
                enriched_data = self._create_stub_enrichment(payload)

                duration_ms = int((time.time() - start_time) * 1000)

                # Create enriched event record
                enriched_event = EnrichedEvent(
                    event_id=event_id,
                    feature_profile=settings.FEATURE_PROFILE,
                    provider="stub",
                    provider_version="phase1",
                    market_data=enriched_data["market_data"],
                    ta_data=enriched_data["ta_data"],
                    levels_data=enriched_data.get("levels_data"),
                    derivs_data=enriched_data.get("derivs_data"),
                    constraints=enriched_data["constraints"],
                    data_timestamps=enriched_data["data_timestamps"],
                    quality_flags=enriched_data["quality_flags"],
                    enriched_payload=enriched_data["enriched_payload"],
                    enriched_at=now,
                    enrichment_duration_ms=duration_ms,
                )
                db.add(enriched_event)

                # Update event status
                event.status = "enriched"
                event.enriched_at = now

                # Add timeline entry
                timeline = ProcessingTimeline(
                    event_id=event_id,
                    status="ENRICHED",
                    details={"duration_ms": duration_ms, "profile": settings.FEATURE_PROFILE},
                )
                db.add(timeline)

                await db.commit()

                # Enqueue for evaluation
                await self.producer.enqueue_enriched(event_id, enriched_data["enriched_payload"])

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
            )

            return True

        except Exception as e:
            logger.error(f"Enrichment failed for {event_id}: {e}")
            log_stage(logger, "ENRICHMENT", event_id, status="failed", error=str(e))
            return False

    def _create_stub_enrichment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create stub enrichment data for Phase 1.

        This mimics the structure of real enriched data without
        actually fetching from providers.
        """
        now = datetime.now(timezone.utc)
        symbol = payload.get("symbol", "BTC-PERP")
        entry_price = float(payload.get("entry_price", 50000))
        signal_direction = payload.get("signal_direction", "LONG")

        # Stub market data
        market_data = {
            "mid_price": entry_price * 1.001,  # Slight drift
            "bid": entry_price * 0.999,
            "ask": entry_price * 1.001,
            "spread_bps": 20,  # 0.2% spread
            "volume_24h": 1_000_000,
        }

        # Stub TA data (trend_follow_v1 profile)
        ta_data = {
            "ema_9": entry_price * 1.002,
            "ema_21": entry_price * 1.001,
            "ema_50": entry_price * 0.998,
            "macd": {
                "macd": 50,
                "signal": 40,
                "histogram": 10,
            },
            "rsi_14": 55,
            "atr_14": entry_price * 0.02,  # 2% ATR
        }

        # Stub derivs data (for crypto perps)
        derivs_data = {
            "funding_rate": 0.0001,  # 0.01%
            "funding_interval_h": 8,
            "open_interest": 50_000_000,
            "mark_price": entry_price * 1.0005,
            "oracle_price": entry_price * 1.0003,
        }

        # Stub constraints
        constraints = {
            "max_position_size_pct": 20,
            "min_hold_minutes": 30,
            "max_trades_per_hour": 4,
            "max_leverage": 10,
        }

        # Data timestamps
        data_timestamps = {
            "mid_ts": now.isoformat(),
            "l2_ts": now.isoformat(),
            "candles_ts": now.isoformat(),
            "funding_ts": now.isoformat(),
        }

        # Quality flags (all good for stub)
        quality_flags = {
            "stale": [],
            "missing": [],
            "out_of_range": [],
            "provider_errors": [],
        }

        # Compact enriched payload for AI
        enriched_payload = {
            "event_id": payload.get("event_id", ""),
            "symbol": symbol,
            "signal_direction": signal_direction,
            "entry_price": entry_price,
            "liquidation_price": float(payload.get("liquidation_price", entry_price * 0.9)),
            "size": float(payload.get("size", 1)),
            "ts_utc": payload.get("ts_utc", now.isoformat()),
            "source": payload.get("source", "unknown"),
            "event_type": payload.get("event_type", "OPEN_SIGNAL"),
            "market": market_data,
            "ta": ta_data,
            "derivs": derivs_data,
            "constraints": constraints,
        }

        return {
            "market_data": market_data,
            "ta_data": ta_data,
            "levels_data": None,
            "derivs_data": derivs_data,
            "constraints": constraints,
            "data_timestamps": data_timestamps,
            "quality_flags": quality_flags,
            "enriched_payload": enriched_payload,
        }

    def _get_stage_name(self) -> str:
        """Get the stage name for DLQ entries."""
        return "enrichment"
