"""The auto wrap-up -> auto-clear -> auto-resume cycle, as ONE opt-in feature.

Must-block / must-allow pairs for each rule the cycle depends on:

  - wrap-up blocks once per threshold crossing, keyed on the payload's
    session_id, and never blocks on a stop_hook_active continuation -- but
    that continuation IS the turn auto-clear has to run on;
  - two sessions in one repo do not share a marker, and one session's
    SessionStart does not re-arm another's;
  - a clear needs a verified handoff from THIS session and a trustworthy
    context reading behind the wrap-up;
  - an unknown / estimated / stale reading, or a marker that is not the
    hook's JSON at all, never clears;
  - the target window is identified uniquely (owner pid first, title as a
    fallback that refuses on zero or several), or nothing is typed;
  - the handoff and its next action come back after a clear, inside the
    3,000-char resume budget, with no initialUserMessage.

Both flavours run wherever their interpreter exists. The .ps1 ones are told
they are on Windows (`OS=Windows_NT`) and get a stubbed window list through
CREW_AUTOCLEAR_WINDOW_STUB, so they run on a Linux pwsh too. Every run sets
CREW_AUTOCLEAR_INHIBIT and points HOME at the fixture: no case can read the
developer's real opt-in, enumerate a real window, or send a keystroke.
"""
import json
import os
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import context_fixtures
import crew_autocycle
import crew_fixtures

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
FLAVORS = [f for f, have in (("sh", _BASH), ("ps1", _PWSH)) if have]
# There is no python driver here: the rules live in the two wrappers. Four
# tests (`by_flavor`) are the per-shell parity sample run by default -- a
# wrap-up block, a stop_hook_active stand-down, a clear sent, and the resume
# end to end. Every other test (`by_flavor_matrix`) is `slow` in both
# flavours: `pytest -m slow` or `--run-slow` (conftest.py).
by_flavor = pytest.mark.parametrize("flavor", FLAVORS)
by_flavor_matrix = pytest.mark.parametrize(
    "flavor", [pytest.param(f, marks=crew_fixtures.SLOW) for f in FLAVORS])

SESSION_A = "11111111-aaaa-4aaa-8aaa-000000000001"
SESSION_B = "22222222-bbbb-4bbb-8bbb-000000000002"
GOOD_HANDOFF = (
    "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
    "## Done\n- a thing\n\n## Next action\nRun the NEXT-ACTION-TOKEN migration.\n")
_PS_ARGS = {"--session": "-Session", "--dry-run": "-DryRun", "--root": "-Root", "--force": "-Force"}


# --- plumbing --------------------------------------------------------------

def _script(flavor, name):
    path = os.path.join(_SCRIPTS, f"{name}.{flavor}")
    return path.replace("\\", "/") if flavor == "sh" else path


def _invoke(flavor, name, root, payload=None, args=(), env_extra=None):
    home = str(root.parent / "home")
    env = dict(os.environ, HOME=home, USERPROFILE=home, CREW_AUTOCLEAR_INHIBIT="1",
               CLAUDE_PROJECT_DIR=str(root),
               CREW_VAULT_OPS=str(root.parent / "absent-vault-ops.py"),
               CREW_OBSIDIAN_CONFIG=str(root.parent / "absent-obsidian.json"))
    if flavor == "ps1":
        env["OS"] = "Windows_NT"
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _script(flavor, name),
               *[_PS_ARGS.get(a, a) for a in args]]
    else:
        cmd = [_BASH, _script(flavor, name), *args]
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True,
                          input=json.dumps(payload) if payload is not None else "",
                          check=False, timeout=120)


def _machine(root, enabled=True, **auto):
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    block = dict(auto)
    if enabled is not None:
        block["enabled"] = enabled
    (crew / "config.json").write_text(json.dumps({"context": {"autoClear": block}}), encoding="utf-8")


def _context_cfg(**auto):
    cfg = {"warnAt": 0.8, "budgetTokens": None, "reserveTokens": 0, "autoWrapUp": True,
           "handoffPath": ".work/HANDOFF.md"}
    if auto:
        cfg["autoClear"] = auto
    return cfg


def _repo(tmp_path, budget=None, **auto):
    cfg = _context_cfg(**auto)
    cfg["budgetTokens"] = budget
    return crew_fixtures.make_repo(tmp_path, config={"context": cfg}, git=False)


def _usage(model, total):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "model": model, "usage": {
        "input_tokens": total // 10, "cache_read_input_tokens": total - total // 10 - 1000,
        "cache_creation_input_tokens": 1000, "output_tokens": 5}}})


def _transcript(root, used, model="claude-opus-5", boundary_after=False, name="t.jsonl"):
    lines = ['{"type":"user","message":{"role":"user","content":"hi"}}', _usage(model, used)]
    if boundary_after:
        lines.append('{"type":"system","subtype":"compact_boundary","content":"Conversation compacted"}')
    path = root / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _stop(root, transcript, session=SESSION_A, active=False):
    return {"session_id": session, "transcript_path": str(transcript), "cwd": str(root),
            "hook_event_name": "Stop", "stop_hook_active": active}


def _marker_path(root, session):
    return root / ".crew" / (crew_autocycle.MARKER_PREFIX + crew_autocycle.session_key(session))


def _write_marker(root, session=SESSION_A, **fields):
    data = {"session_id": session, "requested_at": time.time() - 30, "trusted": True, "why": "measured"}
    data.update(fields)
    _marker_path(root, session).write_text(json.dumps(data), encoding="utf-8")


def _write_handoff(root, text=GOOD_HANDOFF, offset=5):
    (root / ".work").mkdir(exist_ok=True)
    path = root / ".work" / "HANDOFF.md"
    path.write_text(text, encoding="utf-8")
    stamp = time.time() + offset
    os.utime(path, (stamp, stamp))


def _windows(tmp_path, windows):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(windows), encoding="utf-8")
    return {"CREW_AUTOCLEAR_WINDOW_STUB": str(path)}


def _sendable(flavor, tmp_path, root):
    """A target each flavour can identify uniquely: a tmux pane whose pid is
    this test process (an ancestor of the script) for bash, and one stubbed
    window owned by this test process for PowerShell."""
    if flavor == "sh":
        bindir = tmp_path / "fakebin"
        bindir.mkdir(exist_ok=True)
        tmux = bindir / "tmux"
        tmux.write_text(f"#!/bin/sh\necho {os.getpid()}\n", encoding="ascii", newline="\n")
        tmux.chmod(0o755)
        _machine(root, method="tmux")
        return {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "TMUX": "/tmp/fake,1,0",
                "TMUX_PANE": "%7"}
    _machine(root)
    return _windows(tmp_path, [{"id": 4242, "pid": os.getpid(), "title": "Claude Code"}])


def _xdotool_env(tmp_path, windows):
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    fake = bindir / "xdotool"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
    fake.chmod(0o755)
    env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "DISPLAY": ":0"}
    env.update(_windows(tmp_path, windows))
    return env


def _log(root):
    path = root / ".crew" / ".autoclear.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_flavors_are_discoverable():
    assert FLAVORS, "neither bash nor pwsh is available - nothing here ran"


# --- wrap-up: once per crossing, stop_hook_active, session keys -------------

@by_flavor
def test_wrap_up_blocks_once_per_crossing(flavor, tmp_path):
    root = _repo(tmp_path)
    transcript = _transcript(root, 950_000)

    runs = [_invoke(flavor, "context-watch", root, _stop(root, transcript)) for _ in range(3)]

    assert [r.returncode for r in runs] == [2, 0, 0], runs[0].stderr
    assert runs[1].stderr.strip() == runs[2].stderr.strip() == ""
    marker = json.loads(_marker_path(root, SESSION_A).read_text(encoding="utf-8"))
    assert (marker["session_id"], marker["trusted"], marker["why"]) == (SESSION_A, True, "measured")


@by_flavor
def test_stop_hook_active_never_blocks_and_claims_nothing(flavor, tmp_path):
    root = _repo(tmp_path)
    transcript = _transcript(root, 950_000)

    result = _invoke(flavor, "context-watch", root, _stop(root, transcript, active=True))

    assert (result.returncode, result.stderr.strip()) == (0, "")
    assert not _marker_path(root, SESSION_A).exists()


@by_flavor_matrix
def test_the_forced_continuation_hands_over_to_auto_clear(flavor, tmp_path):
    """Root cause of "worked when it worked": the continuation the wrap-up
    forces is the turn the handoff gets written, and the hook used to exit on
    stop_hook_active before auto-clear could look -- so the clear waited for
    the user's NEXT turn."""
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _write_marker(root)
    _write_handoff(root)
    transcript = _transcript(root, 950_000)

    result = _invoke(flavor, "context-watch", root, _stop(root, transcript, active=True), env_extra=env)

    assert result.returncode == 0
    assert "would have sent" in _log(root), _log(root) + result.stderr


@by_flavor_matrix
def test_a_measured_drop_under_the_threshold_rearms_the_next_crossing(flavor, tmp_path):
    root = _repo(tmp_path)
    _write_marker(root)
    low = _transcript(root, 100_000, name="low.jsonl")
    high = _transcript(root, 950_000, name="high.jsonl")

    rearm = _invoke(flavor, "context-watch", root, _stop(root, low))
    again = _invoke(flavor, "context-watch", root, _stop(root, high))

    assert rearm.returncode == 0
    assert again.returncode == 2, again.stderr


@by_flavor_matrix
def test_an_estimate_under_the_threshold_does_not_rearm(flavor, tmp_path):
    root = _repo(tmp_path, budget=100)
    _write_marker(root)
    blob = root / "blob.jsonl"
    blob.write_bytes(b"x" * 100)

    _invoke(flavor, "context-watch", root, _stop(root, blob))

    assert _marker_path(root, SESSION_A).exists()


@by_flavor_matrix
def test_two_sessions_in_one_repo_each_get_their_own_wrap_up(flavor, tmp_path):
    root = _repo(tmp_path)
    transcript = _transcript(root, 950_000)

    first = _invoke(flavor, "context-watch", root, _stop(root, transcript, session=SESSION_A))
    other = _invoke(flavor, "context-watch", root, _stop(root, transcript, session=SESSION_B))

    assert (first.returncode, other.returncode) == (2, 2), other.stderr
    assert _marker_path(root, SESSION_A).exists() and _marker_path(root, SESSION_B).exists()


@by_flavor_matrix
def test_the_session_key_is_the_same_in_every_flavour(flavor, tmp_path):
    odd = "ab/c d:e..é-9_z"
    root = _repo(tmp_path)
    transcript = _transcript(root, 950_000)

    _invoke(flavor, "context-watch", root, _stop(root, transcript, session=odd))

    assert [p.name for p in (root / ".crew").glob(".handoff-requested-*")] == [
        ".handoff-requested-" + crew_autocycle.session_key(odd)]


@by_flavor_matrix
def test_one_sessions_start_does_not_rearm_another(flavor, tmp_path):
    root = _repo(tmp_path)
    for session in (SESSION_A, SESSION_B):
        _write_marker(root, session)
        (root / ".crew" / (".autoclear-sent-" + session)).write_text("", encoding="utf-8")

    _invoke(flavor, "handoff-read", root,
            {"session_id": SESSION_B, "source": "startup", "cwd": str(root), "hook_event_name": "SessionStart"})

    assert _marker_path(root, SESSION_A).exists()
    assert (root / ".crew" / (".autoclear-sent-" + SESSION_A)).exists()
    assert not _marker_path(root, SESSION_B).exists()
    assert not (root / ".crew" / (".autoclear-sent-" + SESSION_B)).exists()


# --- what the marker says about the reading ---------------------------------

@by_flavor_matrix
@pytest.mark.parametrize("case,why", [
    ("measured", "measured"),
    ("estimated", "estimated-from-transcript-size"),
    ("unknown-model", "unknown-window"),
    ("stale", "stale-reading-before-compaction"),
])
def test_the_marker_records_whether_the_reading_can_be_trusted(flavor, case, why, tmp_path):
    root = _repo(tmp_path, budget=100 if case == "estimated" else None)
    if case == "estimated":
        transcript = root / "blob.jsonl"
        transcript.write_bytes(b"x" * 500)
    elif case == "unknown-model":
        transcript = _transcript(root, 190_000, model="some-unlisted-model")
    else:
        transcript = _transcript(root, 950_000, boundary_after=case == "stale")

    result = _invoke(flavor, "context-watch", root, _stop(root, transcript))

    assert result.returncode == 2, result.stderr
    marker = json.loads(_marker_path(root, SESSION_A).read_text(encoding="utf-8"))
    assert (marker["why"], marker["trusted"]) == (why, why == "measured")


# --- auto-clear: verified handoff, trustworthy reading, machine opt-in ------

@by_flavor
def test_a_verified_handoff_behind_a_trusted_reading_is_sent(flavor, tmp_path):
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert "would send" in result.stdout, result.stderr


@by_flavor_matrix
@pytest.mark.parametrize("case,expect", [
    ("no-handoff", "has not been written"),
    ("older-handoff", "predates"),
    ("stub-handoff", "minHandoffLines"),
    ("skeleton", "skeleton"),
    ("untrusted", "not trustworthy"),
    ("zero-byte-marker", "empty or not JSON"),
    ("other-session", "different session"),
    ("no-session", "no session id"),
    ("no-marker", "no wrap-up was requested"),
])
def test_no_clear_without_a_verified_handoff_and_a_trusted_reading(flavor, case, expect, tmp_path):
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _write_marker(root, trusted=case != "untrusted", why="estimated-from-transcript-size")
    if case == "zero-byte-marker":
        _marker_path(root, SESSION_A).write_text("", encoding="utf-8")
    if case == "other-session":
        _write_marker(root, session_id=SESSION_B)
    if case == "no-marker":
        _marker_path(root, SESSION_A).unlink()
    texts = {"stub-handoff": "# Handoff\nTODO\n",
             "skeleton": GOOD_HANDOFF + "UNKNOWN - this skeleton was written automatically at compaction.\n"}
    if case != "no-handoff":
        _write_handoff(root, texts.get(case, GOOD_HANDOFF), offset=-600 if case == "older-handoff" else 5)
    session = "" if case == "no-session" else SESSION_A

    result = _invoke(flavor, "auto-clear", root, args=("--session", session, "--dry-run"), env_extra=env)

    assert "would send" not in result.stdout
    assert expect in result.stderr, result.stderr
    assert not (root / ".crew" / (".autoclear-sent-" + SESSION_A)).exists()


@by_flavor_matrix
@pytest.mark.parametrize("machine,repo", [(None, True), (True, False), ("true", None), (False, True)])
def test_only_the_machine_can_opt_in_and_a_repo_can_only_opt_out(flavor, machine, repo, tmp_path):
    root = _repo(tmp_path, **({} if repo is None else {"enabled": repo}))
    env = _sendable(flavor, tmp_path, root)
    _machine(root, enabled=machine, **({"method": "tmux"} if flavor == "sh" else {}))
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert (result.stdout.strip(), _log(root)) == ("", "")


# --- window targeting ---------------------------------------------------------

_ME = os.getpid()
_WINDOW_CASES = [
    ("owner-one", [{"id": 1, "pid": _ME, "title": "zsh"}], "", "owner pid]"),
    ("owner-two", [{"id": 1, "pid": _ME, "title": "a"}, {"id": 2, "pid": _ME, "title": "b"}], "", "2 windows"),
    ("owner-two-title", [{"id": 1, "pid": _ME, "title": "Claude x"}, {"id": 2, "pid": _ME, "title": "b"}],
     "claude", "owner pid + title]"),
    ("owner-wrong-title", [{"id": 1, "pid": _ME, "title": "vim"}], "Claude", "no window whose title"),
    ("title-none", [{"id": 1, "pid": 999999, "title": "vim"}], "Claude", "0 windows have a title"),
    ("title-two", [{"id": 1, "pid": 999998, "title": "Claude a"}, {"id": 2, "pid": 999999, "title": "Claude b"}],
     "Claude", "2 windows have a title"),
    ("title-one", [{"id": 1, "pid": 999999, "title": "Claude a"}, {"id": 2, "pid": 999998, "title": "vim"}],
     "Claude", "title fallback]"),
    ("nothing", [{"id": 1, "pid": 999999, "title": "Claude a"}], "", "no window belongs to any ancestor"),
]


@by_flavor_matrix
@pytest.mark.parametrize("case,windows,title,expect", _WINDOW_CASES, ids=[c[0] for c in _WINDOW_CASES])
def test_the_window_is_identified_uniquely_or_not_at_all(flavor, case, windows, title, expect, tmp_path):
    del case
    root = _repo(tmp_path)
    if flavor == "sh":
        env = _xdotool_env(tmp_path, windows)
        _machine(root, method="xdotool", windowTitle=title or None)
    else:
        env = _windows(tmp_path, windows)
        _machine(root, windowTitle=title or None)
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    sent = expect.endswith("]")
    assert ("would send" in result.stdout) is sent, result.stdout + result.stderr
    assert expect in (result.stdout if sent else result.stderr)


@pytest.mark.parametrize("case,windows,title,expect", _WINDOW_CASES, ids=[c[0] for c in _WINDOW_CASES])
def test_resolve_target_table(case, windows, title, expect):
    del case
    found = crew_autocycle.resolve_target(crew_autocycle.ancestors(), windows, title)

    assert found["ok"] is expect.endswith("]")
    assert expect.rstrip("]") in (found.get("how", "") if found["ok"] else found["reason"])


@pytest.mark.skipif(_BASH is None, reason="needs bash")
# A fixed id for this process's pid: under pytest-xdist each worker has its
# own pid, and ids that differ between workers abort the whole run.
@pytest.mark.parametrize("pane_pid,sent", [pytest.param(os.getpid(), True, id="own-pid-True"),
                                           pytest.param(999999, False, id="999999-False")])
def test_a_tmux_pane_must_be_the_one_running_this_session(pane_pid, sent, tmp_path):
    root = _repo(tmp_path)
    env = _sendable("sh", tmp_path, root)
    (tmp_path / "fakebin" / "tmux").write_text(f"#!/bin/sh\necho {pane_pid}\n", encoding="ascii", newline="\n")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke("sh", "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert ("would send" in result.stdout) is sent, result.stderr
    assert sent or "could not be confirmed" in result.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_wtype_is_refused_even_with_unsafe_focus(tmp_path):
    root = _repo(tmp_path, unsafeFocus=True)
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "wtype").write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
    (bindir / "wtype").chmod(0o755)
    _machine(root, method="wtype")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke("sh", "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra={"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "WAYLAND_DISPLAY": "w-0"})

    assert "would send" not in result.stdout
    assert "cannot identify a window" in result.stderr


# --- the whole cycle: wrap-up -> handoff -> clear -> resume ----------------

@by_flavor
def test_write_clear_resume_carries_the_next_action_end_to_end(flavor, tmp_path):
    """The handoff's next action is its LAST section, after a body longer than
    the whole resume budget -- the shape a truncating resume used to lose."""
    root = context_fixtures.make_repo(tmp_path, config={"context": _context_cfg()})
    env = _sendable(flavor, tmp_path, root)
    transcript = _transcript(root, 950_000)

    wrap = _invoke(flavor, "context-watch", root, _stop(root, transcript), env_extra=env)
    _write_handoff(root, "# Handoff\nticket: T-1\n\n## In flight\n" + "- detail line\n" * 400
                   + "\n## Next action\nRun the NEXT-ACTION-TOKEN migration.\n")
    _invoke(flavor, "context-watch", root, _stop(root, transcript, active=True), env_extra=env)
    start = {"session_id": SESSION_B, "source": "clear", "cwd": str(root), "hook_event_name": "SessionStart",
             "transcript_path": str(root / "fresh.jsonl")}
    _invoke(flavor, "handoff-read", root, start, env_extra=env)
    resumed = _invoke(flavor, "crew-context", root, start, env_extra=env)

    assert wrap.returncode == 2, wrap.stderr
    assert "would have sent" in _log(root), _log(root)
    injected = json.loads(resumed.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "NEXT-ACTION-TOKEN" in injected
    assert len(injected) <= 3000
    assert "initialUserMessage" not in resumed.stdout


def test_every_autocycle_sabotage_anchor_is_present_exactly_once():
    """The cheap standing check sabotage.py's harness gives its own table: an
    edit that moves a line a mutation aims at would otherwise leave that
    mutation testing nothing until somebody paid for a full run."""
    import sabotage_autocycle  # pylint: disable=import-outside-toplevel

    lost = []
    for label, target, find, _replace, _test in sabotage_autocycle.AUTOCYCLE_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            if handle.read().count(find) != 1:
                lost.append(label)

    assert not lost, lost
