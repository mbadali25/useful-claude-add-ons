"""Observers of the Bridge: read-only connections that see every message and who is online."""

import json

import websockets
from websockets.asyncio.server import ServerConnection


class Observers:
    """Connections that get a copy of every message the Bridge stores."""

    def __init__(self) -> None:
        self._connections: set[ServerConnection] = set()

    def add(self, connection: ServerConnection) -> None:
        self._connections.add(connection)

    def discard(self, connection: ServerConnection) -> None:
        self._connections.discard(connection)

    async def broadcast(self, message: dict) -> None:
        """Send a stored message to every observer."""
        await self._send(json.dumps({**message, "type": "observed"}))

    async def peers_changed(self, peers: list[dict]) -> None:
        """Send the peer list after a peer joined or left."""
        await self._send(json.dumps({"type": "peers_changed", "peers": peers}))

    async def _send(self, payload: str) -> None:
        for connection in list(self._connections):
            try:
                await connection.send(payload)
            except websockets.exceptions.ConnectionClosed:
                self._connections.discard(connection)
