"""WebSocket server for real-time decision delivery."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from src.observability.logging import get_logger
from src.observability.metrics import metrics

logger = get_logger(__name__)


@dataclass
class Subscription:
    """WebSocket subscription with filters."""

    id: str
    websocket: WebSocket
    filters: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(self, decision: dict) -> bool:
        """Check if a decision matches this subscription's filters."""
        if not self.filters:
            return True  # No filters = subscribe to all

        for key, value in self.filters.items():
            if key == "model" and decision.get("model") != value:
                return False
            if key == "symbol" and decision.get("symbol") != value:
                return False
            if key == "event_type" and decision.get("event_type") != value:
                return False

        return True


class WebSocketManager:
    """Manages WebSocket connections and subscriptions."""

    def __init__(self):
        self.subscriptions: Dict[str, Subscription] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, subprotocol: Optional[str] = None) -> str:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            subprotocol: Optional subprotocol to echo back (e.g., "bearer" for auth)

        Returns:
            Subscription ID
        """
        await websocket.accept(subprotocol=subprotocol)

        sub_id = str(uuid4())
        subscription = Subscription(
            id=sub_id,
            websocket=websocket,
        )

        async with self._lock:
            self.subscriptions[sub_id] = subscription

        metrics.update_ws_connections(len(self.subscriptions))
        logger.info(f"WebSocket connected: {sub_id}")

        return sub_id

    async def disconnect(self, sub_id: str) -> None:
        """
        Remove a WebSocket connection.

        Args:
            sub_id: Subscription ID
        """
        async with self._lock:
            if sub_id in self.subscriptions:
                del self.subscriptions[sub_id]

        metrics.update_ws_connections(len(self.subscriptions))
        logger.info(f"WebSocket disconnected: {sub_id}")

    async def subscribe(
        self,
        sub_id: str,
        filters: Dict[str, str],
    ) -> None:
        """
        Update subscription filters.

        Args:
            sub_id: Subscription ID
            filters: Filter criteria (model, symbol, event_type)
        """
        async with self._lock:
            if sub_id in self.subscriptions:
                self.subscriptions[sub_id].filters = filters

        logger.info(f"Subscription updated: {sub_id}, filters={filters}")

    async def unsubscribe(self, sub_id: str) -> None:
        """
        Clear subscription filters (receive nothing until resubscribe).

        Args:
            sub_id: Subscription ID
        """
        async with self._lock:
            if sub_id in self.subscriptions:
                # Set impossible filter to effectively unsubscribe
                self.subscriptions[sub_id].filters = {"_unsubscribed": "true"}

        logger.info(f"Subscription cleared: {sub_id}")

    async def broadcast(self, decision: dict) -> int:
        """
        Broadcast a decision to matching subscribers.

        Args:
            decision: Decision payload to broadcast

        Returns:
            Number of subscribers notified
        """
        message = json.dumps({
            "type": "decision",
            **decision,
            "published_at": datetime.now(timezone.utc).isoformat(),
        })

        sent_count = 0
        failed_subs: List[str] = []

        async with self._lock:
            subs_snapshot = list(self.subscriptions.values())

        for sub in subs_snapshot:
            if sub.matches(decision):
                try:
                    await sub.websocket.send_text(message)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to {sub.id}: {e}")
                    failed_subs.append(sub.id)

        # Clean up failed connections
        for sub_id in failed_subs:
            await self.disconnect(sub_id)

        return sent_count

    async def send_error(
        self,
        sub_id: str,
        code: str,
        message: str,
    ) -> None:
        """
        Send an error message to a specific subscriber.

        Args:
            sub_id: Subscription ID
            code: Error code
            message: Error message
        """
        async with self._lock:
            sub = self.subscriptions.get(sub_id)

        if sub:
            try:
                await sub.websocket.send_json({
                    "type": "error",
                    "code": code,
                    "message": message,
                })
            except Exception as e:
                logger.warning(f"Failed to send error to {sub_id}: {e}")

    async def send_pong(self, sub_id: str) -> None:
        """Send pong response to a ping."""
        async with self._lock:
            sub = self.subscriptions.get(sub_id)

        if sub:
            try:
                await sub.websocket.send_json({"type": "pong"})
            except Exception:
                pass

    def get_stats(self) -> dict:
        """Get WebSocket server statistics."""
        filter_counts: Dict[str, int] = {
            "model": 0,
            "symbol": 0,
            "event_type": 0,
            "all": 0,
        }

        for sub in self.subscriptions.values():
            if not sub.filters:
                filter_counts["all"] += 1
            else:
                for key in ["model", "symbol", "event_type"]:
                    if key in sub.filters:
                        filter_counts[key] += 1

        return {
            "total_connections": len(self.subscriptions),
            "subscriptions_by_filter": filter_counts,
        }


# Global WebSocket manager instance
ws_manager = WebSocketManager()


async def handle_websocket(websocket: WebSocket, subprotocol: Optional[str] = None) -> None:
    """
    Handle a WebSocket connection lifecycle.

    Args:
        websocket: FastAPI WebSocket instance
        subprotocol: Optional subprotocol to echo back (e.g., "bearer" for auth)
    """
    sub_id = await ws_manager.connect(websocket, subprotocol=subprotocol)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            action = data.get("action")

            if action == "subscribe":
                filters = data.get("filters", {})
                # Validate filters
                valid_keys = {"model", "symbol", "event_type"}
                filters = {k: v for k, v in filters.items() if k in valid_keys}
                await ws_manager.subscribe(sub_id, filters)

            elif action == "unsubscribe":
                await ws_manager.unsubscribe(sub_id)

            elif data.get("type") == "ping":
                await ws_manager.send_pong(sub_id)

            else:
                await ws_manager.send_error(
                    sub_id,
                    "INVALID_ACTION",
                    f"Unknown action: {action}",
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for {sub_id}: {e}")
    finally:
        await ws_manager.disconnect(sub_id)
