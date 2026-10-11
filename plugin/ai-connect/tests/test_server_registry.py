"""PeerRegistry: a live name cannot be taken; a dead one can be reclaimed by its credential."""

import asyncio
from datetime import timedelta

import test_server_harness as h  # noqa: F401  (sets sys.path)  # pylint: disable=unused-import

import pytest
from websockets.protocol import State

from server.peer_registry import NameTakenError, PeerRegistry, utc_now


class FakeSocket:
    def __init__(self, state=State.OPEN):
        self.state = state
        self.sent: list[str] = []
        self.closed = False

    async def send(self, payload):
        self.sent.append(payload)

    async def close(self):
        self.closed = True


def test_live_holder_is_not_replaced():
    async def run():
        registry = PeerRegistry()
        first, second = FakeSocket(), FakeSocket()
        await registry.register("A:x", "1.1.1.1", first, credential="peer:A:x")
        with pytest.raises(NameTakenError):
            await registry.register("A:x", "2.2.2.2", second, credential="peer:A:x")
        assert registry.get("A:x").websocket is first
        assert not first.closed and first.sent == []

    asyncio.run(run())


def test_dead_holder_replaced_by_same_credential():
    async def run():
        registry = PeerRegistry()
        dead, fresh = FakeSocket(State.CLOSED), FakeSocket()
        await registry.register("A:x", "1.1.1.1", dead, credential="peer:A:x")
        await registry.register("A:x", "1.1.1.1", fresh, credential="peer:A:x")
        assert registry.get("A:x").websocket is fresh

    asyncio.run(run())


def test_stale_holder_counts_as_dead():
    async def run():
        registry = PeerRegistry(timeout_seconds=10)
        old, fresh = FakeSocket(), FakeSocket()
        await registry.register("A:x", "1.1.1.1", old, credential="shared")
        registry.get("A:x").last_ping = utc_now() - timedelta(seconds=11)
        await registry.register("A:x", "1.1.1.1", fresh, credential="shared")
        assert registry.get("A:x").websocket is fresh
        assert old.closed

    asyncio.run(run())


def test_dead_holder_not_reclaimed_by_other_credential():
    async def run():
        registry = PeerRegistry()
        await registry.register("A:x", "1.1.1.1", FakeSocket(State.CLOSED), credential="peer:A:x")
        with pytest.raises(NameTakenError):
            await registry.register("A:x", "1.1.1.1", FakeSocket(), credential="shared")

    asyncio.run(run())


def test_is_live():
    async def run():
        registry = PeerRegistry()
        peer = await registry.register("A:x", "1.1.1.1", FakeSocket(), credential="c")
        assert registry.is_live(peer)
        peer.websocket.state = State.CLOSING
        assert not registry.is_live(peer)

    asyncio.run(run())
