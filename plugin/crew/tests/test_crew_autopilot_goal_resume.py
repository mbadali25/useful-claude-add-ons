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

    def strip(text):
        return {k: v for k, v in json.loads(text).items() if k != "run"}
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
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
                    "-q", "--allow-empty", "-m", "ticket 3 starts"], cwd=str(root), check=True)

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


@pytest.mark.parametrize("fallback", [True, False], ids=["stop-file", "nothing-writable"])
def test_a_failed_stop_mark_is_named_in_the_stop(tmp_path, monkeypatch, fallback):
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    if not fallback:
        monkeypatch.setattr(handoff, "stop_mark_fallback",
                            lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    for ticket in ("T-0002", "T-0003"):
        index = root / ".work" / "INDEX.md"
        _write(index, _read(index).replace(f"{ticket} | ready |", f"{ticket} | done |"))

    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")
    monkeypatch.setattr(handoff, "goal_mark", boom)
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel

    got = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(tmp_path / "t.jsonl"))

    assert (got["stop"], got["done"], "may still say running" in got["reason"],
            "goal-mark" in got["reason"], crew_goal_state.run_state(str(root), slug)["state"]) == (
        True, True, not fallback, not fallback, "done" if fallback else "running")


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


# --- L-0658 review round 2: the SessionStart staleness rule ------------------------------

@pytest.mark.parametrize("state,stale", [("running", False), ("stopped", False), ("done", False)])
def test_a_goal_handoff_is_not_archived_for_branch_drift(tmp_path, monkeypatch,
                                                                 state, stale):
    """L-0658 review r4: whatever the run state, the goal file judges a goal
    handoff (a stopped goal is named when it is read), never branch drift."""
    import crew_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    if state != "running":
        handoff.goal_mark(str(root), slug, state)
    _goal_handoff(root, slug)  # branch: and head: name another branch
    text = _read(root / ".work" / "HANDOFF.md").replace(
        "written: 2026-10-05T00:00:00Z", "written: " + __import__("time").strftime(
            "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()))
    _write(root / ".work" / "HANDOFF.md", text)

    verdict = crew_state.handoff_staleness(str(root), text)
    archived = crew_state.archive_stale_handoff(str(root), {})

    assert (verdict["stale"], archived["archived"],
            os.path.exists(root / ".work" / "HANDOFF.md")) == (stale, stale, not stale)


def test_two_resume_lines_keep_the_drift_check(tmp_path, monkeypatch):
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    _root, slug = _minted_goal(tmp_path, monkeypatch)
    text = f"resume: /crew:autopilot --goal {slug}\nresume: /crew:done T-0001\n"

    assert crew_goal_state.goal_handoff(text) is False


@pytest.mark.parametrize("how", ["dangling-link", "a-file"])
def test_a_goal_folder_that_is_not_a_directory_is_unknown_not_missing(tmp_path, monkeypatch, how):
    """L-0658 review r3: `.work/autopilot` that is a dangling link (or a file)
    makes every goal file under it unreadable, never absent."""
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    folder = root / ".work" / "autopilot"
    import shutil  # pylint: disable=import-outside-toplevel
    shutil.rmtree(folder)
    if how == "dangling-link":
        os.symlink(str(tmp_path / "gone"), str(folder))
    else:
        _write(folder, "not a folder")
    _goal_handoff(root, slug)

    got = crew_autopilot.resume_target(str(root))

    assert (crew_goal_state.run_state(str(root), slug)["state"], got["stop"],
            "could not read" in got["reason"]) == ("unknown", True, True)


# --- group review fixes (G6b, 2026-10-07) ----------------------------------------------------

def test_a_second_disagreement_keeps_the_running_goal(tmp_path, monkeypatch):
    """L-0659 review r1: a ticket handoff that also disagrees with the disk keeps
    the running-goal note beside its own."""
    root, slug = _minted_goal(tmp_path, monkeypatch)
    crew_ticket_activate(root, "T-0002")
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root),
                            capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                          capture_output=True, text=True, check=True).stdout.strip()
    _write(root / ".work" / "HANDOFF.md",
           f"# Handoff\nbranch: {branch}\nhead: {head}\nresume: /crew:done T-0002\n")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], "the handoff says /crew:done T-0002" in got["disagreement"],
            f"goal {slug} is running" in got["disagreement"]) == ("T-0002", "handoff", True, True)


def test_running_goal_note_names_a_goal_file_it_cannot_read(tmp_path, monkeypatch):
    """L-0659 review r1: the handoff still wins, but the unknown is named."""
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    root, _slug = _minted_goal(tmp_path, monkeypatch)
    _write(root / ".work" / "autopilot" / "broken.json", "{not json")

    note = crew_autopilot_backlog.running_goal_note(str(root))

    assert ("could not tell whether an autopilot goal is running" in note,
            "broken.json" in note) == (True, True)


@pytest.mark.parametrize("how", ["dangling-link", "a-file"])
def test_goal_discovery_reads_a_folder_that_is_not_one_as_unknown(tmp_path, how):
    """L-0659 / T-0056 review: `.work/autopilot` that is a dangling link (or a
    file) is could-not-tell for discovery too, never "no goals"."""
    root = make_repo(tmp_path)
    folder = root / ".work" / "autopilot"
    folder.parent.mkdir(parents=True, exist_ok=True)
    if how == "a-file":
        _write(folder, "not a folder")
    else:
        try:
            os.symlink(str(root / "gone"), str(folder))
        except (OSError, NotImplementedError):
            pytest.skip("cannot make a symlink here - NOT run")

    got = handoff.running_goals(str(root))

    assert (got["running"], len(got["unknown"]), ".work/autopilot" in got["unknown"][0]) == (
        [], 1, True)


def test_an_uppercase_goal_file_name_is_unknown_not_no_goal(tmp_path, monkeypatch):
    """T-0056 review r3: SHIP-IT.JSON opens as ship-it on a case-insensitive
    filesystem and not on a case-sensitive one: either way it is named."""
    root, slug = _minted_goal(tmp_path, monkeypatch)
    folder = root / ".work" / "autopilot"
    os.replace(str(folder / f"{slug}.json"), str(folder / "tmp-name"))
    os.replace(str(folder / "tmp-name"), str(folder / f"{slug.upper()}.JSON"))

    got = handoff.running_goals(str(root))

    assert (got["running"], [u for u in got["unknown"] if "not lowercase" in u] != []) == (
        [], True)


def test_the_wrap_up_dirty_step_keeps_a_goal_line():
    """T-0056 review r3: `--wrap-up` on a dirty tree still writes a goal line."""
    with open(os.path.join(context._ROOT, "commands", "handoff.md"),  # pylint: disable=protected-access
              encoding="utf-8") as handle:
        text = handle.read()
    dirty = [line for line in text.splitlines() if line.startswith("3. Dirty:")]

    assert (len(dirty), "goal line" in dirty[0], "still wins" in dirty[0]) == (1, True, True)


def test_a_goal_file_naming_a_ticket_it_did_not_mint_is_refused(tmp_path, monkeypatch):
    """L-0541 review r6 (must-block): an id in the goal file counts only when that
    ticket's direction.md carries this goal's mark for its place."""
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    _write(root / ".work" / "tickets" / "T-0009" / "direction.md", "someone else's ticket\n")
    path = root / ".work" / "autopilot" / f"{slug}.json"
    goal = json.loads(_read(path))
    goal["tickets"][1]["id"] = "T-0009"
    _write(path, json.dumps(goal))

    pick = crew_autopilot_backlog.next_goal_ticket(str(root), slug)
    code, text = crew_autopilot_backlog.ticket_approve(str(root), slug, "T-0009")

    assert (pick["ticket"], pick["stop"], "did not mint it" in pick["reason"], code,
            "did not mint it" in text) == (None, True, True, 2, True)


@pytest.mark.parametrize("usage", [[2100000, -2100000], [None, 1], ["5", 1], [True, 1]])
def test_a_usage_count_that_is_not_a_non_negative_integer_is_unknown(tmp_path, usage):
    """L-0541 review r6: a negative (or non-integer) count never lowers the total."""
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    transcript = tmp_path / "t.jsonl"
    _write(transcript, "".join(json.dumps({
        "type": "assistant", "timestamp": "2026-10-05T00:00:00Z",
        "message": {"usage": {"input_tokens": n, "output_tokens": 0}}}) + "\n" for n in usage))

    assert crew_autopilot_backlog.session_tokens(str(transcript))[0] is None


def test_a_stop_that_cannot_reach_the_goal_file_is_still_a_stop(tmp_path, monkeypatch):
    """T-0056 review r4 (must-block): the stop goes to `<slug>.stop`, which every
    reader takes over a goal file still saying running; an explicit run clears it."""
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    real = handoff.goal_mark

    def refuse(top, goal, state, *rest, **kw):
        if state != "running":
            raise handoff.MarkError("goal lock busy")
        return real(top, goal, state, *rest, **kw)
    monkeypatch.setattr(handoff, "goal_mark", refuse)

    got = crew_autopilot_backlog._marked(str(root), slug, {  # pylint: disable=protected-access
        "ticket": None, "stop": True, "done": False, "reason": "owner decides"})
    stopped = (crew_goal_state.run_state(str(root), slug)["state"],
               handoff.running_goals(str(root))["stopped"],
               handoff.handoff_resume(str(root), "T-0002")["kind"])
    monkeypatch.setattr(handoff, "goal_mark", real)
    handoff.goal_mark(str(root), slug, "running", "T-0002")

    assert (".stop instead" in got["reason"], stopped,
            crew_goal_state.run_state(str(root), slug)["state"]) == (
        True, ("stopped", [slug], "ticket"), "running")


def test_goal_mark_reads_the_stop_reason_from_a_file(tmp_path, monkeypatch):
    """T-0056 review r4: the reason never goes on a command line."""
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    _write(root / ".work" / "autopilot" / f"{slug}.reason", "waiting on the owner's `$(x)` call\n")

    code = crew_autopilot.main(["goal-mark", "--root", str(root), "--goal", slug, "--state",
                                "stopped", "--reason-file",
                                str(root / ".work" / "autopilot" / f"{slug}.reason")])

    assert (code, crew_goal_state.run_state(str(root), slug)["reason"]) == (
        0, "waiting on the owner's `$(x)` call")


def test_a_discovered_goal_run_never_resumes_past_a_stop(tmp_path, monkeypatch):
    """L-0659 review r2 (must-block): a goal found by discovery or a handoff is
    run only while it still reads running; the owner's `--goal` still restarts it."""
    import crew_autopilot_backlog  # pylint: disable=import-outside-toplevel
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    handoff.goal_mark(str(root), slug, "stopped", None, "the owner stopped it")
    transcript = tmp_path / "t.jsonl"

    found = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(transcript),
                                            discovered=True)
    kept = crew_goal_state.run_state(str(root), slug)
    refused = None
    try:
        handoff.goal_mark(str(root), slug, "running", "T-0002", only_if_running=True)
    except handoff.MarkError as exc:
        refused = str(exc)
    chosen = crew_autopilot_backlog.goal_run(str(root), slug, "s1", str(transcript))

    assert (found["stop"], "no longer running" in found["reason"], kept["state"],
            kept["reason"], "no longer running" in (refused or ""), chosen["ticket"],
            crew_goal_state.run_state(str(root), slug)["state"]) == (
        True, True, "stopped", "the owner stopped it", True, "T-0002", "running")


def test_the_precompact_skeleton_header_may_carry_the_goal_line():
    """T-0056 review r5 (must-allow / must-block): only the header's goal line is
    read; a resume-like file name under Changed files is still never one."""
    import crew_autocycle  # pylint: disable=import-outside-toplevel
    head = "# Handoff\nwritten: x\nbranch: b\nhead: h\n"
    body = ("\n## Changed files\nresume: /crew:status\n\n## Next action\n"
            + crew_autocycle.SKELETON_MARK + " at compaction.\n")

    with_goal = crew_resume.parse_resume(head + "resume: /crew:autopilot --goal ship-it\n" + body)
    without = crew_resume.parse_resume(head + body)
    ticket_line = crew_resume.parse_resume(head + "resume: /crew:done T-1\n" + body)

    assert ((with_goal["ok"], with_goal["kind"], with_goal["arg"]), without["ok"],
            ticket_line["ok"]) == ((True, "goal", "ship-it"), False, False)


def test_a_run_state_on_a_file_that_is_not_a_goal_is_unknown(tmp_path):
    """L-0659 review r3: `{"run": {"state": "done"}}` alone is no goal file."""
    root = _repo(tmp_path)
    _write(root / ".work" / "autopilot" / "bad.json", '{"run": {"state": "done"}}')

    got = handoff.running_goals(str(root))

    assert (got["done"], len(got["unknown"]), "not a goal file" in got["unknown"][0]) == (
        [], 1, True)


def test_the_handoff_reader_matches_discovery_on_names_and_bom(tmp_path, monkeypatch):
    """L-0658 review r6: a UTF-8 BOM reads; a goal file name that is not the
    lowercase slug is unknown here as in discovery."""
    import crew_goal_state  # pylint: disable=import-outside-toplevel
    root, slug = _minted_goal(tmp_path, monkeypatch)
    path = root / ".work" / "autopilot" / f"{slug}.json"
    with open(str(path), "rb") as handle:
        raw = handle.read()
    with open(str(path), "wb") as handle:
        handle.write(b"\xef\xbb\xbf" + raw)
    bom = crew_goal_state.run_state(str(root), slug)["state"]
    os.replace(str(path), str(path.parent / "tmp-name"))
    os.replace(str(path.parent / "tmp-name"), str(path.parent / f"{slug.upper()}.json"))

    assert (bom, crew_goal_state.run_state(str(root), slug.upper().lower())["state"]) == (
        "running", "missing" if os.path.normcase("A") == "A" else "unknown")


def test_a_json_whose_name_is_not_a_slug_is_unknown_never_dropped(tmp_path):
    """T-0056 review r6: `ship_it.json` (a renamed goal file) makes the handoff say
    `resume: none` with a reason, never the ticket form."""
    root = _repo(tmp_path)
    _write(root / ".work" / "autopilot" / "ship_it.json", '{"run": {"state": "running"}}')
    _write(root / ".work" / "autopilot" / "x.proposal.json", "{}")

    got = handoff.running_goals(str(root))

    assert (got["running"], [u for u in got["unknown"] if "ship_it.json" in u] != [],
            [u for u in got["unknown"] if "proposal" in u]) == ([], True, [])
