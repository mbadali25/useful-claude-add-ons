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


def _repo(tmp_path, mode="plan"):
    """A repo with autopilot armed: handoff_resume names a running goal only
    while autopilot can continue it (T-0056 review round 2)."""
    root = make_repo(tmp_path, mode="off")
    _write(root / ".crew" / "config.json", json.dumps({"scope": {"mode": "off"},
                                                       "autopilot": {"mode": mode}}))
    return root


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
    root = _repo(tmp_path)
    slug = _goal(root)
    before = json.loads(_read(_path(root, slug)))

    handoff.goal_mark(str(root), slug, state, "T-0002", "a reason")

    after = json.loads(_read(_path(root, slug)))
    run = after.pop("run")
    assert (after, run["state"], run["ticket"], run["reason"], bool(run["at"])) == (
        before, state, "T-0002", "a reason", True)


def test_goal_mark_keeps_the_rest_of_the_file_byte_for_byte(tmp_path):
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)

    assert handoff.running_goals(str(root)) == {"running": [], "stopped": [], "done": [],
                                                "unknown": []}


def test_running_goals_sorts_by_state(tmp_path):
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
    slug = _goal(root)
    handoff.goal_mark(str(root), slug, "running", "T-0001")

    out = _cli(root, "handoff-resume", "--ticket", "T-0001")

    assert (out.returncode, out.stdout.splitlines()[0], out.stdout.splitlines()[1].split()[0]) == (
        0, f"resume: /crew:autopilot --goal {slug}", "kind=goal")


def test_handoff_resume_cli_crash_says_none_and_unknown(tmp_path):
    root = _repo(tmp_path)

    out = _cli(root, "handoff-resume", "--ticket", "not a ticket")

    assert (out.returncode, out.stdout.splitlines()[:1], out.stdout.splitlines()[1][:12]) == (
        0, ["resume: none"], "kind=unknown")


@pytest.mark.parametrize("state,code,first", [("running", 0, "marked=1"),
                                              ("paused", 2, "marked=0 reason=state")])
def test_goal_mark_cli(tmp_path, state, code, first):
    root = _repo(tmp_path)
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


# --- L-0658: a --goal handoff is checked against the goal file -----------------------

def _goal_handoff(root, slug, branch="some-other-branch", head="0123456789"):
    _write(root / ".work" / "HANDOFF.md",
           f"# Handoff\nwritten: 2026-10-05T00:00:00Z\nbranch: {branch}\nhead: {head}\n"
           f"resume: /crew:autopilot --goal {slug}\n\n## Next action\ncontinue the goal\n")


def test_goal_handoff_survives_a_branch_switch(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    _goal_handoff(root, slug)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["stop"], got["goal"]) == (
        "T-0002", "handoff", False, slug)


@pytest.mark.parametrize("state,stops,words", [
    ("missing", False, "does not exist"),
    ("not-json", True, "could not read"),
    ("done", False, "is done"),
    ("stopped", True, "token cap"),
    ("paused", True, "could not read"),
    ("no-run", False, "has not started"),
])
def test_goal_handoff_not_running_is_not_taken(tmp_path, monkeypatch, state, stops, words):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    path = _path(root, slug)
    data = json.loads(_read(path))
    if state == "missing":
        os.remove(path)
    elif state == "not-json":
        _write(path, "{cut")
    elif state == "no-run":
        data.pop("run")
        _write(path, json.dumps(data))
    else:
        data["run"] = {"state": state, "ticket": "T-0002", "reason": "token cap reached"}
        _write(path, json.dumps(data))
    _goal_handoff(root, slug)

    got = crew_autopilot.resume_target(str(root))
    shown = crew_autopilot.status(str(root))["resume_line"]

    reason = got["reason"] if stops else " ".join(got["fallthrough"])
    assert (got["stop"] if stops else got["source"] != "handoff", words in reason,
            got["goal"] == slug if stops else got.get("goal") is None,
            shown.startswith(f"not usable: /crew:autopilot --goal {slug} - "),
            "token cap" in shown) == (True, True, True, True, False)


def test_ticket_handoff_branch_mismatch_still_falls_through(tmp_path, monkeypatch):
    root, _slug = _minted_goal(tmp_path, monkeypatch)
    _write(root / ".work" / "HANDOFF.md",
           "# Handoff\nbranch: some-other-branch\nhead: 0123456789\n"
           "resume: /crew:autopilot T-0002\n")

    got = crew_autopilot.resume_target(str(root))
    shown = crew_autopilot.status(str(root))["resume_line"]

    assert (got["source"] != "handoff", "branch:" in " ".join(got["fallthrough"]),
            shown.endswith("its branch: does not match this checkout")) == (True, True, True)


def test_status_shows_a_running_goal_handoff_as_usable_across_branches(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    _goal_handoff(root, slug)

    shown = crew_autopilot.status(str(root))["resume_line"]

    assert shown == f"/crew:autopilot --goal {slug} (usable)"


def test_goal_resumes_after_switching_to_the_next_ticket_branch(tmp_path, monkeypatch):
    """The owner's scenario, part (b): goal at ticket 2 of 3, a handoff written
    on ticket 2's branch, ticket 3's branch checked out, resume continues."""
    root, slug = _minted_goal(tmp_path, monkeypatch)
    subprocess.run(["git", "checkout", "-q", "-b", "T-0002-build"], cwd=str(root), check=True)
    _write(root / ".work" / "HANDOFF.md", "# Handoff\nbranch: T-0002-build\nhead: "
           + subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                            capture_output=True, text=True, check=True).stdout.strip()
           + "\n" + handoff.handoff_resume(str(root), "T-0002")["line"] + "\n")
    index = root / ".work" / "INDEX.md"
    _write(index, _read(index).replace("T-0002 | ready |", "T-0002 | done |"))
    subprocess.run(["git", "checkout", "-q", "-b", "T-0003-build"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "ticket 3 starts"],
                   cwd=str(root), check=True)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["stop"], got["goal"]) == (
        "T-0003", "handoff", False, slug)


# --- T-0056 review round 1 -----------------------------------------------------------

def test_an_unlistable_goal_folder_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _ticket(root, "T-0001")
    handoff.goal_mark(str(root), _goal(root), "running")
    real = os.listdir

    def denied(path):
        if str(path).endswith(os.path.join(".work", "autopilot")):
            raise PermissionError(13, "denied")
        return real(path)
    monkeypatch.setattr(os, "listdir", denied)

    got = handoff.handoff_resume(str(root), "T-0001")

    assert (got["line"], got["kind"], ".work/autopilot/" in got["reason"]) == (
        "resume: none", "unknown", True)


def test_a_run_that_cannot_be_marked_running_stops(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    index = root / ".work" / "INDEX.md"
    _write(index, _read(index).replace("T-0002 | ready |", "T-0002 | done |"))

    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")
    monkeypatch.setattr(handoff, "goal_mark", boom)
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    transcript = tmp_path / "t.jsonl"

    got = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(transcript))

    assert (got["ticket"], got["stop"], "could not record" in got["reason"]) == (
        None, True, True)


# --- L-0659: bare /crew:autopilot finds a running goal ---------------------------------

def _second_goal(root, state="running", text=None):
    slug = _goal(root, goal="another goal")
    if text is not None:
        _write(_path(root, slug), text)
    else:
        handoff.goal_mark(str(root), slug, state, None, "token cap reached")
    return slug


def test_bare_resume_finds_the_one_running_goal(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["goal"], got["stop"],
            "no .work/HANDOFF.md" in got["fallthrough"]) == (
        "T-0002", "goal-file", slug, False, True)


def test_two_running_goals_stop_and_list_both(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    other = _second_goal(root)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], slug in got["reason"], other in got["reason"],
            "name one: /crew:autopilot --goal <slug>" in got["reason"]) == (
        None, True, True, True, True)


@pytest.mark.parametrize("text", ["{cut", "[1]", '{"run": {"state": "paused"}}'])
@pytest.mark.parametrize("beside", [True, False], ids=["beside-running", "alone"])
def test_unreadable_goal_file_stops_bare_resume(tmp_path, monkeypatch, text, beside):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    if not beside:
        handoff.goal_mark(str(root), slug, "done")
    crew_ticket_activate(root, "T-0002")
    bad = _second_goal(root, text=text)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], f".work/autopilot/{bad}.json" in got["reason"],
            "could not be read" in got["reason"]) == (None, True, True, True)


def crew_ticket_activate(root, ticket):
    import crew_ticket  # pylint: disable=import-outside-toplevel
    crew_ticket.activate(str(root), ticket)


def test_stopped_goal_is_named_not_resumed(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    handoff.goal_mark(str(root), slug, "stopped", "T-0002", "token cap reached")
    crew_ticket_activate(root, "T-0002")

    got = crew_autopilot.resume_target(str(root))

    note = [w for w in got["fallthrough"] if slug in w]
    assert (got["ticket"], got["source"], got["goal"], len(note),
            "token cap reached" in note[0], f"/crew:autopilot --goal {slug}" in note[0]) == (
        "T-0002", "active-ticket", None, 1, True, True)


@pytest.mark.parametrize("how", ["done", "no-folder"])
def test_no_goal_keeps_todays_order(tmp_path, monkeypatch, how):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    crew_ticket_activate(root, "T-0002")
    if how == "done":
        handoff.goal_mark(str(root), slug, "done")
    else:
        import shutil  # pylint: disable=import-outside-toplevel
        shutil.rmtree(root / ".work" / "autopilot")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["goal"], got["fallthrough"],
            got["disagreement"]) == ("T-0002", "active-ticket", None, ["no .work/HANDOFF.md"], "")


def test_argument_wins_over_a_running_goal(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    _second_goal(root)
    crew_ticket_activate(root, "T-0002")

    by_ticket = crew_autopilot.resume_target(str(root), ticket="T-0002")
    by_goal = crew_autopilot.resume_target(str(root), goal=slug)

    assert ((by_ticket["source"], by_ticket["stop"], by_ticket["goal"]),
            (by_goal["source"], by_goal["ticket"], by_goal["stop"])) == (
        ("argument", False, None), (f"goal:{slug}", "T-0002", False))


def test_a_usable_ticket_handoff_wins_and_names_the_goal(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    crew_ticket_activate(root, "T-0002")
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root),
                            capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                          capture_output=True, text=True, check=True).stdout.strip()
    _write(root / ".work" / "HANDOFF.md",
           f"# Handoff\nbranch: {branch}\nhead: {head}\nresume: /crew:autopilot T-0002\n")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], slug in got["disagreement"]) == (
        "T-0002", "handoff", True)


def test_status_shows_the_running_goal_bare_would_take(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    before = sorted(os.listdir(root / ".work" / "autopilot"))

    text = crew_autopilot.status_text(crew_autopilot.status(str(root)))

    assert (text.splitlines()[1], len(text.splitlines()) <= crew_autopilot.STATUS_MAX_LINES,
            sorted(os.listdir(root / ".work" / "autopilot")) == before) == (
        f"ticket: T-0002 (from goal-file, goal {slug})", True, True)


def test_goal_resumes_after_a_crash(tmp_path, monkeypatch):
    """The owner's scenario, part (c): goal at ticket 2 of 3, the session dies
    with no handoff; a new session's bare run resumes ticket 2 at its phase."""
    root, slug = _minted_goal(tmp_path, monkeypatch)
    assert not os.path.exists(root / ".work" / "HANDOFF.md")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["goal"], got["next"]["phase"], got["activate"]) == (
        "T-0002", slug, crew_autopilot.next_phase(str(root), "T-0002")["phase"], True)


# --- review round 2 (T-0056), round 1 (L-0658) -------------------------------------------

def test_a_running_goal_while_autopilot_is_off_is_unknown(tmp_path):
    root = _repo(tmp_path, mode="off")
    _ticket(root, "T-0001")
    handoff.goal_mark(str(root), _goal(root), "running")

    got = handoff.handoff_resume(str(root), "T-0001")

    assert (got["line"], got["kind"], "not armed" in got["reason"]) == (
        "resume: none", "unknown", True)


def test_goal_run_unarmed_marks_the_goal_stopped(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    config = json.loads(_read(root / ".crew" / "config.json"))
    config["autopilot"]["mode"] = "off"
    _write(root / ".crew" / "config.json", json.dumps(config))
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel

    got = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(tmp_path / "t.jsonl"))

    assert (got["stop"], json.loads(_read(_path(root, slug)))["run"]["state"]) == (
        True, "stopped")


def test_a_failed_stop_mark_is_named_in_the_stop(tmp_path, monkeypatch):
    root, slug = _minted_goal(tmp_path, monkeypatch)
    for ticket in ("T-0002", "T-0003"):
        index = root / ".work" / "INDEX.md"
        _write(index, _read(index).replace(f"{ticket} | ready |", f"{ticket} | done |"))

    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")
    monkeypatch.setattr(handoff, "goal_mark", boom)
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel

    got = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(tmp_path / "t.jsonl"))

    assert (got["stop"], got["done"], "may still say running" in got["reason"],
            "goal-mark" in got["reason"]) == (True, True, True, True)


def test_a_goal_file_that_cannot_be_looked_up_is_unknown(tmp_path, monkeypatch):
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path)
    real = os.lstat

    def denied(path, *args, **kwargs):
        if str(path).endswith("ship-it.json"):
            raise PermissionError(13, "denied")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "lstat", denied)

    got = crew_goal_state.handoff_refusal(str(root), "ship-it")

    assert (got[0], "could not read" in got[1]) == ("unknown", True)
