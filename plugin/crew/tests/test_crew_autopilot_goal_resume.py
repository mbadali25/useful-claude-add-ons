"""T-0056: a running autopilot goal is written into every handoff -- the goal
file's `run` block (`goal_mark`), `running_goals`, and `handoff_resume`, the
one function every handoff writer asks for its `resume:` line.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_goal_resume.py -q

Every repository is built under tmp_path; nothing touches the real one or
~/.claude. The PreCompact skeleton's two flavours run through the real hook
scripts in test_crew_resume_hook.py; the owner's scenario here runs the sh
one where bash is installed.
"""
import json
import os
import subprocess
import sys

import context  # pylint: disable=unused-import
import context_fixtures
import crew_autopilot
import crew_autopilot_goal
import crew_autopilot_handoff as handoff
import crew_fixtures
import crew_resume
import pytest
from scope_fixtures import make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_SCRIPT = os.path.join(_SCRIPTS, "crew_autopilot.py")
_BASH = crew_fixtures.resolve_bash()
TICKETS = [{"title": f"ticket {n}", "risk": "low", "depends_on": [n - 1] if n else []}
           for n in range(3)]
PROPOSAL = {"done_condition": "the three tickets are done", "findings": []}


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read(path):
    with open(str(path), encoding="utf-8") as handle:
        return handle.read()


def _goal(root, goal="ship the export"):
    return crew_autopilot_goal.write_goal(str(root), goal, dict(PROPOSAL),
                                          [dict(t) for t in TICKETS])["slug"]


def _path(root, slug):
    return root / ".work" / "autopilot" / f"{slug}.json"


def _cli(root, *argv):
    return subprocess.run([sys.executable, _SCRIPT, argv[0], "--root", str(root)]
                          + list(argv[1:]), capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def _ticket(root, ticket):
    _write(root / ".work" / "tickets" / ticket / "direction.md", "go\n")


# --- goal_mark ------------------------------------------------------------------

@pytest.mark.parametrize("state", handoff.RUN_STATES)
def test_goal_mark_writes_the_run_block_and_keeps_every_other_key(tmp_path, state):
    root = make_repo(tmp_path, mode="off")
    slug = _goal(root)
    before = json.loads(_read(_path(root, slug)))

    handoff.goal_mark(str(root), slug, state, "T-0002", "a reason")

    after = json.loads(_read(_path(root, slug)))
    run = after.pop("run")
    assert (after, run["state"], run["ticket"], run["reason"], bool(run["at"])) == (
        before, state, "T-0002", "a reason", True)


def test_goal_mark_keeps_the_rest_of_the_file_byte_for_byte(tmp_path):
    root = make_repo(tmp_path, mode="off")
    slug = _goal(root)
    handoff.goal_mark(str(root), slug, "running", "T-0001")
    first = _read(_path(root, slug))

    handoff.goal_mark(str(root), slug, "running", "T-0001")

    strip = lambda text: {k: v for k, v in json.loads(text).items() if k != "run"}  # noqa: E731
    assert (_read(_path(root, slug)).split('"run"')[0] == first.split('"run"')[0],
            strip(first) == strip(_read(_path(root, slug)))) == (True, True)


@pytest.mark.parametrize("slug,state,content", [
    ("ok", "paused", None), ("Bad", "running", None), ("../x", "running", None),
    ("ok", "running", "missing"), ("ok", "running", "{not json"), ("ok", "running", "[1]")])
def test_goal_mark_refuses_and_writes_nothing(tmp_path, slug, state, content):
    root = make_repo(tmp_path, mode="off")
    real = _goal(root)
    path = _path(root, real)
    if content == "missing":
        os.remove(path)
    elif content is not None:
        _write(path, content)
    target = real if slug == "ok" else slug
    before = _read(path) if os.path.exists(path) else None

    with pytest.raises(handoff.MarkError):
        handoff.goal_mark(str(root), target, state)

    assert (_read(path) if os.path.exists(path) else None) == before


def test_goal_mark_failed_replace_keeps_the_old_file(tmp_path, monkeypatch):
    root = make_repo(tmp_path, mode="off")
    slug = _goal(root)
    before = _read(_path(root, slug))

    def boom(*_args, **_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        handoff.goal_mark(str(root), slug, "running", "T-0001")

    assert (_read(_path(root, slug)), sorted(os.listdir(_path(root, slug).parent))) == (
        before, [f"{slug}.json"])


# --- running_goals ----------------------------------------------------------------

def test_running_goals_with_no_folder_is_empty(tmp_path):
    root = make_repo(tmp_path, mode="off")

    assert handoff.running_goals(str(root)) == {"running": [], "stopped": [], "done": [],
                                                "unknown": []}


def test_running_goals_sorts_by_state(tmp_path):
    root = make_repo(tmp_path, mode="off")
    slugs = [_goal(root, goal=f"goal {n}") for n in range(4)]
    for slug, state in zip(slugs, ("running", "stopped", "done")):
        handoff.goal_mark(str(root), slug, state)
    _write(root / ".work" / "autopilot" / "x.proposal.json", "{broken")

    got = handoff.running_goals(str(root))

    assert (got["running"], got["stopped"], got["done"], got["unknown"]) == (
        [slugs[0]], [slugs[1]], [slugs[2]], [])


@pytest.mark.parametrize("content,why", [
    ("{broken", "JSON"), ("[1, 2]", "not a JSON object"),
    ('{"run": {"state": "paused"}}', "paused"), ('{"run": {}}', "None"),
    ('{"run": "running"}', "None")])
def test_running_goals_unreadable_is_unknown_never_dropped(tmp_path, content, why):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".work" / "autopilot" / "bad.json", content)

    got = handoff.running_goals(str(root))

    assert (got["running"], got["done"], len(got["unknown"]),
            ".work/autopilot/bad.json" in got["unknown"][0], why in got["unknown"][0]) == (
        [], [], 1, True, True)


# --- handoff_resume -----------------------------------------------------------------

@pytest.mark.parametrize("states,ticket,line,kind", [
    (["running"], "T-0001", "resume: /crew:autopilot --goal goal-0", "goal"),
    (["running"], None, "resume: /crew:autopilot --goal goal-0", "goal"),
    ([], "T-0001", "resume: /crew:autopilot T-0001", "ticket"),
    ([], None, "resume: none", "none"),
    ([], "T-0009", "resume: none", "none"),
    (["running", "running"], "T-0001", "resume: none", "unknown"),
    (["running", "unknown"], "T-0001", "resume: none", "unknown"),
    (["unknown"], "T-0001", "resume: none", "unknown"),
    (["stopped"], "T-0001", "resume: /crew:autopilot T-0001", "ticket"),
    (["done"], None, "resume: none", "none"),
    ([None], "T-0001", "resume: /crew:autopilot T-0001", "ticket"),
], ids=["one-running", "one-running-no-ticket", "ticket", "nothing", "ticket-no-folder",
        "two-running", "running-and-unknown", "unknown", "stopped", "done", "not-started"])
def test_handoff_resume_cases(tmp_path, states, ticket, line, kind):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, "T-0001")
    for n, state in enumerate(states):
        slug = _goal(root, goal=f"goal {n}")
        if state == "unknown":
            _write(_path(root, slug), "{broken")
        elif state:
            handoff.goal_mark(str(root), slug, state)

    got = handoff.handoff_resume(str(root), ticket)

    named = f"goal-{len(states) - 1}" in got["reason"] if kind == "unknown" else True
    assert (got["line"], got["kind"], named) == (line, kind, True)


@pytest.mark.parametrize("state,ticket", [("running", "T-0001"), (None, "T-0001"),
                                          (None, None), ("two", None)])
def test_handoff_resume_line_parses_with_crew_resume(tmp_path, state, ticket):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, "T-0001")
    if state == "running":
        handoff.goal_mark(str(root), _goal(root), "running")
    elif state == "two":
        for n in range(2):
            handoff.goal_mark(str(root), _goal(root, goal=f"g {n}"), "running")

    line = handoff.handoff_resume(str(root), ticket)["line"]
    parsed = crew_resume.parse_resume(line + "\n")

    assert (("resume: " + crew_resume.render(parsed)) if parsed["ok"] else parsed["reason"]) == (
        line if line != "resume: none" else "resume: none")


def test_handoff_resume_cli(tmp_path):
    root = make_repo(tmp_path, mode="off")
    slug = _goal(root)
    handoff.goal_mark(str(root), slug, "running", "T-0001")

    out = _cli(root, "handoff-resume", "--ticket", "T-0001")

    assert (out.returncode, out.stdout.splitlines()[0], out.stdout.splitlines()[1].split()[0]) == (
        0, f"resume: /crew:autopilot --goal {slug}", "kind=goal")


def test_handoff_resume_cli_crash_says_none_and_unknown(tmp_path):
    root = make_repo(tmp_path, mode="off")

    out = _cli(root, "handoff-resume", "--ticket", "not a ticket")

    assert (out.returncode, out.stdout.splitlines()[:1], out.stdout.splitlines()[1][:12]) == (
        0, ["resume: none"], "kind=unknown")


@pytest.mark.parametrize("state,code,first", [("running", 0, "marked=1"),
                                              ("paused", 2, "marked=0 reason=state")])
def test_goal_mark_cli(tmp_path, state, code, first):
    root = make_repo(tmp_path, mode="off")
    slug = _goal(root)

    out = _cli(root, "goal-mark", "--goal", slug, "--state", state, "--ticket", "T-0001")

    assert (out.returncode, out.stdout.startswith(first)) == (code, True)


# --- the owner's scenario, part (a) -------------------------------------------------

def _minted_goal(tmp_path, monkeypatch):
    """A crew repo (context_fixtures, so the PreCompact hook writes) with a goal
    at ticket 2 of 3: ticket 1 done, goal-run picked ticket 2."""
    root = context_fixtures.make_repo(tmp_path)
    config = json.loads(_read(root / ".crew" / "config.json"))
    config.update({"tracker": "files", "scope": {"mode": "off", "allowCliApproval": True},
                   "autopilot": {"mode": "backlog", "approval": "self"}})
    _write(root / ".crew" / "config.json", json.dumps(config))
    slug = _goal(root)
    assert crew_autopilot.main(["goal-approve", "--root", str(root), "--goal", slug]) == 0
    index = root / ".work" / "INDEX.md"
    _write(index, _read(index).replace("T-0001 | ready |", "T-0001 | done |"))
    transcript = tmp_path / "t.jsonl"
    _write(transcript, json.dumps({"type": "assistant", "timestamp": "2026-10-05T00:00:00Z",
                                   "message": {"usage": {"input_tokens": 1,
                                                         "output_tokens": 1}}}) + "\n")
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    got = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(transcript))
    assert (got["ticket"], got["stop"]) == ("T-0002", False), got
    monkeypatch.chdir(root)
    return root, slug


def test_goal_survives_a_handoff_from_every_writer(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    want = f"resume: /crew:autopilot --goal {slug}"
    low_context = handoff.handoff_resume(str(root), "T-0002")["line"]
    command = _cli(root, "handoff-resume", "--ticket", "T-0002").stdout.splitlines()[0]
    skeleton = None
    if _BASH:
        home = tmp_path / "home"
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), CLAUDE_PROJECT_DIR=str(root),
                   CREW_AUTOCLEAR_INHIBIT="1")
        payload = {"hook_event_name": "PreCompact", "session_id": "s9", "cwd": str(root),
                   "trigger": "auto", "transcript_path": str(root / "none.jsonl")}
        subprocess.run([_BASH, os.path.join(_SCRIPTS, "handoff-write.sh")], cwd=str(root),
                       env=env, input=json.dumps(payload), capture_output=True, text=True,
                       check=False, timeout=120)
        skeleton = [l for l in _read(root / ".work" / "HANDOFF.md").splitlines()
                    if l.startswith("resume:")]

    assert (low_context, command, skeleton if _BASH else [want]) == (want, want, [want])
