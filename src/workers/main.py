"""Worker process entry point."""

import asyncio
import signal
import sys
from typing import List

from src.core.config import settings
from src.services.queue.redis_client import init_redis_client, close_redis_client


async def run_workers():
    """Run all worker processes."""
    # Initialize Redis
    redis = await init_redis_client()

    # TODO: Initialize workers
    # - EnrichmentWorker
    # - EvaluationWorker

    workers: List[asyncio.Task] = []

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_shutdown(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        print(f"Starting workers with profile: {settings.FEATURE_PROFILE}")
        print(f"AI models enabled: {settings.ai_models_list}")

        # Wait for shutdown signal
        await shutdown_event.wait()

    finally:
        # Cancel all workers
        for worker in workers:
            worker.cancel()

        # Wait for workers to finish
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

        # Close Redis connection
        await close_redis_client()

        print("Workers shut down gracefully")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_workers())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
