"""The Bridge's hot auth reload and its join endpoint, against a real Bridge on a free port.

Must-block: a revoked peer's live connection is closed and it cannot connect
again; a broken config never replaces the table; a used, expired or unknown
code gets the one generic 403, and a flood of them a 429. Must-allow: a peer
added to config.yaml connects with no restart; peers still in the table keep
their connections across a reload. Files live under tmp_path only.
"""

import asyncio
import http.client
import json
import logging

import pytest
import yaml
from websockets.exceptions import ConnectionClosed, InvalidStatus

import test_server_harness as h  # noqa: F401  # puts the repo root on sys.path first

import installer  # noqa: E402
import join_codes as jc  # noqa: E402
from config_loader import server_settings  # noqa: E402
from server.main import build_server  # noqa: E402
from server.roles import token_sha256  # noqa: E402
from test_server_harness import connect, recv_type, register  # noqa: E402

ALICE, BOB, CAROL = "alice", "bob", "carol"
TOKENS = {ALICE: "a" * 64, BOB: "b" * 64, CAROL: "c" * 64}
POLL = 0.05


def run(coro):
    return asyncio.run(coro)


def write(path, config):
    jc.write_config(path, config)


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "ai-connect" / "config.yaml"
    path.parent.mkdir()
    config = installer._example()  # pylint: disable=protected-access
    config["server"]["port"] = 0
    config["auth"]["peers"] = {ALICE: token_sha256(TOKENS[ALICE]), BOB: token_sha256(TOKENS[BOB])}
    write(path, config)
    return path


def edit_peers(path, change):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(config["auth"]["peers"])
    write(path, config)


class Bridge:
    def __init__(self, config_path, tmp_path):
        self.server = build_server(server_settings(yaml.safe_load(config_path.read_text(encoding="utf-8"))),
                                   db_path=str(tmp_path / "messages.db"), config_path=config_path)
        self.server.reload_seconds = POLL

    async def __aenter__(self):
        await self.server.start()
        return self.server

    async def __aexit__(self, *exc):
        await self.server.stop()


async def wait_reloaded(server, at_least: int = 2) -> None:
    # A couple of polls past the edit
    await asyncio.sleep(POLL * (at_least + 2))


async def closed_with(ws, timeout=3.0):
    try:
        while True:
            await asyncio.wait_for(ws.recv(), timeout)
    except ConnectionClosed as err:
        return err.rcvd.code if err.rcvd else None


def get_join(port, secret_hex, name):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", jc.JOIN_PATH, headers={jc.SECRET_HEADER: secret_hex, jc.NAME_HEADER: name})
        response = connection.getresponse()
        return response.status, response.read().decode()
    finally:
        connection.close()


# --- revocation -----------------------------------------------------------------

def test_revoked_peer_is_disconnected_and_cannot_return(config_path, tmp_path):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            async with connect(server, TOKENS[ALICE]) as alice, connect(server, TOKENS[BOB]) as bob:
                assert (await register(alice, ALICE))["type"] == "registered"
                assert (await register(bob, BOB))["type"] == "registered"
                edit_peers(config_path, lambda peers: peers.pop(BOB))
                code = await closed_with(bob)
                # Alice, still in the table, keeps her connection
                await alice.send(json.dumps({"type": "ping"}))
                assert (await recv_type(alice, "pong"))["type"] == "pong"
            with pytest.raises(InvalidStatus) as err:
                async with connect(server, TOKENS[BOB]):
                    pass
            return code, err.value.response.status_code

    code, status = run(go())
    assert code == 1008
    assert status == 401


def test_replaced_token_closes_the_old_connection(config_path, tmp_path):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            async with connect(server, TOKENS[BOB]) as bob:
                await register(bob, BOB)
                edit_peers(config_path, lambda peers: peers.__setitem__(BOB, token_sha256("new" * 22)))
                return await closed_with(bob)

    assert run(go()) == 1008


def test_new_peer_is_accepted_with_no_restart(config_path, tmp_path):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            with pytest.raises(InvalidStatus):
                async with connect(server, TOKENS[CAROL]):
                    pass
            edit_peers(config_path, lambda peers: peers.__setitem__(CAROL, token_sha256(TOKENS[CAROL])))
            await wait_reloaded(server)
            async with connect(server, TOKENS[CAROL]) as carol:
                return await register(carol, CAROL)

    assert run(go())["type"] == "registered"


@pytest.mark.parametrize("broken", [
    "auth: [this is: not yaml",                          # does not parse
    "server: {port: 0}\nauth: {peers: {bob: nothex}}\n",  # parses, invalid auth
    "just a string\n",                                  # not a mapping
])
def test_broken_config_keeps_the_old_table(config_path, tmp_path, caplog, broken):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            async with connect(server, TOKENS[BOB]) as bob:
                await register(bob, BOB)
                config_path.write_text(broken, encoding="utf-8")
                await wait_reloaded(server)
                # Still connected, and a new connection with the old table's token works
                await bob.send(json.dumps({"type": "ping"}))
                pong = await recv_type(bob, "pong")
                async with connect(server, TOKENS[ALICE]) as alice:
                    registered = await register(alice, ALICE)
                return pong, registered

    with caplog.at_level(logging.ERROR):
        pong, registered = run(go())
    assert pong["type"] == "pong" and registered["type"] == "registered"
    assert "auth_reload_failed" in caplog.text


def test_fixing_a_broken_config_is_picked_up(config_path, tmp_path):
    good = config_path.read_text(encoding="utf-8")

    async def go():
        async with Bridge(config_path, tmp_path) as server:
            config_path.write_text("auth: [broken", encoding="utf-8")
            await wait_reloaded(server)
            config = yaml.safe_load(good)
            config["auth"]["peers"][CAROL] = token_sha256(TOKENS[CAROL])
            write(config_path, config)
            await wait_reloaded(server)
            async with connect(server, TOKENS[CAROL]) as carol:
                return await register(carol, CAROL)

    assert run(go())["type"] == "registered"


def test_bridge_without_a_config_path_never_reloads(tmp_path):
    async def go():
        async with h.running_bridge(tmp_path) as server:
            return await server.reload_auth(), server._reload_task  # pylint: disable=protected-access

    assert run(go()) == (False, None)


# --- the join endpoint ------------------------------------------------------------

def test_join_code_redeems_over_the_bridge_and_the_peer_connects_at_once(config_path, tmp_path, caplog):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            code = jc.decode(jc.create_invite(config_path, CAROL, 3600, "127.0.0.1", server.bound_port))
            status, body = await asyncio.to_thread(get_join, server.bound_port, code.secret.hex(), CAROL)
            token = json.loads(body)["token"]
            # No poll wait: redemption swaps the table itself
            async with connect(server, token) as carol:
                registered = await register(carol, CAROL)
            again = await asyncio.to_thread(get_join, server.bound_port, code.secret.hex(), CAROL)
            return status, token, registered, again

    # INFO, the Bridge's own level: websockets' DEBUG lines echo every request header, the
    # handshake's Bearer token included, for every connection alike
    with caplog.at_level(logging.INFO):
        status, token, registered, again = run(go())
    assert status == 200 and registered["type"] == "registered"
    assert again == (403, jc.GENERIC_REFUSAL + "\n")
    assert token not in caplog.text


@pytest.mark.parametrize("case", ["unknown", "wrong_name", "expired", "not_hex"])
def test_every_refusal_is_the_same_403(config_path, tmp_path, case):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            expiry = 60
            code = jc.decode(jc.create_invite(config_path, CAROL, expiry, "127.0.0.1", server.bound_port))
            secret, name = code.secret.hex(), CAROL
            if case == "unknown":
                secret = "00" * 16
            elif case == "wrong_name":
                name = "mallory"
            elif case == "not_hex":
                secret = "zz"
            else:
                store = jc.invites_path(config_path)
                data = json.loads(store.read_text(encoding="utf-8"))
                data["invites"][-1]["expires"] = 1
                store.write_text(json.dumps(data), encoding="utf-8")
            return await asyncio.to_thread(get_join, server.bound_port, secret, name)

    assert run(go()) == (403, jc.GENERIC_REFUSAL + "\n")


def test_failed_redemptions_are_rate_limited(config_path, tmp_path):
    async def go():
        async with Bridge(config_path, tmp_path) as server:
            code = jc.decode(jc.create_invite(config_path, CAROL, 3600, "127.0.0.1", server.bound_port))
            statuses = [(await asyncio.to_thread(get_join, server.bound_port, "00" * 16, CAROL))[0]
                        for _ in range(6)]
            # Even the right code waits now: the limiter answers before the store is read
            right = await asyncio.to_thread(get_join, server.bound_port, code.secret.hex(), CAROL)
            return statuses, right[0]

    statuses, right = run(go())
    assert statuses[:5] == [403] * 5 and statuses[5] == 429
    assert right == 429


def test_join_endpoint_is_off_without_a_config(tmp_path):
    async def go():
        async with h.running_bridge(tmp_path) as server:
            return await asyncio.to_thread(get_join, server.bound_port, "00" * 16, CAROL)

    assert run(go())[0] == 404


def test_a_yaml_error_logs_its_place_not_the_text_and_only_once(config_path, caplog):
    """The offending YAML can be a token: only the error type and line/column are logged, once per file."""
    from server.auth_reload import AuthReloader  # pylint: disable=import-outside-toplevel
    secret = "f" * 40
    reloader = AuthReloader(config_path)
    assert reloader.check() is not None  # the good file first
    # An undefined alias: PyYAML's own message quotes its name ("found undefined alias '<secret>'")
    config_path.write_text(f"auth: {{peers: *{secret}}}\n", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert reloader.check() is None
        assert reloader.check() is None
    failures = [r.getMessage() for r in caplog.records if "auth_reload_failed" in r.getMessage()]
    assert len(failures) == 1 and secret not in failures[0] and "line " in failures[0]
