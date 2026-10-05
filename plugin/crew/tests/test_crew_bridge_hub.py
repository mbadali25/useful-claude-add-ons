"""crew_bridge.py: the main session is the hub, lanes never ring a peer (L-0637).

A real wave is built with test_crew_wave.py's fixtures (`crew_wave.start`, an
isolated worktree under `<main>/.claude/worktrees/`, `crew_wave.lane_init`),
so the lane marker is the one T-0029 writes: the lane file
`.work/autopilot/<slug>/lanes/<id>.json` naming the lane's worktree. A bare
repository under tmp_path is the remote holding the channel. The validator
cases run `_test/validate-prompts.py` on a COPY of the prompt tree.
"""
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_bridge
import crew_wave
import pytest
from test_crew_bridge import CHANNEL, _channel_commit, bell, git
from test_crew_wave import _isolated, _started

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATOR = os.path.join("hooks", "scripts", "_test", "validate-prompts.py")
REFUSAL = "refused - a lane does not message a peer; report the question to the main session"


def _remote(tmp_path, root):
    """origin: a bare repository holding crew-coord/test; returns its tip."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)
    git(root, "remote", "add", "origin", str(bare))
    tip = _channel_commit(root)
    git(root, "push", "-q", "origin", f"{tip}:refs/heads/crew-coord/{CHANNEL}")
    return tip


def _hub(tmp_path):
    """(main checkout, lane worktree, channel tip): lane T-1 of wave `s` initialised."""
    root = _started(tmp_path)
    tip = _remote(tmp_path, root)
    lane = _isolated(root)
    ok, why = crew_wave.lane_init(str(lane), str(root), "s", "T-1")
    assert ok, why
    return root, lane, tip


def run(where, argv, capsys, stdin=b""):
    capsys.readouterr()  # the fixture's own output (approve_as_user prints hook JSON)
    code = crew_bridge.main(argv + ["--channel", CHANNEL, "--remote", "origin", "--root", str(where)],
                            stdin=io.BytesIO(stdin))
    return code, capsys.readouterr().out.splitlines()


def _lane_file(root):
    return root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json"


# --- must-block ---------------------------------------------------------------------

def test_ring_in_a_lane_is_refused(tmp_path, capsys, monkeypatch):
    root, lane, tip = _hub(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "lane-session")
    for argv in (["ring"], ["ring", "--to", "peer-a"]):
        code, lines = run(lane, argv, capsys)
        assert (code, lines) == (1, [REFUSAL])
    assert git(root, "ls-remote", "origin", f"refs/heads/crew-coord/{CHANNEL}").split()[0] == tip


def test_ring_where_the_lane_marker_is_corrupt_is_unknown(tmp_path, capsys):
    root, lane, _ = _hub(tmp_path)
    _lane_file(root).write_text("{not json", encoding="utf-8")
    code, lines = run(lane, ["ring"], capsys)
    assert code == 3
    assert lines and lines[0].startswith("unknown") and not any(l.startswith("crew-doorbell/") for l in lines)


def test_ring_where_a_lane_file_is_unreadable_is_unknown_not_not_a_lane(tmp_path, capsys):
    # A linked worktree no readable lane file names is not yet "not a lane" while
    # another lane file cannot be read: it could be the one naming this worktree.
    root, _, _ = _hub(tmp_path)
    plain = _isolated(root, name="maybe-a-lane")
    other = root / ".work" / "autopilot" / "s" / "lanes" / "T-2.json"
    other.write_text('{"state": "no-such-state"}', encoding="utf-8")
    code, lines = run(plain, ["ring"], capsys)
    assert code == 3 and lines[0].startswith("unknown")


@pytest.mark.parametrize("lane", [{"state": "running"}, {"state": "running", "worktree": ""},
                                  {"state": "running", "worktree": 7}, {"state": "clean", "worktree": ["x"]}],
                         ids=["running-no-worktree", "running-empty", "running-number", "clean-list"])
def test_a_lane_file_without_a_readable_worktree_is_unknown(tmp_path, capsys, lane):
    root, _, _ = _hub(tmp_path)
    plain = _isolated(root, name="maybe-a-lane")
    _lane_file(root).write_text(json.dumps(lane), encoding="utf-8")
    code, lines = run(plain, ["ring"], capsys)
    assert code == 3 and lines[0].startswith("unknown")


@pytest.mark.parametrize("which", ["autopilot", "lanes"])
def test_a_marker_directory_that_cannot_be_looked_up_is_unknown(tmp_path, capsys, monkeypatch, which):
    root, _, _ = _hub(tmp_path)
    plain = _isolated(root, name="maybe-a-lane")
    base = os.path.join(os.path.realpath(str(root)), ".work", "autopilot")
    target = base if which == "autopilot" else os.path.join(base, "s", "lanes")
    real = os.lstat

    def denied(path, *args, **kwargs):
        if os.fspath(path) == target:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(crew_bridge.os, "lstat", denied)
    code, lines = run(plain, ["ring"], capsys)
    assert code == 3 and lines[0].startswith("unknown")


def test_a_pending_lane_without_a_worktree_names_no_worktree(tmp_path, capsys):
    # `start` writes pending lane files with no worktree; lane-init adds it.
    root = _started(tmp_path)
    tip = _remote(tmp_path, root)
    plain = _isolated(root, name="not-a-lane")
    assert run(plain, ["ring"], capsys) == (0, [bell(tip)])


# --- must-allow --------------------------------------------------------------------

def test_ring_in_the_main_checkout_works(tmp_path, capsys):
    root, _, tip = _hub(tmp_path)
    _lane_file(root).write_text("{not json", encoding="utf-8")  # the main checkout is never a lane
    assert run(root, ["ring"], capsys) == (0, [bell(tip)])


def test_ring_in_a_linked_worktree_that_is_not_a_lane_works(tmp_path, capsys):
    root, _, tip = _hub(tmp_path)
    plain = _isolated(root, name="not-a-lane")
    assert run(plain, ["ring"], capsys) == (0, [bell(tip)])
    elsewhere = tmp_path / "elsewhere"
    git(root, "worktree", "add", "-q", "-b", "elsewhere", str(elsewhere))
    assert run(elsewhere, ["ring"], capsys) == (0, [bell(tip)])


def test_receive_works_in_a_lane(tmp_path, capsys):
    _, lane, tip = _hub(tmp_path)
    code, lines = run(lane, ["receive"], capsys, stdin=bell(tip).encode())
    assert code == 0 and lines[-1].startswith("next: crew_coord.py status")


# --- the lane prompt ----------------------------------------------------------------

def test_lane_prompt_returns_a_question_for_another_session_to_the_main_session(tmp_path):
    root = _started(tmp_path)
    text = crew_wave.lane_prompt(str(root), "s", "T-1")
    flat = " ".join(text.split())
    assert "question for another session" in flat
    assert "for the main session to file in the record and ring" in flat
    assert "SendMessage" not in text and "ListAgents" not in text


# --- the prompt validator, on a copy ---------------------------------------------------

def _tree(tmp_path):
    root = tmp_path / "plugin" / "crew"
    shutil.copytree(CREW, root, ignore=shutil.ignore_patterns(
        "tests", "__pycache__", "*.pyc", "evals", "docs"))
    return root


def _validate(root):
    proc = subprocess.run([sys.executable, str(root / VALIDATOR)], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def _grant(path, tool):
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"^tools: (.*)$", lambda m: f"tools: {m.group(1)}, {tool}", text, count=1, flags=re.M)
    assert new != text
    path.write_text(new, encoding="utf-8", newline="\n")


def test_validator_passes_on_the_repo_and_an_untouched_copy(tmp_path):
    assert _validate(pathlib.Path(CREW))[0] == 0
    assert _validate(_tree(tmp_path))[0] == 0


def test_validator_fails_an_agent_granted_send_message(tmp_path):
    root = _tree(tmp_path)
    _grant(root / "agents" / "explorer.md", "SendMessage")
    code, out = _validate(root)
    assert code == 1 and "explorer.md" in out and "SendMessage" in out


def test_validator_fails_an_agent_granted_list_agents(tmp_path):
    root = _tree(tmp_path)
    _grant(root / "agents" / "researcher.md", "ListAgents")
    code, out = _validate(root)
    assert code == 1 and "researcher.md" in out and "ListAgents" in out


def test_validator_fails_a_new_agent_granted_either(tmp_path):
    root = _tree(tmp_path)
    shutil.copy(root / "agents" / "security.md", root / "agents" / "courier.md")
    text = (root / "agents" / "courier.md").read_text(encoding="utf-8")
    (root / "agents" / "courier.md").write_text(text.replace("name: security", "name: courier"),
                                                encoding="utf-8", newline="\n")
    _grant(root / "agents" / "courier.md", "ListAgents")
    code, out = _validate(root)
    assert code == 1 and "courier.md" in out


def test_validator_fails_a_lane_prompt_naming_either_tool(tmp_path):
    root = _tree(tmp_path)
    source = root / "hooks" / "scripts" / "crew_wave.py"
    text = source.read_text(encoding="utf-8")
    anchor = '"Never, at any setting: accepting'
    assert text.count(anchor) == 1
    source.write_text(text.replace(anchor, '"Ask a peer with SendMessage. " ' + anchor), encoding="utf-8",
                      newline="\n")
    code, out = _validate(root)
    assert code == 1 and "lane prompt" in out and "SendMessage" in out


def test_validator_keeps_both_tool_names_known():
    source = pathlib.Path(CREW, VALIDATOR).read_text(encoding="utf-8")
    known = source[source.index("KNOWN_TOOLS = {"):source.index("}", source.index("KNOWN_TOOLS = {"))]
    assert '"ListAgents"' in known and '"SendMessage"' in known
