"""
WebSocket Manager — ResQnet Disaster Response Coordination System

Manages all active WebSocket connections and provides thread-safe broadcasting
of JSON messages to all connected clients.
"""

import json
import asyncio
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages a pool of active WebSocket connections.
    Provides safe broadcast and disconnect handling.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(
            "[WebSocketManager] New client connected. Total: %d",
            len(self.active_connections),
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the pool."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(
            "[WebSocketManager] Client disconnected. Total: %d",
            len(self.active_connections),
        )

    async def broadcast(self, data: dict) -> None:
        """
        Broadcast a JSON-serializable dict to ALL active connections.
        Dead connections are automatically removed.
        """
        if not self.active_connections:
            logger.debug("[WebSocketManager] No active connections — skipping broadcast.")
            return

        message = json.dumps(data, ensure_ascii=False, default=str)
        dead_connections: Set[WebSocket] = set()

        async with self._lock:
            targets = set(self.active_connections)

        for websocket in targets:
            try:
                await websocket.send_text(message)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[WebSocketManager] Failed to send to client, marking as dead: %s", exc
                )
                dead_connections.add(websocket)

        if dead_connections:
            async with self._lock:
                self.active_connections -= dead_connections
            logger.info(
                "[WebSocketManager] Removed %d dead connections. Remaining: %d",
                len(dead_connections),
                len(self.active_connections),
            )

    async def send_personal_message(self, data: dict, websocket: WebSocket) -> None:
        """
        Send a JSON message to a single specific WebSocket connection.
        """
        try:
            message = json.dumps(data, ensure_ascii=False, default=str)
            await websocket.send_text(message)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("[WebSocketManager] Failed personal message: %s", exc)
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Return the current number of active connections."""
        return len(self.active_connections)


# Singleton instance — imported and shared across the app
manager = ConnectionManager()
