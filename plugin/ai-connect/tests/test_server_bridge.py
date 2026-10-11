"""End-to-end: a real Bridge on a free port, real websocket clients."""

import asyncio
import json
import logging

import test_server_harness as h

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus

from server import websocket_server as ws_server
from server.limits import Limits
from test_server_harness import connect, recv, recv_type, register, running_bridge, send


def run(coro):
    return asyncio.run(coro)


# --- handshake -------------------------------------------------------------

@pytest.mark.parametrize("token", ["wrong", h.SHARED_TOKEN])
def test_handshake_refuses_unknown_and_disabled_shared_token(tmp_path, token, caplog):
    async def go():
        async with running_bridge(tmp_path) as server:
            with pytest.raises(InvalidStatus) as err:
                async with connect(server, token):
                    pass
            assert err.value.response.status_code == 401

    with caplog.at_level(logging.WARNING):
        run(go())
    assert token not in caplog.text


def test_shared_token_on_registers_and_warns(tmp_path, caplog):
    async def go():
        async with running_bridge(tmp_path, allow_shared_token=True) as server:
            async with connect(server, h.SHARED_TOKEN) as ws:
                return await register(ws, "Other:Project")

    with caplog.at_level(logging.WARNING):
        frame = run(go())
    assert frame == {"type": "registered", "name": "Other:Project"}
    assert "shared_token_used" in caplog.text
    assert h.SHARED_TOKEN not in caplog.text


# --- names -----------------------------------------------------------------

def test_happy_register_and_message(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as alice, connect(server, h.BOB_TOKEN) as bob:
                assert (await register(alice, h.ALICE))["type"] == "registered"
                assert (await register(bob, h.BOB))["type"] == "registered"
                await send(alice, type="message", to=h.BOB, content="hi")
                return await recv_type(bob, "message")

    frame = run(go())
    assert (frame["from"], frame["content"]) == (h.ALICE, "hi")


def test_wrong_name_for_token_refused(tmp_path, caplog):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                return await register(ws, h.BOB)

    with caplog.at_level(logging.WARNING):
        frame = run(go())
    assert frame["type"] == "error"
    assert frame["code"] == "name_not_bound_to_token"
    assert "name_not_bound_to_token" in caplog.text
    assert h.ALICE_TOKEN not in caplog.text


@pytest.mark.parametrize("name", ["Bridge", "bridge", "User:max"])
def test_reserved_names_refused(tmp_path, name):
    async def go():
        async with running_bridge(tmp_path, allow_shared_token=True) as server:
            async with connect(server, h.SHARED_TOKEN) as ws:
                return await register(ws, name)

    frame = run(go())
    assert (frame["type"], frame["code"]) == ("error", "reserved_name")


def test_live_name_cannot_be_taken_over(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as first, connect(server, h.ALICE_TOKEN) as second:
                assert (await register(first, h.ALICE))["type"] == "registered"
                refused = await register(second, h.ALICE)
                # The first connection keeps the name and hears nothing
                assert await h.nothing_arrives(first)
                await send(first, type="list_peers")
                peers = await recv_type(first, "peer_list")
                return refused, peers

    refused, peers = run(go())
    assert (refused["type"], refused["code"]) == ("error", "name_taken")
    assert [p["name"] for p in peers["peers"]] == [h.ALICE]


def test_standby_then_name_free_after_holder_leaves(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as second:
                async with connect(server, h.ALICE_TOKEN) as first:
                    await register(first, h.ALICE)
                    assert (await register(second, h.ALICE, standby=True))["type"] == "standby"
                free = await recv_type(second, "name_free")
                return free, await register(second, h.ALICE, standby=True)

    free, again = run(go())
    assert free["name"] == h.ALICE
    assert again["type"] == "registered"


def test_reconnect_after_close_gets_name(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as first:
                await register(first, h.ALICE)
            await asyncio.sleep(0.1)
            async with connect(server, h.ALICE_TOKEN) as second:
                return await register(second, h.ALICE)

    assert run(go())["type"] == "registered"


# --- reading others' messages ------------------------------------------------

def test_peer_cannot_watch_another_peer(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await send(ws, type="watch", peer=h.BOB)
                refused = await recv(ws)
                await send(ws, type="watch", peer=h.ALICE)
                ok = await recv(ws)
                return refused, ok

    refused, ok = run(go())
    assert (refused["type"], refused["code"]) == ("error", "watch_not_own_name")
    assert ok == {"type": "watching", "peer": h.ALICE}


@pytest.mark.parametrize("msg_type", ["observe", "history_all"])
def test_peer_cannot_observe(tmp_path, msg_type):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await send(ws, type=msg_type, since="2000-01-01", limit=10)
                return await recv(ws)

    frame = run(go())
    assert (frame["type"], frame["code"]) == ("error", "role_not_allowed")


def test_observer_sees_messages(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.OBSERVER_TOKEN) as obs, connect(server, h.ALICE_TOKEN) as alice:
                await send(obs, type="observe")
                assert (await recv(obs))["type"] == "observing"
                await register(alice, h.ALICE)
                await send(alice, type="message", to=h.BOB, content="x")
                return await recv_type(obs, "observed")

    assert run(go())["content"] == "x"


def test_message_to_reserved_name_refused(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await register(ws, h.ALICE)
                await send(ws, type="message", to="Bridge", content="x")
                return await recv_type(ws, "error")

    assert run(go())["code"] == "reserved_name"


def test_peer_can_reply_to_user(tmp_path):
    """The documented reply path: peer_send(to="User:<name>") reaches the observers, unrefused."""
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.OBSERVER_TOKEN) as obs, connect(server, h.ALICE_TOKEN) as alice:
                await send(obs, type="observe")
                await recv_type(obs, "observing")
                await register(alice, h.ALICE)
                await send(alice, type="message", to="User:max", content="done")
                observed = await recv_type(obs, "observed")
                return observed, await h.nothing_arrives(alice)

    observed, quiet = run(go())
    assert (observed["to"], observed["content"]) == ("User:max", "done")
    assert quiet


@pytest.mark.parametrize("to", ["user:max", "User:", "User:a b", "BRIDGE"])
def test_message_to_malformed_reserved_name_refused(tmp_path, to):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await register(ws, h.ALICE)
                await send(ws, type="message", to=to, content="x")
                return await recv_type(ws, "error")

    assert run(go())["code"] == "reserved_name"


# --- offline queue -----------------------------------------------------------

FAST = {"rate_per_second": 1000, "rate_burst": 1000}


async def collect_unread(ws, count: int) -> list[dict]:
    """The unread frames until count messages have arrived."""
    frames, got = [], 0
    while got < count:
        frame = await recv_type(ws, "unread")
        frames.append(frame)
        got += len(frame["messages"])
    return frames


def test_offline_queue_capped_by_count(tmp_path, caplog):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_unread_per_peer=2, **FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                for i in range(2):
                    await send(alice, type="message", to=h.BOB, content=f"m{i}")
                assert await h.nothing_arrives(alice)
                await send(alice, type="message", to=h.BOB, content="S3CRET-overflow")
                refused = await recv_type(alice, "error")
            async with connect(server, h.BOB_TOKEN) as bob:
                await register(bob, h.BOB)
                frames = await collect_unread(bob, 2)
                return refused, frames, await h.nothing_arrives(bob)

    with caplog.at_level(logging.WARNING):
        refused, frames, quiet = run(go())
    assert refused["code"] == "recipient_queue_full"
    assert [m["content"] for f in frames for m in f["messages"]] == ["m0", "m1"]
    assert quiet
    assert "recipient_queue_full" in caplog.text
    assert "S3CRET" not in caplog.text


def test_offline_queue_capped_by_bytes(tmp_path):
    async def go():
        limits = Limits(max_unread_bytes_per_peer=1000, **FAST)
        async with running_bridge(tmp_path, limits=limits) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                await send(alice, type="message", to=h.BOB, content="x" * 600)
                assert await h.nothing_arrives(alice)
                await send(alice, type="message", to=h.BOB, content="y" * 600)
                return await recv_type(alice, "error")

    assert run(go())["code"] == "recipient_queue_full"


def test_cap_does_not_apply_to_online_recipient(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_unread_per_peer=1, **FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice, connect(server, h.BOB_TOKEN) as bob:
                # Bob first, so Alice hears no peer_joined
                await register(bob, h.BOB)
                await register(alice, h.ALICE)
                for i in range(3):
                    await send(alice, type="message", to=h.BOB, content=f"m{i}")
                got = [(await recv_type(bob, "message"))["content"] for _ in range(3)]
                return got, await h.nothing_arrives(alice)

    got, quiet = run(go())
    assert got == ["m0", "m1", "m2"]
    assert quiet


def test_unread_over_a_mebibyte_arrives_in_frames_the_client_accepts(tmp_path):
    """20 x 60 KB waits for Bob; the default client (max_size 1 MiB) must get all of it."""
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                for i in range(20):
                    await send(alice, type="message", to=h.BOB, content=f"{i:02d}" + "x" * 60_000)
                # A connection's frames are handled in order: the pong means all 20 are stored,
                # so none can arrive live as a "message" once Bob registers
                await send(alice, type="ping")
                await recv_type(alice, "pong", timeout=10)
            async with connect(server, h.BOB_TOKEN) as bob:
                await register(bob, h.BOB)
                return await collect_unread(bob, 20)

    frames = run(go())
    assert len(frames) > 1
    assert [m["content"][:2] for f in frames for m in f["messages"]] == [f"{i:02d}" for i in range(20)]
    assert all(len(json.dumps(f).encode()) <= 1 << 20 for f in frames)


def test_user_send_to_full_queue_reports_per_recipient(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_unread_per_peer=1, **FAST)) as server:
            async with connect(server, h.USER_TOKEN) as user:
                answers = []
                for _ in range(2):
                    await send(user, type="user_send", **{"as": "max"}, to=[h.BOB], content="x")
                    answers.append(await recv_type(user, "user_sent"))
                return answers

    first, second = run(go())
    assert first["sent"][0]["id"] and "code" not in first["sent"][0]
    assert second["sent"][0]["code"] == "recipient_queue_full"
    assert second["sent"][0]["id"] is None


def test_unread_chunks_edges():
    assert ws_server._unread_chunks([]) == []  # pylint: disable=protected-access
    big = {"id": "1", "content": "x" * (ws_server.UNREAD_FRAME_MAX_BYTES + 10)}
    small = {"id": "2", "content": "y"}
    assert ws_server._unread_chunks([small, big, small]) == [[small], [big], [small]]  # pylint: disable=protected-access


class FailingSocket:
    """Accepts the first send, then the connection is gone."""

    def __init__(self):
        self.sent: list[str] = []

    async def send(self, payload):
        if self.sent:
            raise ConnectionClosed(None, None)
        self.sent.append(payload)


def test_unread_marked_delivered_only_once_sent(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            for i in range(3):
                await server.store.store(h.ALICE, h.BOB, f"{i}" + "x" * 400_000, None, delivered=False)
            ws = FailingSocket()
            with pytest.raises(ConnectionClosed):
                await server._deliver_unread(ws, h.BOB)  # pylint: disable=protected-access
            first = json.loads(ws.sent[0])["messages"]
            return first, await server.store.get_unread(h.BOB)

    first, left = run(go())
    assert first and left
    assert {m["id"] for m in first}.isdisjoint(m["id"] for m in left)
    assert len(first) + len(left) == 3


# --- limits ----------------------------------------------------------------

def test_oversize_message_refused_without_closing(tmp_path, caplog):
    body = "S3CRET-" + "x" * 2000

    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_message_bytes=1000)) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await register(ws, h.ALICE)
                await send(ws, type="message", to=h.BOB, content=body)
                refused = await recv(ws)
                await send(ws, type="ping")
                return refused, await recv(ws)

    with caplog.at_level(logging.WARNING):
        refused, pong = run(go())
    assert (refused["type"], refused["code"]) == ("error", "message_too_large")
    assert pong == {"type": "pong"}
    assert "message_too_large" in caplog.text
    assert "S3CRET" not in caplog.text


def test_message_at_limit_accepted(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_message_bytes=100)) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                frame = '{"type": "ping"}'
                await ws.send(frame + " " * (100 - len(frame)))
                return await recv(ws)

    assert run(go()) == {"type": "pong"}


def test_multibyte_counted_in_bytes(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(max_message_bytes=100)) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                # 40 characters, 120 bytes
                await send(ws, type="ping", pad="€" * 40)
                return await recv(ws)

    assert run(go())["code"] == "message_too_large"


def test_rate_burst_refused(tmp_path, caplog):
    clock = h.FrozenClock()

    async def go():
        limits = Limits(rate_per_second=1, rate_burst=3)
        async with running_bridge(tmp_path, limits=limits, clock=clock) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                frames = []
                for _ in range(5):
                    await send(ws, type="ping")
                    frames.append(await recv(ws))
                clock.now += 1
                await send(ws, type="ping")
                frames.append(await recv(ws))
                return frames

    with caplog.at_level(logging.WARNING):
        frames = run(go())
    assert [f["type"] for f in frames] == ["pong", "pong", "pong", "error", "error", "pong"]
    assert frames[3]["code"] == "rate_limited"
    # One log line per run of refusals, not one per refused frame
    assert caplog.text.count("rate_limited") == 1


def test_rate_limit_is_per_connection(tmp_path):
    clock = h.FrozenClock()

    async def go():
        limits = Limits(rate_per_second=1, rate_burst=1)
        async with running_bridge(tmp_path, limits=limits, clock=clock) as server:
            async with connect(server, h.ALICE_TOKEN) as a, connect(server, h.BOB_TOKEN) as b:
                await send(a, type="ping")
                await send(b, type="ping")
                return await recv(a), await recv(b)

    assert run(go()) == ({"type": "pong"}, {"type": "pong"})


# --- Codex QA: delivery is marked only once it happened; idle subscriptions are bounded ---


class _DeadSocket:
    """A registry entry whose connection closed before the heartbeat noticed."""

    async def send(self, _payload):
        raise ConnectionClosed(None, None)

    async def close(self):
        return None


def test_direct_message_to_a_closed_socket_stays_unread(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            await server.registry.register(h.BOB, "127.0.0.1", _DeadSocket(), "bob-credential")
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                await send(alice, type="message", to=h.BOB, content="did you get this?")
                await send(alice, type="ping")
                await recv_type(alice, "pong")
            return await server.store.get_unread(h.BOB)

    unread = run(go())
    assert [m["content"] for m in unread] == ["did you get this?"]


def test_direct_message_to_a_live_peer_is_marked_delivered(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            async with connect(server, h.BOB_TOKEN) as bob, connect(server, h.ALICE_TOKEN) as alice:
                await register(bob, h.BOB)
                await register(alice, h.ALICE)
                await send(alice, type="message", to=h.BOB, content="hi")
                got = await recv_type(bob, "message")
                await send(alice, type="ping")
                await recv_type(alice, "pong")
                return got, await server.store.get_unread(h.BOB)

    got, unread = run(go())
    assert got["content"] == "hi"
    assert unread == []


def test_idle_subscriptions_per_peer_are_capped(tmp_path, caplog):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                for i in range(ws_server.MAX_IDLE_SUBSCRIPTIONS_PER_PEER):
                    await send(alice, type="notify_when_idle", peer=f"Ghost:{i}")
                with caplog.at_level(logging.WARNING):
                    await send(alice, type="notify_when_idle", peer="Ghost:one-too-many")
                    refused = await recv_type(alice, "error")
                held = sum(h.ALICE in subs for subs in server._idle_subscribers.values())  # pylint: disable=protected-access
                return refused, held

    refused, held = run(go())
    assert refused["code"] == "too_many_subscriptions"
    assert held == ws_server.MAX_IDLE_SUBSCRIPTIONS_PER_PEER
    assert "too_many_subscriptions" in caplog.text


def test_idle_subscriptions_end_with_the_subscriber(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                await send(alice, type="notify_when_idle", peer="Ghost:1")
                await send(alice, type="ping")
                await recv_type(alice, "pong")
                assert server._idle_subscribers  # pylint: disable=protected-access
            for _ in range(50):
                if not server._idle_subscribers:  # pylint: disable=protected-access
                    break
                await asyncio.sleep(0.02)
            return dict(server._idle_subscribers)  # pylint: disable=protected-access

    assert run(go()) == {}


def test_notify_when_idle_with_a_non_string_peer_is_refused(tmp_path):
    async def go():
        async with running_bridge(tmp_path, limits=Limits(**FAST)) as server:
            async with connect(server, h.ALICE_TOKEN) as alice:
                await register(alice, h.ALICE)
                await send(alice, type="notify_when_idle", peer={"not": "a name"})
                error = await recv_type(alice, "error")
                await send(alice, type="ping")
                return error, await recv_type(alice, "pong")

    error, pong = run(go())
    assert "notify_when_idle" in error["error"]
    assert pong["type"] == "pong"  # the connection survived
