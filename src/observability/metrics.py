"""Prometheus metrics for observability."""

from prometheus_client import Counter, Histogram, Gauge, Info, REGISTRY, generate_latest
from typing import Optional


class MetricsCollector:
    """Centralized metrics collection for SigmaPilot Lens."""

    def __init__(self):
        # Application info
        self.app_info = Info(
            "lens_app",
            "Application information",
        )

        # Signal counters
        self.signals_received = Counter(
            "lens_signals_received_total",
            "Total signals received",
            ["source", "symbol", "event_type"],
        )
        self.signals_enqueued = Counter(
            "lens_signals_enqueued_total",
            "Total signals enqueued",
            ["symbol"],
        )
        self.signals_enriched = Counter(
            "lens_signals_enriched_total",
            "Total signals enriched",
            ["profile", "symbol"],
        )
        self.signals_evaluated = Counter(
            "lens_signals_evaluated_total",
            "Total signals evaluated by AI",
            ["model", "symbol", "decision"],
        )
        self.signals_published = Counter(
            "lens_signals_published_total",
            "Total decisions published",
            ["model"],
        )

        # DLQ counter
        self.dlq_entries = Counter(
            "lens_dlq_entries_total",
            "Total DLQ entries",
            ["stage", "error_code"],
        )

        # Latency histograms
        self.enqueue_duration = Histogram(
            "lens_signal_enqueue_duration_seconds",
            "Time to enqueue signal",
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )
        self.enrichment_duration = Histogram(
            "lens_enrichment_duration_seconds",
            "Time to enrich signal",
            ["profile"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
        )
        self.model_evaluation_duration = Histogram(
            "lens_model_evaluation_duration_seconds",
            "Time to evaluate with AI model",
            ["model"],
            buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0],
        )
        self.end_to_end_duration = Histogram(
            "lens_end_to_end_duration_seconds",
            "Total time from receive to publish",
            buckets=[1.0, 2.0, 3.0, 5.0, 6.0, 10.0, 15.0],
        )
        self.websocket_fanout_duration = Histogram(
            "lens_websocket_fanout_duration_seconds",
            "Time to broadcast to subscribers",
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )

        # Queue gauges
        self.queue_depth = Gauge(
            "lens_queue_depth",
            "Current queue depth",
            ["queue"],
        )
        self.pending_enrichment = Gauge(
            "lens_pending_enrichment",
            "Signals pending enrichment",
        )
        self.pending_evaluation = Gauge(
            "lens_pending_evaluation",
            "Signals pending AI evaluation",
        )

        # WebSocket gauges
        self.active_ws_connections = Gauge(
            "lens_active_websocket_connections",
            "Active WebSocket connections",
        )
        self.ws_subscriptions = Gauge(
            "lens_websocket_subscriptions",
            "Active WebSocket subscriptions",
            ["filter_type"],
        )

        # Worker health
        self.worker_heartbeat = Gauge(
            "lens_worker_heartbeat_timestamp",
            "Last worker heartbeat timestamp",
            ["worker_type"],
        )

        # Model-specific metrics
        self.model_errors = Counter(
            "lens_model_errors_total",
            "AI model errors by type",
            ["model", "error_type"],
        )
        self.model_tokens = Counter(
            "lens_model_tokens_total",
            "Tokens used by model",
            ["model", "direction"],  # direction: input/output
        )
        self.model_invalid_outputs = Counter(
            "lens_model_invalid_outputs_total",
            "Invalid JSON outputs from models",
            ["model"],
        )

        # Provider metrics
        self.provider_requests = Counter(
            "lens_provider_requests_total",
            "Data provider requests",
            ["provider", "endpoint", "status"],
        )
        self.provider_latency = Histogram(
            "lens_provider_latency_seconds",
            "Data provider latency",
            ["provider", "endpoint"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
        )

    def set_app_info(self, version: str, feature_profile: str, ai_models: str):
        """Set application info labels."""
        self.app_info.info({
            "version": version,
            "feature_profile": feature_profile,
            "ai_models": ai_models,
        })

    def record_signal_received(self, source: str, symbol: str, event_type: str):
        """Record a signal received."""
        self.signals_received.labels(
            source=source, symbol=symbol, event_type=event_type
        ).inc()

    def record_signal_enqueued(self, symbol: str, duration_seconds: float):
        """Record a signal enqueued."""
        self.signals_enqueued.labels(symbol=symbol).inc()
        self.enqueue_duration.observe(duration_seconds)

    def record_enrichment(self, profile: str, symbol: str, duration_seconds: float):
        """Record enrichment completion."""
        self.signals_enriched.labels(profile=profile, symbol=symbol).inc()
        self.enrichment_duration.labels(profile=profile).observe(duration_seconds)

    def record_evaluation(
        self,
        model: str,
        symbol: str,
        decision: str,
        duration_seconds: float,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
    ):
        """Record AI model evaluation."""
        self.signals_evaluated.labels(model=model, symbol=symbol, decision=decision).inc()
        self.model_evaluation_duration.labels(model=model).observe(duration_seconds)
        if tokens_in:
            self.model_tokens.labels(model=model, direction="input").inc(tokens_in)
        if tokens_out:
            self.model_tokens.labels(model=model, direction="output").inc(tokens_out)

    def record_publish(self, model: str, fanout_duration_seconds: float):
        """Record decision published."""
        self.signals_published.labels(model=model).inc()
        self.websocket_fanout_duration.observe(fanout_duration_seconds)

    def record_end_to_end(self, duration_seconds: float):
        """Record end-to-end latency."""
        self.end_to_end_duration.observe(duration_seconds)

    def record_dlq(self, stage: str, error_code: str):
        """Record DLQ entry."""
        self.dlq_entries.labels(stage=stage, error_code=error_code).inc()

    def record_model_error(self, model: str, error_type: str):
        """Record model error."""
        self.model_errors.labels(model=model, error_type=error_type).inc()

    def record_invalid_output(self, model: str):
        """Record invalid model output."""
        self.model_invalid_outputs.labels(model=model).inc()

    def record_provider_request(
        self,
        provider: str,
        endpoint: str,
        status: str,
        duration_seconds: float,
    ):
        """Record provider request."""
        self.provider_requests.labels(
            provider=provider, endpoint=endpoint, status=status
        ).inc()
        self.provider_latency.labels(
            provider=provider, endpoint=endpoint
        ).observe(duration_seconds)

    def update_queue_depth(self, queue: str, depth: int):
        """Update queue depth gauge."""
        self.queue_depth.labels(queue=queue).set(depth)

    def update_ws_connections(self, count: int):
        """Update WebSocket connection count."""
        self.active_ws_connections.set(count)

    def update_worker_heartbeat(self, worker_type: str):
        """Update worker heartbeat timestamp."""
        import time
        self.worker_heartbeat.labels(worker_type=worker_type).set(time.time())

    def get_metrics(self) -> bytes:
        """Get all metrics in Prometheus format."""
        return generate_latest(REGISTRY)


# Global metrics instance
metrics = MetricsCollector()
