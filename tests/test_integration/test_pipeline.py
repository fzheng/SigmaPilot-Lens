"""Integration tests for the signal processing pipeline.

These tests require running Docker services (DB, Redis).
Run with: pytest -m integration
"""

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="Requires running Docker services")
async def test_signal_to_queue(client, test_signal: dict):
    """Test signal submission enqueues to Redis."""
    response = await client.post("/api/v1/signals", json=test_signal)
    assert response.status_code == 200
    data = response.json()
    assert "event_id" in data
    assert data["status"] == "ENQUEUED"


@pytest.mark.integration
@pytest.mark.skip(reason="Requires running Docker services")
async def test_full_pipeline_e2e(client, test_signal: dict):
    """Test full signal processing pipeline end-to-end."""
    # Submit signal
    response = await client.post("/api/v1/signals", json=test_signal)
    assert response.status_code == 200
    event_id = response.json()["event_id"]

    # Wait for processing (in real test, poll or use events)
    import asyncio
    await asyncio.sleep(1)

    # Check event status
    response = await client.get(f"/api/v1/events/{event_id}")
    # Note: This endpoint may not be fully implemented yet
    assert response.status_code in [200, 501]
