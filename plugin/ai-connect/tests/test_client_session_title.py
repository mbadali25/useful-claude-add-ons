"""A session's label is its Claude Code session name when there is one (0.2.1), else its
project: what is read from Claude Code's own sessions directory, and every way that fails."""

import builtins
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "client") not in sys.path:
    sys.path.append(str(ROOT / "client"))  # last, so client/server.py shadows nothing

from bridge_client import BridgeClient  # noqa: E402  # pylint: disable=import-error,wrong-import-position
from peer_name import (  # noqa: E402  # pylint: disable=wrong-import-position
    claude_session_title,
    claude_sessions_dir,
    peer_name,
    session_identity,
    session_label,
)
from server.roles import SESSION_LABEL  # noqa: E402  # pylint: disable=wrong-import-position

PID = 4242
SECRET = "sk-secret-token-never-read"


def sessions(tmp_path: Path, content: str | bytes | None, pid: int = PID) -> Path:
    """A stand-in for ~/.claude/sessions holding <pid>.json with this content, and a .key beside it."""
    directory = tmp_path / "claude" / "sessions"
    directory.mkdir(parents=True)
    (directory / f"{pid}.abc123.key").write_text(SECRET, encoding="utf-8")
    if isinstance(content, bytes):
        (directory / f"{pid}.json").write_bytes(content)
    elif content is not None:
        (directory / f"{pid}.json").write_text(content, encoding="utf-8")
    return directory


def named(tmp_path: Path, name: object) -> Path:
    return sessions(tmp_path, json.dumps({"pid": PID, "name": name, "nameSource": "user", "cwd": "C:\\repo"}))


# --- reading the name -----------------------------------------------------------

def test_the_session_name_is_read_from_the_file_of_the_sessions_process(tmp_path):
    assert claude_session_title(PID, named(tmp_path, "cross-session")) == "cross-session"


# Each case has an id: pytest puts the id into an environment variable, and Windows
# refuses one as long as the last two cases
@pytest.mark.parametrize("content", [
    pytest.param(None, id="no-file"),       # another harness, or Claude Code changed its layout
    pytest.param("", id="empty"),
    pytest.param("{not json", id="bad-json"),
    pytest.param("[]", id="a-list"),        # JSON, but no object
    pytest.param('"cross-session"', id="a-string"),
    pytest.param("null", id="null"),
    pytest.param("{}", id="no-name"),
    pytest.param('{"name": null}', id="name-null"),
    pytest.param('{"name": ""}', id="name-empty"),
    pytest.param('{"name": 123}', id="name-number"),
    pytest.param('{"name": ["cross-session"]}', id="name-list"),
    pytest.param('{"name": {"name": "x"}}', id="name-object"),
    pytest.param(b"\xff\xfe\x00{", id="not-utf8"),
    pytest.param("[" * 100_000, id="nested-too-deep"),
    pytest.param('{"name": "' + "x" * 200_000 + '"}', id="too-large"),
])
def test_a_missing_or_unusable_file_gives_no_name(tmp_path, content):
    assert claude_session_title(PID, sessions(tmp_path, content)) == ""


def test_another_sessions_file_is_not_this_sessions_name(tmp_path):
    assert claude_session_title(PID + 1, named(tmp_path, "cross-session")) == ""


def test_a_missing_sessions_directory_gives_no_name(tmp_path):
    assert claude_session_title(PID, tmp_path / "nowhere") == ""


def test_an_unreadable_file_gives_no_name(tmp_path):
    directory = sessions(tmp_path, None)
    (directory / f"{PID}.json").mkdir()  # opening it fails with an OSError on every platform
    assert claude_session_title(PID, directory) == ""


def test_only_the_sessions_own_json_is_opened_never_the_key_beside_it(tmp_path, monkeypatch):
    """<pid>.<hash>.key holds a secret: the directory is not listed and no other file is opened."""
    directory = named(tmp_path, "cross-session")
    opened: list[Path] = []
    listed: list[str] = []
    real_open = io.open

    def recording_open(file, *args, **kwargs):
        if not isinstance(file, int):
            opened.append(Path(os.fspath(file)))
        return real_open(file, *args, **kwargs)

    def refuse_listing(*args, **_kwargs):
        listed.append(str(args))
        raise AssertionError("the sessions directory must not be listed")

    monkeypatch.setattr(io, "open", recording_open)
    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(os, "scandir", refuse_listing)
    monkeypatch.setattr(os, "listdir", refuse_listing)
    title = claude_session_title(PID, directory)
    monkeypatch.undo()

    assert title == "cross-session"
    assert opened == [directory / f"{PID}.json"]
    assert not listed
    assert SECRET not in title


def test_the_sessions_directory_is_claude_codes_own(tmp_path):
    assert claude_sessions_dir({}) == Path.home() / ".claude" / "sessions"
    # Claude Code keeps its files there when CLAUDE_CONFIG_DIR moves them
    assert claude_sessions_dir({"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")}) == tmp_path / "cfg" / "sessions"
    assert claude_sessions_dir({"CLAUDE_CONFIG_DIR": ""}) == Path.home() / ".claude" / "sessions"


# --- the label ------------------------------------------------------------------

def test_a_named_session_is_labelled_with_its_name_not_its_project(tmp_path):
    project = tmp_path / "useful-claude-add-ons"
    assert session_label({}, project, "cross-session") == "cross-session"
    assert peer_name({}, project, "dadeush-desktop", "cross-session") == "dadeush-desktop:cross-session"
    assert session_identity({}, project, "laptop", "laptop", "cross-session") == (
        "laptop:cross-session", {"machine_name": "laptop"})


@pytest.mark.parametrize("title", ["", "   ", "---", "...", "\U0001f680", "プロジェクト", "\t\n"])
def test_a_session_without_a_plain_name_is_labelled_with_its_project(tmp_path, title):
    assert session_label({}, tmp_path / "proj", title) == "proj"
    assert peer_name({}, tmp_path / "proj", "laptop", title) == "laptop:proj"
    # ... and a project with nothing plain in it keeps its hash
    assert session_label({}, tmp_path / "プロ", title).startswith("p-")


@pytest.mark.parametrize("title, label", [
    ("cross session", "cross-session"),
    ("Fix: the login/flow (v2)!", "Fix-the-login-flow-v2"),
    ("Zürich Café", "Zurich-Cafe"),
    ("..hidden..", "hidden"),
    ("tab\there\nnewline", "tab-here-newline"),
    ("laptop:other", "laptop-other"),       # a colon cannot reach into another machine's names
    ("日本 release 2", "release-2"),
    ("x" * 300, "x" * 40),
])
def test_an_odd_session_name_is_sanitised(tmp_path, title, label):
    assert session_label({}, tmp_path / "proj", title) == label


@pytest.mark.parametrize("title", ["x" * 300, "Fix: the login (v2)!", "a" * 39 + "..b", "日本 r", "a b" * 40])
def test_every_label_from_a_session_name_is_one_the_bridge_accepts(tmp_path, title):
    for env in ({"AI_CONNECT_PEER_SUFFIX": "s" * 30}, {}):
        label = session_label(env, tmp_path / "proj", title)
        # Room is left for the collision suffix ("-<process id>")
        assert SESSION_LABEL.fullmatch(label) and SESSION_LABEL.fullmatch(f"{label}-4294967295"), label


def test_the_suffix_is_appended_to_a_session_name_too(tmp_path):
    env = {"AI_CONNECT_PEER_SUFFIX": "review"}
    assert session_label(env, tmp_path / "proj", "cross-session") == "cross-session-review"
    assert peer_name(env, tmp_path / "proj", "laptop", "cross-session") == "laptop:cross-session-review"
    # Without a usable session name it is the project's, as before
    assert peer_name(env, tmp_path / "proj", "laptop", "") == "laptop:proj-review"


def test_a_name_given_outright_wins_over_the_session_name(tmp_path):
    env = {"AI_CONNECT_PEER_NAME": "laptop:mine", "AI_CONNECT_PEER_SUFFIX": "review"}
    assert peer_name(env, tmp_path / "proj", "laptop", "cross-session") == "laptop:mine"
    assert session_identity(env, tmp_path / "proj", "laptop", "laptop", "cross-session") == (
        "laptop:mine", {"machine_name": ""})


def test_the_legacy_host_project_name_ignores_the_session_name(tmp_path):
    """No client.name: only the legacy shared token accepts the name, and it stays Host:Project."""
    assert peer_name({}, tmp_path / "proj", "", "cross-session") == peer_name({}, tmp_path / "proj", "")
    assert peer_name({}, tmp_path / "proj", "", "cross-session").endswith(":proj")


def test_a_per_project_name_with_its_own_token_ignores_the_session_name(tmp_path):
    """client.name_mode: per-project binds "<client.name>-<project>" to a token; the name must stay that."""
    assert session_identity({}, tmp_path / "proj", "laptop-proj", "laptop", "cross-session") == ("laptop-proj", {})


def test_the_name_read_from_the_file_ends_up_in_the_peer_name(tmp_path):
    title = claude_session_title(PID, named(tmp_path, "Cross Session ✓"))
    project = tmp_path / "useful-claude-add-ons"
    assert peer_name({}, project, "dadeush-desktop", title) == "dadeush-desktop:Cross-Session"
    missing = claude_session_title(PID, tmp_path / "nowhere")
    assert peer_name({}, tmp_path / "useful-claude-add-ons", "dadeush-desktop", missing) == (
        "dadeush-desktop:useful-claude-add-ons")


# --- two sessions with one name ----------------------------------------------------

def test_two_sessions_with_one_session_name_are_told_apart_by_process_id(tmp_path):
    """Both ask for "<machine>:<session name>"; the Bridge refuses the second, which appends its process id."""
    import asyncio  # pylint: disable=import-outside-toplevel

    first = peer_name({}, tmp_path / "api", "laptop", "cross-session")
    second = peer_name({}, tmp_path / "web", "laptop", "cross-session")
    assert first == second == "laptop:cross-session"

    sent: list[dict] = []
    client = BridgeClient("h", 1, second, "t", machine_name="laptop", collision_suffix=str(PID))

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send  # pylint: disable=protected-access
    asyncio.run(client._handle({"type": "error", "code": "name_taken", "error": "held"}))  # pylint: disable=protected-access
    assert sent == [{"type": "register", "name": f"laptop:cross-session-{PID}", "standby": False}]
    assert client.peer_name == f"laptop:cross-session-{PID}"
    assert SESSION_LABEL.fullmatch(client.peer_name.split(":", 1)[1])
