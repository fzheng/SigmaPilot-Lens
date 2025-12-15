"""API v1 router aggregation."""

from fastapi import APIRouter

from src.api.v1 import decisions, events, health, keys, signals, ws

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(signals.router, prefix="/signals", tags=["Signals"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(decisions.router, prefix="/decisions", tags=["Decisions"])
api_router.include_router(keys.router, prefix="/keys", tags=["API Keys"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
