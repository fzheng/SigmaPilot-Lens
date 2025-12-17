"""API v1 router aggregation."""

from fastapi import APIRouter

from src.api.v1 import decisions, dlq, events, health, signals, ws

api_router = APIRouter()

# Include all sub-routers
# Note: All endpoints (except health) are protected by network-level security
# Only requests from internal Docker network are allowed
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(signals.router, prefix="/signals", tags=["Signals"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(decisions.router, prefix="/decisions", tags=["Decisions"])
api_router.include_router(dlq.router, prefix="/dlq", tags=["DLQ"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
