"""Worker process entry point.

This module serves as the main entry point for the worker process that handles
signal processing in SigmaPilot Lens. It orchestrates two concurrent workers:

1. EnrichmentWorker: Consumes signals from the pending queue, validates them
   against current market conditions, fetches market data from Hyperliquid,
   computes technical indicators, and produces enriched events.

2. EvaluationWorker: Consumes enriched events, evaluates them using multiple
   AI models in parallel, validates outputs, and publishes decisions via WebSocket.

Key Features:
- Graceful shutdown handling (SIGINT/SIGTERM)
- Unique consumer names for Redis consumer groups (enables horizontal scaling)
- Connection lifecycle management (Redis, PostgreSQL)
- Worker failure detection and logging

Usage:
    python -m src.workers.main

Environment:
    - FEATURE_PROFILE: Enrichment profile (trend_follow_v1, crypto_perps_v1, full_v1)
    - AI_MODELS: Comma-separated list of AI models to use
    - DATABASE_URL: PostgreSQL connection string
    - REDIS_URL: Redis connection string
"""

import asyncio
import os
import signal
import sys
from typing import List

from src.core.config import settings
from src.models.database import init_db, close_db
from src.observability.logging import get_logger, setup_logging
from src.services.queue import (
    QueueProducer,
    RedisClient,
    close_redis_client,
    get_redis_client,
    init_redis_client,
)
from src.workers.enrichment_worker import EnrichmentWorker
from src.workers.evaluation_worker import EvaluationWorker

logger = get_logger(__name__)


async def run_workers():
    """Run all worker processes.

    Initializes connections, creates worker instances, and runs them concurrently.
    Handles graceful shutdown on SIGINT/SIGTERM signals with a 10-second timeout
    for worker cancellation.

    The function creates unique consumer names using hostname and PID to enable
    multiple worker instances to participate in the same consumer group for
    horizontal scaling.
    """
    # Set up logging
    setup_logging()

    # Initialize database connection
    await init_db()
    logger.info("Database initialized")

    # Initialize Redis
    redis = await init_redis_client()
    redis_client = RedisClient(redis)
    logger.info("Redis initialized")

    # Create producer for enrichment worker
    producer = QueueProducer(redis_client)

    # Generate unique consumer names based on hostname/PID
    hostname = os.environ.get("HOSTNAME", "worker")
    pid = os.getpid()
    consumer_suffix = f"{hostname}-{pid}"

    # Create workers
    enrichment_worker = EnrichmentWorker(
        redis_client=redis_client,
        producer=producer,
        consumer_name=f"enrichment-{consumer_suffix}",
    )
    evaluation_worker = EvaluationWorker(
        redis_client=redis_client,
        consumer_name=f"evaluation-{consumer_suffix}",
    )

    workers: List[asyncio.Task] = []

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
        # Stop workers gracefully
        enrichment_worker.stop()
        evaluation_worker.stop()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        logger.info(f"Starting workers with profile: {settings.FEATURE_PROFILE}")
        logger.info(f"AI models enabled: {settings.ai_models_list}")

        # Start worker tasks
        workers = [
            asyncio.create_task(enrichment_worker.run(), name="enrichment-worker"),
            asyncio.create_task(evaluation_worker.run(), name="evaluation-worker"),
        ]

        logger.info("Workers started, waiting for signals...")

        # Wait for shutdown signal or any worker to fail
        done, pending = await asyncio.wait(
            workers + [asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If a worker failed, log the error
        for task in done:
            if task.get_name() in ["enrichment-worker", "evaluation-worker"]:
                try:
                    task.result()
                except Exception as e:
                    logger.error(f"Worker {task.get_name()} failed: {e}")

    finally:
        # Cancel all workers
        for worker in workers:
            worker.cancel()

        # Wait for workers to finish (with timeout)
        if workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*workers, return_exceptions=True),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Workers did not shut down in time")

        # Close connections
        await close_redis_client()
        await close_db()

        logger.info("Workers shut down gracefully")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_workers())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
