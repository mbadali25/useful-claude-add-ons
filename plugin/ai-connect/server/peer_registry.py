"""Registry of the peers connected to the Bridge."""

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

PeerCallback = Callable[["Peer"], Awaitable[None]]


class NameTakenError(Exception):
    """The name belongs to a live connection, or to another credential."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Peer:
    """A connected peer."""
    name: str
    ip: str
    connected_at: str
    websocket: Any = None
    last_ping: datetime = field(default_factory=utc_now)
    # Reported by the peer itself: state ("busy", "idle", "waiting") with
    # an optional detail (e.g. what it waits for), and a free status line
    state: str = ""
    state_detail: str = ""
    state_since: str = ""
    status: str = ""
    # Which token registered the name (roles.Identity.credential), never the token
    credential: str = ""


class PeerRegistry:
    """Keeps track of all connected peers."""

    def __init__(self, timeout_seconds: int = 300):
        self._peers: dict[str, Peer] = {}
        self._timeout = timeout_seconds
        self._on_join: PeerCallback | None = None
        self._on_leave: PeerCallback | None = None

    def on_join(self, callback: PeerCallback) -> None:
        self._on_join = callback

    def on_leave(self, callback: PeerCallback) -> None:
        self._on_leave = callback

    async def register(self, name: str, ip: str, websocket: Any, credential: str) -> Peer:
        """Register a peer under the name it sent ("Host:Project").

        A name held by a live connection is not taken over: NameTakenError.
        A dead holder (closed, or silent past the timeout) is replaced, but
        only by the same credential, so a reconnect gets its name back and
        nobody else can grab it in the gap.
        """
        existing = self._peers.get(name)
        if existing is not None:
            if self.is_live(existing):
                raise NameTakenError(name)
            if existing.credential != credential:
                raise NameTakenError(name)
            del self._peers[name]
            if existing.websocket:
                with suppress(ConnectionClosed):
                    await existing.websocket.close()

        peer = Peer(
            name=name,
            ip=ip,
            connected_at=utc_now().isoformat(),
            websocket=websocket,
            credential=credential,
        )
        self._peers[name] = peer
        if self._on_join:
            await self._on_join(peer)
        return peer

    def is_live(self, peer: Peer) -> bool:
        """Whether the peer's connection is open and it pinged within the timeout."""
        if peer.websocket is None or getattr(peer.websocket, "state", None) is not State.OPEN:
            return False
        return (utc_now() - peer.last_ping).total_seconds() <= self._timeout

    async def unregister(self, name: str) -> None:
        peer = self._peers.pop(name, None)
        if peer and self._on_leave:
            await self._on_leave(peer)

    def get(self, name: str) -> Peer | None:
        """Peer by its full name ("Host:Project")."""
        return self._peers.get(name)

    def all(self) -> list[Peer]:
        return list(self._peers.values())

    def update_ping(self, name: str) -> None:
        """Record that the peer itself sent a ping."""
        if name in self._peers:
            self._peers[name].last_ping = utc_now()

    async def cleanup_stale(self) -> list[str]:
        """Remove peers that have not pinged for longer than the timeout."""
        now = utc_now()
        stale = [
            name for name, peer in self._peers.items()
            if (now - peer.last_ping).total_seconds() > self._timeout
        ]
        for name in stale:
            await self.unregister(name)
        return stale
