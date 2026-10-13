"""Several sessions per machine: one token per machine, one name per session.

A machine's token registers its bound name and any "<name>:<label>" under it.
Every test runs a real Bridge on a free port with real websocket clients.
"""

import asyncio

import test_server_harness as h

import pytest
from websockets.exceptions import ConnectionClosed

from server.roles import Roles, token_sha256
from test_server_harness import connect, recv, recv_type, register, running_bridge, send

A1 = f"{h.ALICE}:proj"
A2 = f"{h.ALICE}:other"

# Names of another machine, or of none: the separator is part of the prefix
FOREIGN = [h.BOB, f"{h.BOB}:proj", f"{h.ALICE}x:proj", f"{h.ALICE}x", "Host", "Host:Alic", f"{h.ALICE.lower()}:proj"]
BAD_LABELS = [f"{h.ALICE}:", f"{h.ALICE}:a:b", f"{h.ALICE}:a b", f"{h.ALICE}:" + "x" * 65, f"{h.ALICE}:é",
              f"{h.ALICE}:a\nb"]


def run(coro):
    return asyncio.run(coro)


def bearer(token: str) -> str:
    return f"Bearer {token}"


async def no_message(ws, timeout: float = 0.3) -> bool:
    """Whether no message (live or unread) arrives; peer_joined and the like do not count."""
    try:
        while True:
            if (await recv(ws, timeout)).get("type") in ("message", "unread"):
                return False
    except asyncio.TimeoutError:
        return True


async def names_online(ws) -> list[str]:
    await send(ws, type="list_peers")
    return sorted(p["name"] for p in (await recv_type(ws, "peer_list"))["peers"])


# --- two sessions, one machine ------------------------------------------------

def test_two_sessions_of_one_machine_are_both_online_and_both_receive(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two, \
                    connect(server, h.BOB_TOKEN) as bob:
                assert await register(one, A1) == {"type": "registered", "name": A1}
                assert await register(two, A2) == {"type": "registered", "name": A2}
                await register(bob, h.BOB)
                online = await names_online(bob)
                await send(bob, type="message", to=A1, content="for one")
                got_one = await recv_type(one, "message")
                await send(bob, type="message", to=A2, content="for two")
                got_two = await recv_type(two, "message")
                # Each got its own message only
                quiet = await no_message(one) and await no_message(two)
                await send(one, type="message", to=h.BOB, content="from one")
                return online, got_one, got_two, quiet, await recv_type(bob, "message")

    online, got_one, got_two, quiet, reply = run(go())
    assert online == sorted([A1, A2, h.BOB])
    assert (got_one["to"], got_one["content"]) == (A1, "for one")
    assert (got_two["to"], got_two["content"]) == (A2, "for two")
    assert quiet
    assert (reply["from"], reply["content"]) == (A1, "from one")


def test_machine_name_reaches_every_session_of_that_machine(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two, \
                    connect(server, h.ALICE_TOKEN) as bare, connect(server, h.BOB_TOKEN) as bob:
                await register(one, A1)
                await register(two, A2)
                # A 0.1.8 client of the same machine holds the bare name
                await register(bare, h.ALICE)
                await register(bob, h.BOB)
                await send(bob, type="message", to=h.ALICE, content="all of you")
                frames = [await recv_type(ws, "message") for ws in (one, two, bare)]
                return frames, await server.store.get_unread(h.ALICE), await no_message(bob)

    frames, unread, quiet = run(go())
    assert [(f["to"], f["content"]) for f in frames] == [(h.ALICE, "all of you")] * 3
    assert len({f["id"] for f in frames}) == 1  # one stored message, three deliveries
    assert unread == []
    assert quiet


def test_a_session_writing_to_its_own_machine_reaches_the_others_not_itself(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two:
                await register(one, A1)
                await register(two, A2)
                await send(one, type="message", to=h.ALICE, content="siblings")
                return await recv_type(two, "message"), await no_message(one)

    got, quiet = run(go())
    assert (got["from"], got["content"]) == (A1, "siblings")
    assert quiet


def test_a_peer_writing_to_its_own_bare_name_does_not_reach_the_machines_sessions(tmp_path):
    """deploy test registers the machine's name and sends itself a nonce: no session may be woken by it."""
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as smoke, \
                    connect(server, h.ALICE_TOKEN) as watcher:
                await register(one, A1)
                await send(watcher, type="watch", peer=A1, session="9")
                await recv(watcher)
                await register(smoke, h.ALICE)
                await send(smoke, type="message", to=h.ALICE, content="nonce")
                back = await recv_type(smoke, "message")
                return back, await no_message(one), await no_message(watcher)

    back, session_quiet, watcher_quiet = run(go())
    assert back["content"] == "nonce"
    assert session_quiet and watcher_quiet


def test_a_session_name_is_not_a_machine_name(tmp_path):
    """A message to one session stays with that session, even with siblings online."""
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two, \
                    connect(server, h.BOB_TOKEN) as bob:
                await register(one, A1)
                await register(two, f"{A1}-2")
                await register(bob, h.BOB)
                await send(bob, type="message", to=A1, content="x")
                await recv_type(one, "message")
                return await no_message(two)

    assert run(go())


# --- the prefix guard ----------------------------------------------------------

@pytest.mark.parametrize("name", FOREIGN)
def test_a_machine_cannot_register_under_another_machines_prefix(tmp_path, name, caplog):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as intruder, connect(server, h.BOB_TOKEN) as bob:
                refused = await register(intruder, name)
                await register(bob, h.BOB)
                online = await names_online(bob)
                await send(bob, type="message", to=name, content="S3CRET")
                return refused, online, await no_message(intruder)

    refused, online, quiet = run(go())
    assert (refused["type"], refused["code"]) == ("error", "name_not_bound_to_token")
    assert online == [h.BOB]
    assert quiet  # what is sent to the name does not reach the connection that asked for it
    assert h.ALICE_TOKEN not in caplog.text


@pytest.mark.parametrize("name", FOREIGN)
def test_a_machine_cannot_watch_under_another_machines_prefix(tmp_path, name):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                await send(ws, type="watch", peer=name)
                return await recv(ws)

    frame = run(go())
    assert (frame["type"], frame["code"]) == ("error", "watch_not_own_name")


@pytest.mark.parametrize("name", [h.ALICE, A1, f"{h.ALICE}:a.b_c-1", f"{h.ALICE}:" + "x" * 64])
def test_a_machine_registers_and_watches_its_own_names(tmp_path, name):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws, connect(server, h.ALICE_TOKEN) as watcher:
                await send(watcher, type="watch", peer=name)
                return await register(ws, name), await recv(watcher)

    registered, watching = run(go())
    assert registered == {"type": "registered", "name": name}
    assert watching == {"type": "watching", "peer": name}


@pytest.mark.parametrize("name", BAD_LABELS)
def test_a_session_label_is_plain_and_short(tmp_path, name):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                return await register(ws, name)

    frame = run(go())
    assert (frame["type"], frame["code"]) == ("error", "invalid_session_label")


@pytest.mark.parametrize("name", [f"{h.BOB}:proj", f"{h.ALICE}:x"])
def test_the_shared_token_cannot_take_a_session_name_of_an_enrolled_machine(tmp_path, name):
    async def go():
        async with running_bridge(tmp_path, allow_shared_token=True) as server:
            async with connect(server, h.SHARED_TOKEN) as ws:
                refused = await register(ws, name)
                await send(ws, type="watch", peer=name)
                return refused, await recv(ws), await register(ws, "Other:Project")

    refused, watch, own = run(go())
    assert (refused["type"], refused["code"]) == ("error", "name_bound_to_other_token")
    assert (watch["type"], watch["code"]) == ("error", "watch_not_own_name")
    assert own["type"] == "registered"


def test_a_machine_whose_name_is_a_prefix_of_another_does_not_own_it():
    """auth.peers may hold both "Host" and "Host:Alice": the longer name owns what is under it."""
    roles = Roles(peer_token_sha256={"Host": token_sha256("host-token"), h.ALICE: token_sha256(h.ALICE_TOKEN)})
    host, alice = roles.identity_for(bearer("host-token")), roles.identity_for(bearer(h.ALICE_TOKEN))
    assert roles.register_refusal(host, "Host") is None
    assert roles.register_refusal(host, "Host:proj") is None
    assert roles.register_refusal(host, h.ALICE) == "name_not_bound_to_token"
    assert roles.register_refusal(host, A1) == "name_not_bound_to_token"
    assert roles.watch_refusal(host, A1) == "watch_not_own_name"
    assert roles.register_refusal(alice, A1) is None
    assert roles.register_refusal(alice, "Host:proj") == "name_not_bound_to_token"


# --- a label collision -----------------------------------------------------------

def test_a_live_session_name_is_not_taken_over_by_a_sibling(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as first, connect(server, h.ALICE_TOKEN) as second:
                await register(first, A1)
                refused = await register(second, A1)
                waiting = await register(second, A1, standby=True)
                other = await register(second, f"{A1}-4242")
                return refused, waiting, other, await names_online(first)

    refused, waiting, other, online = run(go())
    assert (refused["type"], refused["code"]) == ("error", "name_taken")
    assert waiting == {"type": "standby", "name": A1}
    assert other["type"] == "registered"
    assert online == sorted([A1, f"{A1}-4242"])


# --- disconnect and reconnect ------------------------------------------------------

def test_a_session_gets_what_waited_for_its_name_and_no_sibling_does(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.BOB_TOKEN) as bob, connect(server, h.ALICE_TOKEN) as two:
                await register(bob, h.BOB)
                async with connect(server, h.ALICE_TOKEN) as one:
                    await register(one, A1)
                await asyncio.sleep(0.1)
                await send(bob, type="message", to=A1, content="while away")
                await register(two, A2)
                sibling_quiet = await no_message(two)
                async with connect(server, h.ALICE_TOKEN) as back:
                    assert (await register(back, A1))["type"] == "registered"
                    return sibling_quiet, await recv_type(back, "unread")

    sibling_quiet, unread = run(go())
    assert sibling_quiet
    assert [m["content"] for m in unread["messages"]] == ["while away"]


def test_what_waited_for_the_machine_goes_to_its_first_session_once(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.BOB_TOKEN) as bob:
                await register(bob, h.BOB)
                await send(bob, type="message", to=h.ALICE, content="anyone there")
                assert await no_message(bob)
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two:
                await register(one, A1)
                first = await recv_type(one, "unread")
                await register(two, A2)
                return first, await no_message(two), await server.store.get_unread(h.ALICE)

    first, quiet, left = run(go())
    assert [(m["to"], m["content"]) for m in first["messages"]] == [(h.ALICE, "anyone there")]
    assert quiet
    assert left == []


def test_backlog_of_the_machine_is_delivered_exactly_once_across_concurrent_registrations(tmp_path):
    async def drain(ws) -> list[str]:
        contents = []
        try:
            while True:
                frame = await recv(ws, 0.4)
                if frame["type"] == "unread":
                    contents += [m["content"] for m in frame["messages"]]
        except asyncio.TimeoutError:
            return contents

    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.BOB_TOKEN) as bob:
                await register(bob, h.BOB)
                for i in range(5):
                    await send(bob, type="message", to=h.ALICE, content=f"m{i}")
                assert await no_message(bob)
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two:
                await asyncio.gather(send(one, type="register", name=A1), send(two, type="register", name=A2))
                return await asyncio.gather(drain(one), drain(two))

    first, second = run(go())
    assert sorted(first + second) == [f"m{i}" for i in range(5)]


def test_a_sibling_that_fetched_the_backlog_before_it_was_delivered_does_not_send_it_again(tmp_path):
    """Two sessions register together and the second one's read of the store returns late,
    after the first has sent, marked and let go of every row: it must not send its stale copy."""
    async def drain(ws) -> list[str]:
        contents = []
        try:
            while True:
                frame = await recv(ws, 0.8)
                if frame["type"] == "unread":
                    contents += [m["content"] for m in frame["messages"]]
        except asyncio.TimeoutError:
            return contents

    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.BOB_TOKEN) as bob:
                await register(bob, h.BOB)
                for i in range(3):
                    await send(bob, type="message", to=h.ALICE, content=f"m{i}")
                assert await no_message(bob)
            read, calls = server.store.get_unread, []

            async def slow_second_read(peer):
                rows = await read(peer)
                if peer == h.ALICE:
                    calls.append(peer)
                    if len(calls) == 2:
                        await asyncio.sleep(0.4)  # the snapshot is taken; the first replay finishes meanwhile
                return rows

            server.store.get_unread = slow_second_read
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two:
                await asyncio.gather(send(one, type="register", name=A1), send(two, type="register", name=A2))
                return await asyncio.gather(drain(one), drain(two))

    first, second = run(go())
    assert sorted(first + second) == ["m0", "m1", "m2"]


class ClosedSocket:
    """A session whose connection broke: every send fails."""
    state = None

    async def send(self, _payload):
        raise ConnectionClosed(None, None)


def test_a_backlog_whose_session_broke_goes_to_a_sibling_at_once(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as two, connect(server, h.ALICE_TOKEN) as three:
                await register(two, A2)
                await register(three, f"{A2}-3")
                await asyncio.sleep(0.1)  # their own replays, which follow "registered", are over
                for i in range(2):
                    await server.store.store(h.BOB, h.ALICE, f"m{i}", None, delivered=False)
                await server.store.store(h.BOB, A1, "for the broken one", None, delivered=False)
                with pytest.raises(ConnectionClosed):
                    await server._deliver_unread(ClosedSocket(), A1, h.ALICE)  # pylint: disable=protected-access
                got = await recv_type(two, "unread")
                return (got, await no_message(three), await server.store.get_unread(h.ALICE),
                        await server.store.get_unread(A1))

    got, sibling_quiet, machine_left, own_left = run(go())
    assert [m["content"] for m in got["messages"]] == ["m0", "m1"]
    assert sibling_quiet  # one sibling, not each of them
    assert machine_left == []
    # What was for the broken session's own name waits for it, and reaches no sibling
    assert [m["content"] for m in own_left] == ["for the broken one"]


def test_a_backlog_with_no_sibling_online_stays_for_the_next_registration(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            await server.store.store(h.BOB, h.ALICE, "m", None, delivered=False)
            with pytest.raises(ConnectionClosed):
                await server._deliver_unread(ClosedSocket(), A1, h.ALICE)  # pylint: disable=protected-access
            async with connect(server, h.ALICE_TOKEN) as one:
                await register(one, A1)
                return await recv_type(one, "unread")

    assert [m["content"] for m in run(go())["messages"]] == ["m"]


def test_a_register_refusal_says_that_this_bridge_knows_session_names(tmp_path):
    """So a client can tell "not your name" from a Bridge older than 0.2.0, which sends the same code."""
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as ws:
                return await register(ws, f"{h.BOB}:proj")

    frame = run(go())
    assert frame["code"] == "name_not_bound_to_token"
    assert frame["session_names"] is True


# --- watchers, history, idle notices -------------------------------------------------

def test_a_sessions_watcher_hears_its_own_and_the_machines_messages(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as watcher, connect(server, h.BOB_TOKEN) as bob:
                await send(watcher, type="watch", peer=A1, session="100")
                assert (await recv(watcher))["type"] == "watching"
                await register(bob, h.BOB)
                await send(bob, type="message", to=A2, content="for the sibling")
                quiet = await no_message(watcher)
                await send(bob, type="message", to=A1, content="for the session")
                own = await recv_type(watcher, "message")
                await send(bob, type="message", to=h.ALICE, content="for the machine")
                return quiet, own, await recv_type(watcher, "message")

    quiet, own, machine = run(go())
    assert quiet
    assert own["content"] == "for the session"
    assert machine["content"] == "for the machine"


def test_watchers_of_two_machines_may_share_a_session_pid(tmp_path):
    """The session id is a process id: unique on one machine, not across machines."""
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as alice, connect(server, h.BOB_TOKEN) as bob, \
                    connect(server, h.ALICE_TOKEN) as again:
                await send(alice, type="watch", peer=A1, session="4321")
                first = await recv(alice)
                await send(bob, type="watch", peer=h.BOB, session="4321")
                second = await recv(bob)
                await send(again, type="watch", peer=A1, session="4321")
                return first["type"], second["type"], (await recv(again))["type"]

    assert run(go()) == ("watching", "watching", "already_watching")


def test_a_watcher_is_woken_by_what_the_machine_got_while_none_ran(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.BOB_TOKEN) as bob, connect(server, h.ALICE_TOKEN) as watcher:
                await register(bob, h.BOB)
                await send(bob, type="message", to=h.ALICE, content="missed")
                assert await no_message(bob)
                await send(watcher, type="watch", peer=A1, session="7", since="2000-01-01T00:00:00Z")
                await recv_type(watcher, "watching")
                return await recv_type(watcher, "message")

    assert run(go())["content"] == "missed"


def test_history_of_a_session_holds_its_own_and_the_machines_messages(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.ALICE_TOKEN) as two, \
                    connect(server, h.BOB_TOKEN) as bob:
                await register(one, A1)
                await register(two, A2)
                await register(bob, h.BOB)
                await send(bob, type="message", to=A1, content="to one")
                await send(bob, type="message", to=A2, content="to two")
                await send(bob, type="message", to=h.ALICE, content="to the machine")
                await recv_type(two, "message")
                await recv_type(two, "message")
                await send(one, type="message", to=h.BOB, content="from one")
                await recv_type(bob, "message")
                await send(one, type="history", peer=h.BOB)
                mine = await recv_type(one, "history")
                await send(bob, type="history", peer=h.ALICE)
                machine = await recv_type(bob, "history")
                await send(bob, type="history", peer=A2)
                return mine, machine, await recv_type(bob, "history")

    mine, machine, session = run(go())
    assert [m["content"] for m in mine["messages"]] == ["to one", "to the machine", "from one"]
    # Asked by the machine's name, the conversation with each of its sessions
    assert [m["content"] for m in machine["messages"]] == ["to one", "to two", "to the machine", "from one"]
    assert [m["content"] for m in session["messages"]] == ["to two"]


def test_notify_when_idle_for_a_machine_fires_for_its_first_idle_session(tmp_path):
    async def go():
        async with running_bridge(tmp_path) as server:
            async with connect(server, h.ALICE_TOKEN) as one, connect(server, h.BOB_TOKEN) as bob:
                await register(one, A1)
                await register(bob, h.BOB)
                await send(bob, type="notify_when_idle", peer=h.ALICE)
                assert await no_message(bob)
                await send(one, type="set_state", state="idle")
                later = await recv_type(bob, "message")
                await send(bob, type="notify_when_idle", peer=h.ALICE)
                return later, await recv_type(bob, "message")

    later, at_once = run(go())
    assert later["from"] == "Bridge" and A1 in later["content"]
    assert A1 in at_once["content"]
