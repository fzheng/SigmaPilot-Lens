#!/usr/bin/env python3
"""
Load test script for SigmaPilot Lens.

Targets: 60 signals/min sustained throughput
Verifies: p95 latencies within SLA

Usage:
    # Run against local docker-compose (from within network)
    python -m tests.load.load_test --target http://gateway:8000 --duration 60

    # Run with custom rate
    python -m tests.load.load_test --target http://localhost:8000 --rate 30 --duration 120
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

try:
    import httpx
except ImportError:
    print("Error: httpx required. Install with: pip install httpx")
    sys.exit(1)


@dataclass
class TestResult:
    """Single request result."""
    success: bool
    status_code: int
    latency_ms: float
    event_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class LoadTestStats:
    """Aggregated load test statistics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def requests_per_second(self) -> float:
        duration = self.end_time - self.start_time
        if duration == 0:
            return 0.0
        return self.total_requests / duration

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def max_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return max(self.latencies)

    @property
    def min_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return min(self.latencies)


class LoadTester:
    """Load test runner for SigmaPilot Lens API."""

    SYMBOLS = ["BTC", "ETH", "SOL", "ARB", "DOGE", "AVAX", "LINK", "MATIC"]
    DIRECTIONS = ["long", "short"]
    EVENT_TYPES = ["OPEN_SIGNAL"]
    SOURCES = ["strategy_alpha", "strategy_beta", "strategy_gamma"]

    def __init__(
        self,
        target_url: str,
        rate_per_min: int = 60,
        duration_seconds: int = 60,
        concurrent_requests: int = 5,
    ):
        self.target_url = target_url.rstrip("/")
        self.rate_per_min = rate_per_min
        self.duration_seconds = duration_seconds
        self.concurrent_requests = concurrent_requests
        self.stats = LoadTestStats()
        self._stop_event = asyncio.Event()

    def _generate_signal(self) -> dict:
        """Generate a random valid signal payload."""
        symbol = random.choice(self.SYMBOLS)
        direction = random.choice(self.DIRECTIONS)

        # Generate realistic prices based on symbol
        base_prices = {
            "BTC": 95000,
            "ETH": 3500,
            "SOL": 200,
            "ARB": 1.2,
            "DOGE": 0.35,
            "AVAX": 45,
            "LINK": 25,
            "MATIC": 0.95,
        }
        base_price = base_prices.get(symbol, 100)
        # Add some randomness (+/- 2%)
        entry_price = base_price * (1 + random.uniform(-0.02, 0.02))

        return {
            "event_type": random.choice(self.EVENT_TYPES),
            "symbol": symbol,
            "signal_direction": direction,
            "entry_price": round(entry_price, 2),
            "size": round(random.uniform(0.01, 1.0), 4),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "source": random.choice(self.SOURCES),
        }

    async def _send_signal(self, client: httpx.AsyncClient) -> TestResult:
        """Send a single signal and measure latency."""
        signal = self._generate_signal()
        start_time = time.perf_counter()

        try:
            response = await client.post(
                f"{self.target_url}/api/v1/signals",
                json=signal,
                timeout=30.0,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code == 201:
                data = response.json()
                return TestResult(
                    success=True,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    event_id=data.get("event_id"),
                )
            elif response.status_code == 429:
                # Rate limited - count as success but note it
                return TestResult(
                    success=True,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error="rate_limited",
                )
            else:
                return TestResult(
                    success=False,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}: {response.text[:100]}",
                )
        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return TestResult(
                success=False,
                status_code=0,
                latency_ms=latency_ms,
                error="timeout",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return TestResult(
                success=False,
                status_code=0,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def _worker(self, client: httpx.AsyncClient, interval_seconds: float):
        """Worker that sends signals at the specified rate."""
        while not self._stop_event.is_set():
            result = await self._send_signal(client)

            # Record stats
            self.stats.total_requests += 1
            self.stats.latencies.append(result.latency_ms)

            if result.success:
                self.stats.successful_requests += 1
            else:
                self.stats.failed_requests += 1
                if result.error:
                    self.stats.errors.append(result.error)

            # Wait for next interval
            await asyncio.sleep(interval_seconds)

    async def run(self) -> LoadTestStats:
        """Run the load test."""
        # Calculate interval between requests per worker
        requests_per_second = self.rate_per_min / 60
        total_interval = 1.0 / requests_per_second if requests_per_second > 0 else 1.0
        worker_interval = total_interval * self.concurrent_requests

        print(f"\n{'='*60}")
        print(f"SigmaPilot Lens Load Test")
        print(f"{'='*60}")
        print(f"Target URL: {self.target_url}")
        print(f"Target Rate: {self.rate_per_min} req/min ({requests_per_second:.2f} req/s)")
        print(f"Duration: {self.duration_seconds} seconds")
        print(f"Concurrent Workers: {self.concurrent_requests}")
        print(f"{'='*60}\n")

        self.stats = LoadTestStats()
        self.stats.start_time = time.time()
        self._stop_event.clear()

        async with httpx.AsyncClient() as client:
            # Verify target is reachable
            try:
                health_response = await client.get(
                    f"{self.target_url}/api/v1/health",
                    timeout=10.0,
                )
                if health_response.status_code != 200:
                    print(f"Warning: Health check returned {health_response.status_code}")
            except Exception as e:
                print(f"Error: Cannot reach target: {e}")
                return self.stats

            # Start workers
            workers = [
                asyncio.create_task(self._worker(client, worker_interval))
                for _ in range(self.concurrent_requests)
            ]

            # Run for duration
            print(f"Running load test for {self.duration_seconds} seconds...")
            progress_interval = max(10, self.duration_seconds // 10)
            elapsed = 0

            while elapsed < self.duration_seconds:
                await asyncio.sleep(min(progress_interval, self.duration_seconds - elapsed))
                elapsed = time.time() - self.stats.start_time
                current_rate = self.stats.total_requests / elapsed if elapsed > 0 else 0
                print(f"  [{elapsed:.0f}s] Requests: {self.stats.total_requests}, "
                      f"Rate: {current_rate * 60:.1f}/min, "
                      f"Success: {self.stats.success_rate:.1f}%")

            # Stop workers
            self._stop_event.set()
            for worker in workers:
                worker.cancel()

            try:
                await asyncio.gather(*workers, return_exceptions=True)
            except asyncio.CancelledError:
                pass

        self.stats.end_time = time.time()
        return self.stats

    def print_results(self):
        """Print test results."""
        print(f"\n{'='*60}")
        print(f"Load Test Results")
        print(f"{'='*60}")

        duration = self.stats.end_time - self.stats.start_time
        print(f"\nDuration: {duration:.1f} seconds")
        print(f"\nThroughput:")
        print(f"  Total Requests:     {self.stats.total_requests}")
        print(f"  Successful:         {self.stats.successful_requests}")
        print(f"  Failed:             {self.stats.failed_requests}")
        print(f"  Success Rate:       {self.stats.success_rate:.2f}%")
        print(f"  Actual Rate:        {self.stats.requests_per_second * 60:.1f} req/min")

        print(f"\nLatency (ms):")
        print(f"  Min:                {self.stats.min_latency:.1f}")
        print(f"  Avg:                {self.stats.avg_latency:.1f}")
        print(f"  p50 (Median):       {self.stats.p50_latency:.1f}")
        print(f"  p95:                {self.stats.p95_latency:.1f}")
        print(f"  p99:                {self.stats.p99_latency:.1f}")
        print(f"  Max:                {self.stats.max_latency:.1f}")

        # SLA checks
        print(f"\nSLA Verification:")
        rate_ok = self.stats.requests_per_second * 60 >= self.rate_per_min * 0.9
        p95_ok = self.stats.p95_latency < 1000  # 1s for enqueue operation
        success_ok = self.stats.success_rate >= 99.0

        print(f"  Rate >= {self.rate_per_min * 0.9:.0f}/min:   {'PASS' if rate_ok else 'FAIL'}")
        print(f"  p95 < 1000ms:       {'PASS' if p95_ok else 'FAIL'}")
        print(f"  Success >= 99%:     {'PASS' if success_ok else 'FAIL'}")

        if self.stats.errors:
            print(f"\nErrors (first 5):")
            for error in self.stats.errors[:5]:
                print(f"  - {error}")

        print(f"\n{'='*60}")

        # Return exit code
        return 0 if (rate_ok and p95_ok and success_ok) else 1


async def main():
    parser = argparse.ArgumentParser(description="Load test SigmaPilot Lens API")
    parser.add_argument(
        "--target",
        default="http://localhost:8000",
        help="Target URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=60,
        help="Target requests per minute (default: 60)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    tester = LoadTester(
        target_url=args.target,
        rate_per_min=args.rate,
        duration_seconds=args.duration,
        concurrent_requests=args.workers,
    )

    stats = await tester.run()

    if args.json:
        result = {
            "total_requests": stats.total_requests,
            "successful_requests": stats.successful_requests,
            "failed_requests": stats.failed_requests,
            "success_rate": stats.success_rate,
            "requests_per_minute": stats.requests_per_second * 60,
            "latency_ms": {
                "min": stats.min_latency,
                "avg": stats.avg_latency,
                "p50": stats.p50_latency,
                "p95": stats.p95_latency,
                "p99": stats.p99_latency,
                "max": stats.max_latency,
            },
            "duration_seconds": stats.end_time - stats.start_time,
        }
        print(json.dumps(result, indent=2))
        return 0
    else:
        return tester.print_results()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
