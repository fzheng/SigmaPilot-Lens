"""WebSocket endpoint for real-time decision streaming."""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.core.auth import AuthContext, get_websocket_auth_context, require_read, Scope
from src.core.config import settings
from src.observability.logging import get_logger
from src.services.publisher.ws_server import handle_websocket, ws_manager

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for streaming AI decisions in real-time.

    ## Authentication

    When AUTH_MODE is 'psk' or 'jwt', authenticate via the Sec-WebSocket-Protocol header:

    ```
    Sec-WebSocket-Protocol: bearer,<token>
    ```

    The server will echo back "bearer" in the response protocol if auth succeeds.
    Requires `lens:read` scope.

    ## Connection

    Connect to `ws://gateway:8000/api/v1/ws/stream` from within the Docker network.

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

    # Check authentication for WebSocket
    auth = await get_websocket_auth_context(websocket)
    if settings.AUTH_MODE != "none":
        if not auth.authenticated:
            await websocket.close(code=4001, reason="Authentication required")
            return
        if not auth.has_scope(Scope.READ):
            await websocket.close(code=4003, reason="Insufficient permissions")
            return

    # Check max connections
    if len(ws_manager.subscriptions) >= settings.WS_MAX_CONNECTIONS:
        await websocket.close(code=4029, reason="Too many connections")
        return

    # Handle the WebSocket connection
    # If auth was via bearer protocol, we need to accept with that subprotocol
    subprotocol = "bearer" if auth.token_type else None
    try:
        await handle_websocket(websocket, subprotocol=subprotocol)
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
