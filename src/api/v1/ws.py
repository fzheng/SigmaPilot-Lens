"""WebSocket endpoint for real-time decision streaming."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from src.core.config import settings
from src.observability.logging import get_logger
from src.services.publisher.ws_server import handle_websocket, ws_manager

logger = get_logger(__name__)

router = APIRouter()


async def validate_ws_api_key(
    api_key: Optional[str] = Query(None, alias="api_key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Validate API key for WebSocket connections.

    Accepts API key via query parameter or header.
    Query parameter is needed because browsers can't set custom headers on WebSocket.
    """
    key = api_key or x_api_key

    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key (use api_key query param or X-API-Key header)",
        )

    # For Phase 1, only accept admin key
    if key != settings.API_KEY_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return key


@router.websocket("/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None, alias="api_key"),
):
    """
    WebSocket endpoint for streaming AI decisions in real-time.

    ## Connection

    Connect to `/api/v1/ws/stream?api_key=YOUR_API_KEY`

    ## Messages

    ### Subscribe to decisions

    ```json
    {
        "action": "subscribe",
        "filters": {
            "model": "chatgpt",      // optional
            "symbol": "BTC-PERP",    // optional
            "event_type": "OPEN_SIGNAL"  // optional
        }
    }
    ```

    ### Unsubscribe

    ```json
    {"action": "unsubscribe"}
    ```

    ### Ping/Pong (keepalive)

    ```json
    {"type": "ping"}
    ```

    Response: `{"type": "pong"}`

    ## Decision Message Format

    ```json
    {
        "type": "decision",
        "event_id": "uuid",
        "symbol": "BTC-PERP",
        "event_type": "OPEN_SIGNAL",
        "model": "chatgpt",
        "decision": {
            "decision": "FOLLOW_ENTER",
            "confidence": 0.78,
            "entry_plan": {...},
            "risk_plan": {...},
            "size_pct": 15,
            "reasons": ["bullish_trend", "ema_bullish_stack"],
            "model_meta": {...}
        },
        "published_at": "2024-01-15T10:30:00Z"
    }
    ```
    """
    if not settings.WS_ENABLED:
        await websocket.close(code=1000, reason="WebSocket disabled")
        return

    # Validate API key (from query param for WebSocket)
    if not api_key:
        await websocket.close(code=4001, reason="Missing API key")
        return

    if api_key != settings.API_KEY_ADMIN:
        await websocket.close(code=4003, reason="Invalid API key")
        return

    # Check max connections
    if len(ws_manager.subscriptions) >= settings.WS_MAX_CONNECTIONS:
        await websocket.close(code=4029, reason="Too many connections")
        return

    # Handle the WebSocket connection
    try:
        await handle_websocket(websocket, api_key)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@router.get("/stream/stats", summary="Get WebSocket connection statistics")
async def get_ws_stats():
    """
    Get current WebSocket connection statistics.

    Returns connection counts and subscription breakdown.
    """
    return ws_manager.get_stats()
