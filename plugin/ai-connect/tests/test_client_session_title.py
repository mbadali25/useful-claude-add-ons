"""A session's label is its Claude Code session name when there is one (0.2.1), else its
project: what is read from Claude Code's own sessions directory, and every way that fails."""

import builtins
import concurrent.futures
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

import peer_name as peer_name_module  # noqa: E402  # pylint: disable=wrong-import-position
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
    pytest.param('{"name": "' + "x" * 200_000 + '"}', id="too-large"),
])
def test_a_missing_or_unusable_file_gives_no_name(tmp_path, content):
    assert claude_session_title(PID, sessions(tmp_path, content)) == ""


# As deep as fits under the 64 KB cap, so the decoder is reached
TOO_DEEP = "[" * peer_name_module._SESSION_FILE_MAX  # pylint: disable=protected-access


def test_a_file_nested_too_deep_for_the_decoder_gives_no_name(tmp_path):
    try:
        json.loads(TOO_DEEP)
    except RecursionError:
        pass
    except ValueError:
        pytest.skip("this interpreter's JSON decoder nests deeper than the 64 KB cap allows")
    assert claude_session_title(PID, sessions(tmp_path, TOO_DEEP)) == ""


def test_a_recursion_error_from_the_decoder_gives_no_name(tmp_path, monkeypatch):
    """Where the depth that raises it depends on the interpreter, the decoder raising it is stood in for."""
    def too_deep(*_args, **_kwargs):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")

    directory = named(tmp_path, "cross-session")
    monkeypatch.setattr(peer_name_module.json, "loads", too_deep)
    assert claude_session_title(PID, directory) == ""


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_fifo_in_place_of_the_file_gives_no_name_and_does_not_hang(tmp_path):
    """Opening a FIFO for reading waits for a writer; start-up must not."""
    directory = sessions(tmp_path, None)
    os.mkfifo(directory / f"{PID}.json")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(claude_session_title, PID, directory)
        try:
            title = future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            # Free the blocked open so the worker thread can end
            with open(directory / f"{PID}.json", "wb"):
                pass
            pytest.fail("claude_session_title blocked on a FIFO")
    assert title == ""


def test_another_sessions_file_is_not_this_sessions_name(tmp_path):
    assert claude_session_title(PID + 1, named(tmp_path, "cross-session")) == ""


def test_a_missing_sessions_directory_gives_no_name(tmp_path):
    assert claude_session_title(PID, tmp_path / "nowhere") == ""


def test_a_directory_in_place_of_the_file_gives_no_name(tmp_path):
    directory = sessions(tmp_path, None)
    (directory / f"{PID}.json").mkdir()  # opens on POSIX, but is no regular file; refused on Windows
    assert claude_session_title(PID, directory) == ""


def test_only_the_sessions_own_json_is_opened_never_the_key_beside_it(tmp_path, monkeypatch):
    """<pid>.<hash>.key holds a secret: the directory is not listed and no other file is opened."""
    directory = named(tmp_path, "cross-session")
    opened: list[Path] = []
    listed: list[str] = []
    real_open = io.open
    real_os_open = os.open

    def recording_open(file, *args, **kwargs):
        if not isinstance(file, int):
            opened.append(Path(os.fspath(file)))
        return real_open(file, *args, **kwargs)

    def recording_os_open(file, *args, **kwargs):
        opened.append(Path(os.fspath(file)))
        return real_os_open(file, *args, **kwargs)

    def refuse_listing(*args, **_kwargs):
        listed.append(str(args))
        raise AssertionError("the sessions directory must not be listed")

    monkeypatch.setattr(io, "open", recording_open)
    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(os, "open", recording_os_open)
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
    assert session_label({}, project, "cross-session") == "s-cross-session"
    assert peer_name({}, project, "dadeush-desktop", "cross-session") == "dadeush-desktop:s-cross-session"
    assert session_identity({}, project, "laptop", "laptop", "cross-session") == (
        "laptop:s-cross-session", {"machine_name": "laptop"})


@pytest.mark.parametrize("title", ["", "   ", "---", "...", "\U0001f680", "プロジェクト", "\t\n"])
def test_a_session_without_a_plain_name_is_labelled_with_its_project(tmp_path, title):
    assert session_label({}, tmp_path / "proj", title) == "proj"
    assert peer_name({}, tmp_path / "proj", "laptop", title) == "laptop:proj"
    # ... and a project with nothing plain in it keeps its hash
    assert session_label({}, tmp_path / "プロ", title).startswith("p-")


@pytest.mark.parametrize("title, label", [
    ("cross session", "s-cross-session"),
    ("Fix: the login/flow (v2)!", "s-Fix-the-login-flow-v2"),
    ("Zürich Café", "s-Zurich-Cafe"),
    ("..hidden..", "s-hidden"),
    ("tab\there\nnewline", "s-tab-here-newline"),
    ("laptop:other", "s-laptop-other"),     # a colon cannot reach into another machine's names
    ("日本 release 2", "s-release-2"),
    ("x" * 300, "s-" + "x" * 38),
    ("s-deploy", "s-s-deploy"),
])
def test_an_odd_session_name_is_sanitised(tmp_path, title, label):
    assert session_label({}, tmp_path / "proj", title) == label


# --- a session's label is never a project's (0.2.2) -------------------------------------

@pytest.mark.parametrize("project", ["deploy", "useful-claude-add-ons", "s.deploy", "s_deploy", "sdeploy"])
def test_a_session_renamed_after_a_project_cannot_take_that_projects_address(tmp_path, project):
    """must-block: a session named like another project gets "s-<name>", never "<project>"."""
    projects = session_label({}, tmp_path / project)
    renamed = session_label({}, tmp_path / "elsewhere", project)
    assert renamed == "s-" + project
    assert renamed != projects
    assert peer_name({}, tmp_path / "elsewhere", "laptop", project) != peer_name({}, tmp_path / project, "laptop")


@pytest.mark.parametrize("project, label", [
    ("s-deploy", "p-s-deploy"),
    ("S-Deploy", "p-S-Deploy"),
    ("s--deploy", "p-s--deploy"),
    ("s- deploy", "p-s--deploy"),
    ("s-", "p-s"),                     # the hyphen is stripped, and a bare "s" is escaped too
    ("s", "p-s"),
    ("S", "p-S"),
    ("-s-deploy", "p-s-deploy"),       # leading hyphens go first, then the escape applies
    ("..s-deploy", "p-s-deploy"),
])
def test_a_project_whose_name_starts_like_a_session_label_is_escaped(tmp_path, project, label):
    """must-block: a project directory named "s-<x>" cannot pass for the session named "<x>"."""
    assert session_label({}, tmp_path / project) == label
    assert not session_label({}, tmp_path / project).casefold().startswith("s-")


@pytest.mark.parametrize("project, label", [
    ("proj", "proj"),
    ("sproj", "sproj"),
    ("s.proj", "s.proj"),
    ("s_proj", "s_proj"),
    ("p-s-proj", "p-s-proj"),
])
def test_a_project_label_without_the_session_prefix_is_unchanged(tmp_path, project, label):
    """must-allow: only a leading "s-" is escaped; every other project label is as in 0.2.0."""
    assert session_label({}, tmp_path / project) == label


@pytest.mark.parametrize("project", ["s-" + "x" * 60, "S-" + "y" * 38, "s-a"])
@pytest.mark.parametrize("env", [{}, {"AI_CONNECT_PEER_SUFFIX": "s" * 30}, {"AI_CONNECT_PEER_SUFFIX": "s-x"}])
def test_an_escaped_project_label_is_still_one_the_bridge_accepts(tmp_path, project, env):
    label = session_label(env, tmp_path / project)
    assert not label.casefold().startswith("s-"), label
    assert SESSION_LABEL.fullmatch(label) and SESSION_LABEL.fullmatch(f"{label}-4294967295"), label
    assert len(label) <= 40, label


@pytest.mark.parametrize("project", ["s", "S"])
def test_a_project_named_s_cannot_read_as_a_session_label_with_any_suffix(tmp_path, project):
    """must-block: "s" plus suffix "review" would be "s-review", the label of a session named
    "review"; and "s" plus the collision suffix "-4242" that of a session named "4242"."""
    env = {"AI_CONNECT_PEER_SUFFIX": "review"}
    assert session_label(env, tmp_path / project) == f"p-{project}-review"
    assert session_label(env, tmp_path / project) != session_label({}, tmp_path / "x", "review")
    assert f"{session_label({}, tmp_path / project)}-{PID}" != session_label({}, tmp_path / "x", str(PID))


SUFFIXES = [{}, {"AI_CONNECT_PEER_SUFFIX": "review"}, {"AI_CONNECT_PEER_SUFFIX": "s"}, {"AI_CONNECT_PEER_SUFFIX": "-x-"}]


@pytest.mark.parametrize("project", ["deploy", "s-deploy", "S-x", "プロ", "s-" + "z" * 80, "p-s-q", "-", "s", "S", "review"])
@pytest.mark.parametrize("title", ["deploy", "s-deploy", "x" * 300, "p-s-deploy", "S-Q", "review", "s"])
def test_no_session_label_equals_any_project_label(tmp_path, project, title):
    """The invariant, both ways and across suffixes (each session has its own environment):
    a session's label starts with "s-", a project's never does."""
    sessions_ = {session_label(env, tmp_path / "elsewhere", title) for env in SUFFIXES}
    projects = {session_label(env, tmp_path / project) for env in SUFFIXES}
    # ... and with the collision suffix the Bridge client appends on name_taken
    projects |= {f"{label}-{PID}" for label in projects}
    sessions_ |= {f"{label}-{PID}" for label in sessions_}
    assert all(label.startswith("s-") for label in sessions_), sessions_
    assert not any(label.casefold().startswith("s-") for label in projects), projects
    assert not {s.casefold() for s in sessions_} & {p.casefold() for p in projects}


@pytest.mark.parametrize("title", ["x" * 300, "Fix: the login (v2)!", "a" * 39 + "..b", "日本 r", "a b" * 40])
def test_every_label_from_a_session_name_is_one_the_bridge_accepts(tmp_path, title):
    for env in ({"AI_CONNECT_PEER_SUFFIX": "s" * 30}, {}):
        label = session_label(env, tmp_path / "proj", title)
        # Room is left for the collision suffix ("-<process id>")
        assert SESSION_LABEL.fullmatch(label) and SESSION_LABEL.fullmatch(f"{label}-4294967295"), label


def test_the_suffix_is_appended_to_a_session_name_too(tmp_path):
    env = {"AI_CONNECT_PEER_SUFFIX": "review"}
    assert session_label(env, tmp_path / "proj", "cross-session") == "s-cross-session-review"
    assert peer_name(env, tmp_path / "proj", "laptop", "cross-session") == "laptop:s-cross-session-review"
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
    assert peer_name({}, project, "dadeush-desktop", title) == "dadeush-desktop:s-Cross-Session"
    missing = claude_session_title(PID, tmp_path / "nowhere")
    assert peer_name({}, tmp_path / "useful-claude-add-ons", "dadeush-desktop", missing) == (
        "dadeush-desktop:useful-claude-add-ons")


# --- two sessions with one name ----------------------------------------------------

def test_two_sessions_with_one_session_name_are_told_apart_by_process_id(tmp_path):
    """Both ask for "<machine>:<session name>"; the Bridge refuses the second, which appends its process id."""
    import asyncio  # pylint: disable=import-outside-toplevel

    first = peer_name({}, tmp_path / "api", "laptop", "cross-session")
    second = peer_name({}, tmp_path / "web", "laptop", "cross-session")
    assert first == second == "laptop:s-cross-session"

    sent: list[dict] = []
    client = BridgeClient("h", 1, second, "t", machine_name="laptop", collision_suffix=str(PID))

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send  # pylint: disable=protected-access
    asyncio.run(client._handle({"type": "error", "code": "name_taken", "error": "held"}))  # pylint: disable=protected-access
    assert sent == [{"type": "register", "name": f"laptop:s-cross-session-{PID}", "standby": False}]
    assert client.peer_name == f"laptop:s-cross-session-{PID}"
    assert SESSION_LABEL.fullmatch(client.peer_name.split(":", 1)[1])
