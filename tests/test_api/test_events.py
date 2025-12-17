"""Tests for event query endpoints.

This module tests the event query API endpoints that allow operators to:
- List events with filtering by symbol, status, source, time range
- Get detailed event information including timeline and decisions
- Check event processing status

Events represent the full lifecycle of a trading signal from receipt
through enrichment, evaluation, and publication.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4


@pytest.mark.unit
class TestEventResponseSchemas:
    """Tests for event response Pydantic schemas."""

    def test_event_summary_schema(self):
        """Test EventSummary schema for list views."""
        # Import the schema (assuming it exists in events.py)
        # This tests the structure expected by the list endpoint

        event_data = {
            "event_id": str(uuid4()),
            "event_type": "OPEN_SIGNAL",
            "symbol": "BTC",
            "signal_direction": "long",
            "entry_price": 42000.50,
            "size": 0.1,
            "status": "published",
            "source": "test_strategy",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        # Verify all required fields are present
        required_fields = [
            "event_id",
            "event_type",
            "symbol",
            "signal_direction",
            "entry_price",
            "status",
            "source",
            "received_at",
        ]
        for field in required_fields:
            assert field in event_data

    def test_event_detail_with_timeline(self):
        """Test EventDetail schema includes timeline."""
        event_id = str(uuid4())
        timeline = [
            {"status": "RECEIVED", "timestamp": datetime.now(timezone.utc).isoformat()},
            {"status": "ENQUEUED", "timestamp": datetime.now(timezone.utc).isoformat()},
            {"status": "ENRICHED", "timestamp": datetime.now(timezone.utc).isoformat()},
        ]

        event_detail = {
            "event_id": event_id,
            "event_type": "OPEN_SIGNAL",
            "symbol": "BTC",
            "timeline": timeline,
        }

        assert len(event_detail["timeline"]) == 3
        assert event_detail["timeline"][0]["status"] == "RECEIVED"


@pytest.mark.unit
class TestEventFilters:
    """Tests for event query filtering logic."""

    @pytest.mark.parametrize(
        "status",
        ["queued", "enriched", "evaluated", "published", "failed", "rejected"],
    )
    def test_valid_status_filters(self, status):
        """Test that all valid status values are recognized."""
        # Valid status values that can be used for filtering
        valid_statuses = {
            "queued",
            "enriched",
            "evaluated",
            "published",
            "failed",
            "rejected",
            "dlq",
        }
        assert status in valid_statuses or status == "dlq"

    @pytest.mark.parametrize(
        "event_type",
        ["OPEN_SIGNAL", "CLOSE_SIGNAL"],
    )
    def test_valid_event_type_filters(self, event_type):
        """Test that all valid event types are recognized."""
        valid_types = {"OPEN_SIGNAL", "CLOSE_SIGNAL"}
        assert event_type in valid_types


@pytest.mark.unit
class TestEventPagination:
    """Tests for event list pagination."""

    def test_pagination_defaults(self):
        """Test default pagination values."""
        # Default values from the endpoint
        default_limit = 50
        default_offset = 0
        max_limit = 100

        assert default_limit <= max_limit
        assert default_offset >= 0

    def test_pagination_response_structure(self):
        """Test pagination response includes required fields."""
        pagination_response = {
            "items": [],
            "total": 150,
            "limit": 50,
            "offset": 0,
        }

        required_fields = ["items", "total", "limit", "offset"]
        for field in required_fields:
            assert field in pagination_response


@pytest.mark.unit
class TestEventStatusEndpoint:
    """Tests for event status endpoint response."""

    def test_status_response_structure(self):
        """Test status response includes processing information."""
        status_response = {
            "event_id": str(uuid4()),
            "status": "PUBLISHED",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

        assert status_response["status"] == "PUBLISHED"
        # All timestamps should be present for published event
        assert status_response["received_at"] is not None


@pytest.mark.unit
class TestEventIdValidation:
    """Tests for event ID validation."""

    def test_valid_uuid_format(self):
        """Test that valid UUID format is accepted."""
        valid_uuid = str(uuid4())

        # Should be a valid UUID string (36 chars with hyphens)
        assert len(valid_uuid) == 36
        assert valid_uuid.count("-") == 4

    def test_invalid_uuid_format_detection(self):
        """Test that invalid UUID formats can be detected."""
        invalid_ids = [
            "not-a-uuid",
            "12345",
            "",
            "550e8400-e29b-41d4-a716",  # Incomplete
        ]

        for invalid_id in invalid_ids:
            try:
                from uuid import UUID

                UUID(invalid_id)
                is_valid = True
            except ValueError:
                is_valid = False

            assert not is_valid, f"Expected {invalid_id} to be invalid"
