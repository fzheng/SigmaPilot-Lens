"""Tests for Dead Letter Queue (DLQ) endpoints.

This module tests the DLQ management API endpoints that allow operators to:
- List failed processing entries with filtering
- View detailed information about specific failures
- Retry failed entries by re-enqueueing them
- Mark entries as resolved when manually handled

The DLQ is a critical operational component that captures signals that failed
during any stage of processing (enqueue, enrich, evaluate, publish).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestDLQSchemas:
    """Tests for DLQ Pydantic schemas."""

    def test_dlq_entry_summary_schema(self):
        """Test DLQEntrySummary schema validation."""
        from src.api.v1.dlq import DLQEntrySummary

        entry = DLQEntrySummary(
            id=str(uuid4()),
            event_id="event-123",
            stage="enrich",
            reason_code="PROVIDER_ERROR",
            error_message="Hyperliquid API timeout",
            retry_count=3,
            created_at=datetime.now(timezone.utc),
            resolved_at=None,
        )

        assert entry.stage == "enrich"
        assert entry.retry_count == 3
        assert entry.resolved_at is None

    def test_dlq_entry_detail_schema(self):
        """Test DLQEntryDetail schema validation."""
        from src.api.v1.dlq import DLQEntryDetail

        entry = DLQEntryDetail(
            id=str(uuid4()),
            event_id="event-123",
            stage="evaluate",
            reason_code="MODEL_ERROR",
            error_message="ChatGPT rate limited",
            payload={"symbol": "BTC", "entry_price": 42000},
            retry_count=5,
            last_retry_at=datetime.now(timezone.utc),
            resolved_at=None,
            resolution_note=None,
            created_at=datetime.now(timezone.utc),
        )

        assert entry.payload["symbol"] == "BTC"
        assert entry.retry_count == 5

    def test_dlq_resolve_request_validation(self):
        """Test DLQResolveRequest requires non-empty note."""
        from pydantic import ValidationError
        from src.api.v1.dlq import DLQResolveRequest

        # Valid request
        request = DLQResolveRequest(resolution_note="Manually fixed data issue")
        assert len(request.resolution_note) > 0

        # Empty note should fail
        with pytest.raises(ValidationError):
            DLQResolveRequest(resolution_note="")

    def test_dlq_list_response_schema(self):
        """Test DLQListResponse pagination schema."""
        from src.api.v1.dlq import DLQListResponse, DLQEntrySummary

        response = DLQListResponse(
            items=[
                DLQEntrySummary(
                    id=str(uuid4()),
                    event_id="event-1",
                    stage="publish",
                    reason_code="WS_ERROR",
                    error_message="WebSocket disconnected",
                    retry_count=1,
                    created_at=datetime.now(timezone.utc),
                )
            ],
            total=100,
            limit=50,
            offset=0,
        )

        assert len(response.items) == 1
        assert response.total == 100


@pytest.mark.unit
class TestDLQRetryResponse:
    """Tests for DLQ retry response schema."""

    def test_retry_response_schema(self):
        """Test DLQRetryResponse schema."""
        from src.api.v1.dlq import DLQRetryResponse

        response = DLQRetryResponse(
            id=str(uuid4()),
            status="retrying",
            message="Entry re-enqueued for enrich processing",
            retry_count=4,
        )

        assert response.status == "retrying"
        assert response.retry_count == 4


@pytest.mark.unit
class TestDLQResolveResponse:
    """Tests for DLQ resolve response schema."""

    def test_resolve_response_schema(self):
        """Test DLQResolveResponse schema."""
        from src.api.v1.dlq import DLQResolveResponse

        now = datetime.now(timezone.utc)
        response = DLQResolveResponse(
            id=str(uuid4()),
            status="resolved",
            resolved_at=now,
        )

        assert response.status == "resolved"
        assert response.resolved_at == now


@pytest.mark.unit
class TestDLQValidStages:
    """Tests for valid DLQ stage values."""

    @pytest.mark.parametrize(
        "stage",
        ["enqueue", "enrich", "evaluate", "publish"],
    )
    def test_valid_stages(self, stage):
        """Test that all valid stages are accepted."""
        from src.api.v1.dlq import DLQEntrySummary

        entry = DLQEntrySummary(
            id=str(uuid4()),
            event_id="event-123",
            stage=stage,
            reason_code="TEST_ERROR",
            error_message="Test error",
            retry_count=0,
            created_at=datetime.now(timezone.utc),
        )

        assert entry.stage == stage


@pytest.mark.unit
class TestDLQErrorMessageTruncation:
    """Test that long error messages are handled properly."""

    def test_long_error_message(self):
        """Test that very long error messages can be stored."""
        from src.api.v1.dlq import DLQEntryDetail

        # Create a very long error message (e.g., from a stack trace)
        long_message = "Error: " + "x" * 10000

        entry = DLQEntryDetail(
            id=str(uuid4()),
            event_id="event-123",
            stage="enrich",
            reason_code="EXCEPTION",
            error_message=long_message,
            payload={},
            retry_count=0,
            created_at=datetime.now(timezone.utc),
        )

        assert len(entry.error_message) > 1000  # Full message stored
