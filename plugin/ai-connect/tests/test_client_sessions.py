"""The client side of several sessions per machine: the session's name, what it does
when a sibling holds that name, and how it joins a Bridge from before session names."""

import asyncio
import logging
import re
import sys
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "client") not in sys.path:
    sys.path.append(str(ROOT / "client"))  # last, so client/server.py shadows nothing

from bridge_client import BridgeClient  # noqa: E402  # pylint: disable=import-error,wrong-import-position
from peer_name import machine_name, peer_name, session_identity, session_label  # noqa: E402  # pylint: disable=wrong-import-position
from server.roles import SESSION_LABEL  # noqa: E402  # pylint: disable=wrong-import-position

TAKEN = {"type": "error", "code": "name_taken", "error": "held"}
# A Bridge from before session names (0.1.8) refuses every "<machine>:<label>" this way
NOT_BOUND = {"type": "error", "code": "name_not_bound_to_token", "error": "not yours"}
# A 0.2.0 Bridge sends the same code for a name another machine owns, and marks the frame
NOT_YOURS = {**NOT_BOUND, "session_names": True}


def session_client(**kwargs) -> tuple[BridgeClient, list[dict]]:
    """A session client of the machine "laptop" whose sends are recorded instead of sent."""
    sent: list[dict] = []
    client = BridgeClient("h", 1, "laptop:proj", "t", machine_name="laptop", collision_suffix="4242", **kwargs)

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send  # pylint: disable=protected-access
    return client, sent


def handle(client: BridgeClient, *frames: dict) -> None:
    async def go():
        for frame in frames:
            await client._handle(frame)  # pylint: disable=protected-access

    asyncio.run(go())


# --- the name -----------------------------------------------------------------

def test_a_session_is_named_after_its_machine_and_project(tmp_path):
    assert peer_name({}, tmp_path / "proj", "laptop") == "laptop:proj"
    assert peer_name({"CLAUDE_PROJECT_DIR": str(tmp_path / "repo")}, tmp_path / "elsewhere", "laptop") == "laptop:repo"
    assert peer_name({"AI_CONNECT_PEER_SUFFIX": "review"}, tmp_path / "proj", "laptop") == "laptop:proj-review"
    assert peer_name({"AI_CONNECT_PEER_NAME": "laptop:mine"}, tmp_path / "proj", "laptop") == "laptop:mine"


def test_machine_name_is_the_fallback_only_for_a_derived_session_name():
    assert machine_name({}, "laptop") == "laptop"
    # A name given outright is registered as given, and no client.name means the legacy Host:Project
    assert machine_name({"AI_CONNECT_PEER_NAME": "laptop:mine"}, "laptop") == ""
    assert machine_name({}, "") == ""


def test_a_per_project_name_with_its_own_token_is_registered_as_it_is(tmp_path):
    """client.name_mode: per-project (0.1.13) binds "<client.name>-<project>" to a token of its own."""
    assert session_identity({}, tmp_path / "proj", "laptop-proj", "laptop") == ("laptop-proj", {})
    # That mode fell back to client.token, or is off: the session's name is under the machine's
    assert session_identity({}, tmp_path / "proj", "laptop", "laptop") == ("laptop:proj", {"machine_name": "laptop"})
    env = {"AI_CONNECT_PEER_NAME": "reviewer"}
    assert session_identity(env, tmp_path / "proj", "laptop", "laptop") == ("reviewer", {"machine_name": ""})


def test_the_watcher_sends_the_machines_token_for_a_session_name(tmp_path, monkeypatch):
    """A session name holds a colon, so no token file is looked up for it."""
    import config_loader  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(config_loader, "SESSION_TOKEN_DIR", tmp_path / "session-tokens")
    config = {"client": {"name": "laptop", "token": "t" * 64, "bridge_url": "ws://127.0.0.1:9999"}}
    for name in ("laptop:proj", "laptop:proj-4242"):
        settings = config_loader.client_settings(config, environ={}, name=name)
        assert (settings.name, settings.token) == ("laptop", "t" * 64)


@pytest.mark.parametrize("project, label", [
    ("useful-claude-add-ons", "useful-claude-add-ons"),
    ("My Proj (v2)!", "My-Proj-v2"),
    ("Zürich Café", "Zurich-Cafe"),
    ("..hidden..", "hidden"),
    ("tab\there\nnewline", "tab-here-newline"),
])
def test_an_odd_project_name_is_sanitised(tmp_path, project, label):
    assert session_label({"CLAUDE_PROJECT_DIR": str(tmp_path / project)}, tmp_path) == label


def test_a_colon_in_a_project_name_cannot_reach_into_another_name():
    # A directory name may hold a colon on Linux and macOS, never on Windows
    assert session_label({}, PurePosixPath("/home/me/a:b:c")) == "a-b-c"


@pytest.mark.parametrize("project", ["プロジェクト", "\U0001f680", "---", "проект"])
def test_a_project_name_with_nothing_plain_in_it_still_gets_a_label_of_its_own(tmp_path, project):
    label = session_label({"CLAUDE_PROJECT_DIR": str(tmp_path / project)}, tmp_path)
    assert re.fullmatch(r"p-[0-9a-f]{8}", label)
    assert label != session_label({"CLAUDE_PROJECT_DIR": str(tmp_path / (project + "2"))}, tmp_path)


@pytest.mark.parametrize("project", ["x" * 300, "My Proj (v2)!", "プロ", "a" * 39 + "..b", "."])
def test_every_label_is_one_the_bridge_accepts(tmp_path, project):
    environ = {"CLAUDE_PROJECT_DIR": str(tmp_path / project), "AI_CONNECT_PEER_SUFFIX": "s" * 30}
    for env in (environ, {"CLAUDE_PROJECT_DIR": environ["CLAUDE_PROJECT_DIR"]}):
        label = session_label(env, tmp_path)
        # Room is left for the collision suffix ("-<process id>")
        assert SESSION_LABEL.fullmatch(label) and SESSION_LABEL.fullmatch(f"{label}-4294967295"), label


# --- a sibling holds the name ----------------------------------------------------

def test_a_taken_session_name_is_tried_again_with_the_sessions_own_suffix():
    client, sent = session_client()
    handle(client, TAKEN)
    assert sent == [{"type": "register", "name": "laptop:proj-4242", "standby": False}]
    assert client.peer_name == "laptop:proj-4242"
    assert not client.standby and not client.connected
    handle(client, {"type": "registered", "name": "laptop:proj-4242"})
    assert client.connected
    assert client.pop_messages() == []  # a suffix is no trouble: no notice


def test_a_taken_suffixed_name_waits_on_standby_and_is_not_retried_for_ever(caplog):
    client, sent = session_client()
    with caplog.at_level(logging.WARNING):
        handle(client, TAKEN, TAKEN, TAKEN)
    assert [(m["name"], m["standby"]) for m in sent] == [("laptop:proj-4242", False), ("laptop:proj-4242", True)]
    assert client.standby and not client.connected
    assert "not retrying" in caplog.text


def test_the_suffixed_name_is_kept_for_the_next_connection():
    client, sent = session_client()
    handle(client, TAKEN, {"type": "registered", "name": "laptop:proj-4242"})
    sent.clear()
    asyncio.run(client._register())  # pylint: disable=protected-access
    assert sent == [{"type": "register", "name": "laptop:proj-4242", "standby": False}]


def test_the_registered_name_is_reported_once_it_is_known():
    names: list[str] = []
    client, _ = session_client(on_registered=names.append)
    handle(client, TAKEN)
    assert names == []
    handle(client, {"type": "registered", "name": "laptop:proj-4242"})
    assert names == ["laptop:proj-4242"]


def test_a_failing_name_report_does_not_end_the_session(caplog):
    def fail(_name):
        raise OSError("disk full")

    client, _ = session_client(on_registered=fail)
    with caplog.at_level(logging.WARNING):
        handle(client, {"type": "registered", "name": "laptop:proj"})
    assert client.connected
    assert "disk full" in caplog.text


# --- a Bridge from before session names ---------------------------------------------

def test_an_older_bridge_gets_the_machine_name_and_the_session_is_told():
    client, sent = session_client()
    handle(client, NOT_BOUND)
    assert sent == [{"type": "register", "name": "laptop", "standby": False}]
    assert client.peer_name == "laptop"
    handle(client, {"type": "registered", "name": "laptop"})
    assert client.connected
    notices = [m["content"] for m in client.pop_messages()]
    assert len(notices) == 1 and "0.2.0" in notices[0] and "laptop" in notices[0]


def test_a_name_another_machine_owns_is_not_mistaken_for_an_older_bridge(caplog):
    """client.name "Host" in a project "Alice" asks for "Host:Alice", which may be enrolled itself:
    joining as "Host" instead, with a notice blaming the Bridge's age, would hide the conflict."""
    client, sent = session_client()
    with caplog.at_level(logging.ERROR):
        handle(client, NOT_YOURS)
    assert sent == []  # no fallback to the machine name
    assert client.peer_name == "laptop:proj"
    assert not client.connected
    notices = [m["content"] for m in client.pop_messages()]
    assert len(notices) == 1
    assert "laptop:proj" in notices[0] and "client.name" in notices[0] and "another" in notices[0]
    assert "0.2.0" not in notices[0] and "older" not in notices[0]
    assert "name_not_bound_to_token" in caplog.text


def test_on_an_older_bridge_a_second_session_waits_on_standby_as_before():
    client, sent = session_client()
    handle(client, NOT_BOUND, TAKEN)
    # No suffix on the machine name: the old Bridge would refuse it
    assert [(m["name"], m["standby"]) for m in sent] == [("laptop", False), ("laptop", True)]
    assert client.standby


def test_a_refused_machine_name_is_reported_and_not_tried_again():
    client, sent = session_client()
    handle(client, NOT_BOUND, NOT_BOUND)
    assert len(sent) == 1
    assert not client.connected
    assert any("name_not_bound_to_token" in m["content"] for m in client.pop_messages())


def test_a_name_given_outright_has_no_fallback():
    sent: list[dict] = []
    client = BridgeClient("h", 1, "laptop:mine", "t")

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send  # pylint: disable=protected-access
    handle(client, NOT_BOUND)
    assert sent == []
    assert any("name_not_bound_to_token" in m["content"] for m in client.pop_messages())


def test_each_new_connection_asks_for_the_session_name_again(monkeypatch):
    """So a session that fell back joins under its own name once the Bridge is updated."""
    import bridge_client  # pylint: disable=import-error,import-outside-toplevel

    class FakeSocket:
        def __init__(self):
            self.sent = []

        async def send(self, raw):
            self.sent.append(raw)

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(3600)

        async def close(self):
            pass

    sockets = []

    async def fake_connect(_uri, **_kwargs):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(bridge_client.websockets, "connect", fake_connect)

    async def go():
        client = BridgeClient("h", 1, "laptop:proj", "t", machine_name="laptop", collision_suffix="4242")
        await client.connect()
        await client._handle(NOT_BOUND)  # pylint: disable=protected-access
        assert client.peer_name == "laptop"
        await client.connect()
        name = client.peer_name
        await client.disconnect()
        return name

    assert asyncio.run(go()) == "laptop:proj"
    assert '"name": "laptop:proj"' in sockets[1].sent[0]
