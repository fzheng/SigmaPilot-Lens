"""Structured logging configuration."""

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pythonjsonlogger import jsonlogger

from src.core.config import settings


class LensJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with Lens-specific fields."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Add standard fields
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = "sigmapilot-lens"

        # Add location info
        if record.pathname:
            log_record["file"] = f"{record.pathname}:{record.lineno}"

        # Remove redundant fields
        for field in ["asctime", "levelname", "name"]:
            log_record.pop(field, None)


class ContextFilter(logging.Filter):
    """Filter that adds context fields to log records."""

    _context: Dict[str, Any] = {}

    @classmethod
    def set_context(cls, **kwargs):
        """Set context fields that will be added to all logs."""
        cls._context.update(kwargs)

    @classmethod
    def clear_context(cls):
        """Clear all context fields."""
        cls._context.clear()

    @classmethod
    def set_event_id(cls, event_id: str):
        """Set the current event ID for tracing."""
        cls._context["event_id"] = event_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to the log record."""
        for key, value in self._context.items():
            setattr(record, key, value)
        return True


def setup_logging(
    level: Optional[str] = None,
    format_type: Optional[str] = None,
) -> None:
    """
    Set up structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ('json' or 'text')
    """
    level = level or settings.LOG_LEVEL
    format_type = format_type or settings.LOG_FORMAT

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    # Add context filter
    handler.addFilter(ContextFilter())

    # Set formatter based on format type
    if format_type.lower() == "json":
        formatter = LensJsonFormatter(
            "%(timestamp)s %(level)s %(logger)s %(message)s",
            rename_fields={"levelname": "level", "name": "logger"},
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for scoped logging context."""

    def __init__(self, **kwargs):
        self.context = kwargs
        self.previous_context: Dict[str, Any] = {}

    def __enter__(self):
        self.previous_context = ContextFilter._context.copy()
        ContextFilter.set_context(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ContextFilter._context = self.previous_context
        return False


# Convenience functions for structured logging
def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    event_id: Optional[str] = None,
    **extra,
) -> None:
    """
    Log a message with structured extra fields.

    Args:
        logger: Logger instance
        level: Log level
        message: Log message
        event_id: Optional event ID for tracing
        **extra: Additional fields to include
    """
    if event_id:
        extra["event_id"] = event_id
    logger.log(level, message, extra=extra)


def log_stage(
    logger: logging.Logger,
    stage: str,
    event_id: str,
    status: str = "started",
    **extra,
) -> None:
    """
    Log a processing stage transition.

    Args:
        logger: Logger instance
        stage: Stage name (RECEIVED, ENQUEUED, ENRICHED, etc.)
        event_id: Event ID for tracing
        status: Stage status (started, completed, failed)
        **extra: Additional fields
    """
    log_event(
        logger,
        logging.INFO,
        f"{stage} {status}",
        event_id=event_id,
        stage=stage,
        stage_status=status,
        **extra,
    )
