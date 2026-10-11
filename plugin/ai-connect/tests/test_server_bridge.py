"""End-to-end: a real Bridge on a free port, real websocket clients."""

import asyncio
import logging

import test_server_harness as h

import pytest
from websockets.exceptions import InvalidStatus

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
