"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_health_endpoint(client: AsyncClient):
    """Test /api/v1/health returns ok."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.unit
async def test_openapi_schema(client: AsyncClient):
    """Test OpenAPI schema is available."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
    assert "/api/v1/signals" in data["paths"]
