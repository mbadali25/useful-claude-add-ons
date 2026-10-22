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

The rules run through the bash wrappers wherever bash exists. Every run sets
CREW_AUTOCLEAR_INHIBIT and points HOME at the fixture: no case can read the
developer's real opt-in, enumerate a real window, or send a keystroke.
"""
import json
import os
import pathlib
import shutil
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import context_fixtures
import crew_autocycle
import crew_fixtures

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
FLAVORS = [f for f, have in (("sh", _BASH),) if have]
# There is no python driver here: the rules live in the bash wrappers. Four
# tests (`by_flavor`) are the sample run by default -- a wrap-up block, a
# stop_hook_active stand-down, a clear sent, and the resume end to end. Every
# other test (`by_flavor_matrix`) is `slow`: `pytest -m slow` or `--run-slow`
# (conftest.py).
by_flavor = pytest.mark.parametrize("flavor", FLAVORS)
by_flavor_matrix = pytest.mark.parametrize(
    "flavor", [pytest.param(f, marks=crew_fixtures.SLOW) for f in FLAVORS])

SESSION_A = "11111111-aaaa-4aaa-8aaa-000000000001"
SESSION_B = "22222222-bbbb-4bbb-8bbb-000000000002"
GOOD_HANDOFF = (
    "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
    "## Done\n- a thing\n\n## Next action\nRun the NEXT-ACTION-TOKEN migration.\n")


# --- plumbing --------------------------------------------------------------

def _script(flavor, name):
    path = os.path.join(_SCRIPTS, f"{name}.{flavor}")
    return path.replace("\\", "/")


def _invoke(flavor, name, root, payload=None, args=(), env_extra=None):
    home = str(root.parent / "home")
    env = dict(os.environ, HOME=home, USERPROFILE=home, CREW_AUTOCLEAR_INHIBIT="1",
               CLAUDE_PROJECT_DIR=str(root),
               CREW_VAULT_OPS=str(root.parent / "absent-vault-ops.py"),
               CREW_OBSIDIAN_CONFIG=str(root.parent / "absent-obsidian.json"))
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
    cfg = {"warnAt": 0.8, "reserveTokens": 0}
    if auto:
        cfg["autoClear"] = auto
    return cfg


def _repo(tmp_path, **auto):
    cfg = _context_cfg(**auto)
    return crew_fixtures.make_repo(tmp_path, config={"context": cfg}, git=False)


def _repo_no_config(tmp_path):
    """`.crew/` present (so `make_repo` still creates it) but NO
    `.crew/config.json` -- state (2) of `test_auto_clear.py`'s six-state
    matrix. Proves `context-watch`'s OWN handover to auto-clear (the
    forced-continuation branch) reaches it on `.crew/` alone, matching
    auto-clear's own directory gate -- crew 1.0 F4's reachability fix
    (CONFIG.md sec 14)."""
    return crew_fixtures.make_repo(tmp_path, config=None, git=False)


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


# Native Windows has no tmux, and neither the tmux pane check nor the xdotool
# owner-pid match can confirm a target there (`crew_autocycle._ppid` has no
# Windows parent-pid walk, so both fail closed). A test that needs a sendable
# target skips on nt.
_NO_NATIVE_TMUX = ("no native tmux; the pane check has no Windows parent-pid walk "
                   "and fails closed (T-0076)")


def _send_method(flavor):
    """The machine-file keys naming the method `_sendable`'s target uses."""
    del flavor
    return {"method": "tmux"}


def _tmux_env(tmp_path, pane_pid=None):
    """A fake tmux whose one pane reports `pane_pid` (default: the bound
    session's terminal, `crew_fixtures.TERMINAL_PID` -- an ancestor of the
    session's own process in `crew_fixtures.bind_session`'s process table)."""
    pane_pid = crew_fixtures.TERMINAL_PID if pane_pid is None else pane_pid
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {pane_pid}\n",
                             f"@echo off\r\necho {pane_pid}\r\n")
    return crew_fixtures.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7")


def _bound(root, session=SESSION_A):
    """T-0016: `session` bound to its own Claude Code process, which runs in
    its own terminal (`crew_fixtures.bind_session`)."""
    return crew_fixtures.bind_session(root.parent / "home", session)


def _sendable(flavor, tmp_path, root, session=SESSION_A):
    """A target the wrapper can identify uniquely, for a session bound to
    its own process (T-0016): a tmux pane whose pid is that session's
    terminal. Skipped on native Windows (`_NO_NATIVE_TMUX`)."""
    if os.name == "nt":
        pytest.skip(_NO_NATIVE_TMUX)
    _machine(root, **_send_method(flavor))
    env = _bound(root, session)
    env.update(_tmux_env(tmp_path))
    return env


def _xdotool_env(tmp_path, windows):
    """A fake `xdotool` the bash flavour AND the python it starts can find:
    on Windows that is an extensionless shim for bash plus `xdotool.cmd`,
    because a native `shutil.which` never matches an extensionless file."""
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "xdotool")
    env = crew_fixtures.shim_env("sh", bindir, DISPLAY=":0")
    env.update(_windows(tmp_path, windows))
    return env


def _log(root):
    path = root / ".crew" / ".autoclear.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_flavors_are_discoverable():
    assert FLAVORS, "bash is not available - nothing here ran"


def test_log_autoclear_survives_a_lone_surrogate_in_the_message(tmp_path):
    """`log_autoclear` is documented as best-effort - a write failure here
    must never abort the caller's planning. `json.loads` will happily decode
    a `\\ud800` escape from an unknown key into a lone UTF-16 surrogate with
    no complaint, and a STRICT `handle.write()` under `encoding="utf-8"` then
    raises `UnicodeEncodeError` - a `ValueError`, not an `OSError`, so a
    narrower `except OSError:` does not catch it and the "best-effort" call
    aborts whatever planning step invoked it. Sabotaged by hand: reverting
    the open() call to plain `encoding="utf-8"` (no `errors=`) reproduces
    this directly - confirmed red before the fix, green after."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)

    surrogate = "unknown key: \ud800 (lone surrogate)"
    crew_autocycle.log_autoclear(str(root), surrogate)  # must not raise

    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "unknown key:" in log and "lone surrogate" in log, log


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


@pytest.mark.skipif(_BASH is None, reason="needs bash")
@pytest.mark.wallclock
def test_context_watch_stdout_reaches_eof_promptly_even_with_a_long_delay(tmp_path):
    """FIX (Codex): auto-clear.sh's detached tmux/xdotool sender used to
    inherit fd 3 -- the real hook stdout `cw_run_auto_clear` dup's onto it
    before handing over -- so the sender held that pipe open for the whole
    `sleep $DELAY`, and whoever reads the hook's stdout (Claude Code; here,
    this test's own subprocess pipe) never saw EOF until the sender woke up
    and exited. delaySeconds=30 against a 5s read deadline proves the fix
    without the test itself waiting out the delay: the OLD code would still
    be sleeping, well past the deadline.

    Deliberately NOT `_invoke` (which always sets CREW_AUTOCLEAR_INHIBIT):
    inhibit skips the spawn entirely and would prove nothing here. The fake
    `tmux` is genuinely invoked by the real (harmless) detached sender.

    `crew_fixtures.run_gate`, not a bare `subprocess.run`, for the SAME
    reason every other real spawn in this suite goes through it: the direct
    child here (context-watch.sh) returns in well under the 5s deadline
    this test proves, but auto-clear.sh's own sender deliberately outlives
    it -- `setsid ... & disown` (auto-clear.sh's own comment on why: so a
    slow /clear does not get cut off by the hook's own death in real use).
    A bare `subprocess.run` leaves that sender running for the rest of its
    `delaySeconds` with nothing tracking it; measured directly (a
    throwaway repro of this exact scenario) it is still alive 12+ seconds
    after this call returns and self-exits only once its 30s is up.
    `run_gate` registers with the autouse `gate_processes` fixture
    (conftest.py), whose teardown calls `kill_process_group` on every
    process it tracked -- reaching the detached sender via the Windows Job
    Object `popen_gate` now assigns at spawn (crew_fixtures.py), which
    Windows keeps every process the leader creates inside REGARDLESS of
    the POSIX session `setsid` starts (job membership and POSIX sessions
    are unrelated concepts); confirmed directly, same repro, 0 survivors
    after `kill_process_group`. On POSIX this is NOT closed the same way:
    `setsid` deliberately moves the sender into a NEW process group, so
    `killpg` on the leader's own recorded pgid cannot reach it either --
    see TODO.md.

    The deadline (5s) is under the sender's 30s delay, so a sender holding
    the pipe open still fails it."""
    if os.name == "nt":
        pytest.skip(_NO_NATIVE_TMUX)
    method = _send_method("sh")
    root = _repo(tmp_path, delaySeconds=30, **method)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {crew_fixtures.TERMINAL_PID}\n")
    send_env = {"PATH": crew_fixtures.shell_path("sh", [bindir]),
                "TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%7"}
    send_env.update(_bound(root))
    home = tmp_path / "home"  # `_machine` writes to root.parent/"home" == tmp_path/"home"
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               CLAUDE_PROJECT_DIR=str(root), **send_env,
               # T-0016 review round 1: the stubs are read only under the
               # inhibit; "spawn" still spawns the sender, which stops before
               # any keystroke (auto-clear.sh).
               CREW_AUTOCLEAR_INHIBIT="spawn")
    payload = _stop(root, root / ".work" / "irrelevant.jsonl", active=True)
    deadline = 5

    started = time.time()
    result = crew_fixtures.run_gate(
        [_BASH, _script("sh", "context-watch")], cwd=str(root), env=env,
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=deadline, check=False)
    elapsed = time.time() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < deadline, elapsed
    assert f"sent - method {method['method']}" in _log(root), _log(root) + result.stderr


@by_flavor
def test_the_forced_continuation_reaches_auto_clear_with_no_repo_config_json(flavor, tmp_path):
    """crew 1.0 F4 reachability fix. Before it, `context-watch.sh:81` /
    `context-watch.sh` stood the whole hook down on a missing
    `.crew/config.json`, so a `.crew/` directory the machine had still opted
    in for (a fresh checkout, or one that ran `/crew:init` for something
    other than auto-clear) never reached the forced-continuation handover
    below -- even though auto-clear.sh's OWN gate now arms on `.crew/`
    alone (test_auto_clear.py's state (2)). This is the caller-level proof
    that the handover actually runs end to end through context-watch, not
    only when auto-clear is invoked directly."""
    root = _repo_no_config(tmp_path)
    assert not (root / ".crew" / "config.json").exists()
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
    root = _repo(tmp_path)
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
    root = _repo(tmp_path)
    if case == "estimated":
        transcript = root / "blob.jsonl"
        transcript.write_bytes(b"x" * 1_000_000)
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


# --- silent-default guard: an unusable config value is logged, not just defaulted ---

@by_flavor_matrix
def test_an_unrecognised_autoclear_key_is_logged_and_the_default_still_applies(flavor, tmp_path):
    """`delay` (not `delaySeconds`) is exactly the shape a hand-edit typo
    takes: nothing in `settings()`/`Get-CrewAutoClearValue` ever reads it, so
    it silently does nothing and `delaySeconds` falls through to the
    compiled default -- indistinguishable, on disk, from an operator who
    genuinely wanted 3s. The warning is the only thing that tells the two
    apart."""
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **_send_method(flavor), delay=4)
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert "delay: 3s" in result.stdout, result.stdout + result.stderr
    log = _log(root)
    assert "delay" in log and "not a recognised key" in log, log


@by_flavor_matrix
def test_a_numeric_string_delay_is_accepted_silently(flavor, tmp_path):
    """The other half of the same guard: `delaySeconds` as a numeric STRING
    (a plausible hand-edit, quoting a number that did not need it) is
    already accepted and used -- not a misconfiguration, so it must not log
    a warning either."""
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **_send_method(flavor), delaySeconds="4")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert "delay: 4s" in result.stdout, result.stdout + result.stderr
    assert "not a usable number" not in _log(root), _log(root)


@by_flavor_matrix
def test_an_unusable_delay_seconds_is_logged_and_the_default_still_applies(flavor, tmp_path):
    """A `delaySeconds` that is SET but not a usable number at all (unlike
    the numeric-string case above) must warn, naming the effective value."""
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **_send_method(flavor), delaySeconds="soon")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert "delay: 3s" in result.stdout, result.stdout + result.stderr
    log = _log(root)
    assert "delaySeconds" in log and "not a usable number" in log, log


@by_flavor_matrix
def test_an_empty_delay_seconds_array_is_logged_and_the_default_still_applies(flavor, tmp_path):
    root = _repo(tmp_path)
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **_send_method(flavor), delaySeconds=[])
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert "delay: 3s" in result.stdout, result.stdout + result.stderr
    log = _log(root)
    assert "delaySeconds" in log and "not a usable number" in log, log


@by_flavor_matrix
@pytest.mark.parametrize("machine,repo", [(None, True), (True, False), ("true", None), (False, True)])
def test_only_the_machine_can_opt_in_and_a_repo_can_only_opt_out(flavor, machine, repo, tmp_path):
    root = _repo(tmp_path, **({} if repo is None else {"enabled": repo}))
    env = _sendable(flavor, tmp_path, root)
    _machine(root, enabled=machine, **_send_method(flavor))
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert (result.stdout.strip(), _log(root)) == ("", "")


# --- window targeting ---------------------------------------------------------

_ME = os.getpid()
_WINDOW_CASES = [
    ("owner-one", [{"id": 1, "pid": _ME, "title": "zsh"}], "owner pid]"),
    ("owner-two", [{"id": 1, "pid": _ME, "title": "a"}, {"id": 2, "pid": _ME, "title": "b"}], "2 windows"),
    ("nothing", [{"id": 1, "pid": 999999, "title": "Claude a"}], "no window belongs to any ancestor"),
]


@by_flavor_matrix
@pytest.mark.parametrize("case,windows,expect", _WINDOW_CASES, ids=[c[0] for c in _WINDOW_CASES])
def test_the_window_is_identified_uniquely_or_not_at_all(flavor, case, windows, expect, tmp_path):
    if os.name == "nt" and any(w["pid"] == _ME for w in windows):
        pytest.skip("owner-pid matching needs an ancestor walk the bash flavour has no Windows "
                    "branch for (_ppid, crew_autocycle.py); it fails closed there (T-0076)")
    del case
    root = _repo(tmp_path)
    # T-0016: the owner is the bound session's terminal, not this process.
    windows = [dict(w, pid=crew_fixtures.TERMINAL_PID) if w["pid"] == _ME else w for w in windows]
    env = dict(_bound(root), **_xdotool_env(tmp_path, windows))
    _machine(root, method="xdotool")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    sent = expect.endswith("]")
    assert ("would send" in result.stdout) is sent, result.stdout + result.stderr
    assert expect in (result.stdout if sent else result.stderr)


@pytest.mark.parametrize("case,windows,expect", _WINDOW_CASES, ids=[c[0] for c in _WINDOW_CASES])
def test_resolve_target_table(case, windows, expect):
    del case
    found = crew_autocycle.resolve_target(crew_autocycle.ancestors(), windows)

    assert found["ok"] is expect.endswith("]")
    assert expect.rstrip("]") in (found.get("how", "") if found["ok"] else found["reason"])


@pytest.mark.skipif(_BASH is None, reason="needs bash")
# A fixed id for this process's pid: under pytest-xdist each worker has its
# own pid, and ids that differ between workers abort the whole run.
# The refusal case still runs on native Windows: it proves the pane check
# fails closed there. Only the accepting case needs a parent-pid walk.
@pytest.mark.parametrize("pane_pid,sent", [
    pytest.param(crew_fixtures.TERMINAL_PID, True, id="own-pid-True",
                 marks=pytest.mark.skipif(os.name == "nt", reason=_NO_NATIVE_TMUX)),
    pytest.param(999999, False, id="999999-False")])
def test_a_tmux_pane_must_be_the_one_running_this_session(pane_pid, sent, tmp_path):
    """tmux's own mechanics, so never the xdotool fallback `_sendable` takes
    on native Windows: the fake tmux and method are set here directly."""
    root = _repo(tmp_path)
    _machine(root, method="tmux")
    env = dict(_bound(root), **_tmux_env(tmp_path, pane_pid))
    _write_marker(root)
    _write_handoff(root)

    result = _invoke("sh", "auto-clear", root, args=("--session", SESSION_A, "--dry-run"), env_extra=env)

    assert ("would send" in result.stdout) is sent, result.stderr
    assert sent or "could not be confirmed" in result.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_wtype_is_refused_even_with_unsafe_focus(tmp_path):
    root = _repo(tmp_path, unsafeFocus=True)
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "wtype")
    _machine(root, method="wtype")
    _write_marker(root)
    _write_handoff(root)

    result = _invoke("sh", "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=crew_fixtures.shim_env("sh", bindir, WAYLAND_DISPLAY="w-0"))

    assert "would send" not in result.stdout
    assert "cannot identify a window" in result.stderr


# --- OWNER DECISION: `auto` resolves to `notify` on native Windows, never to
# `auto` never resolves to a removed method ------------------------------

_NO_CAPABILITY_ENV = {"TMUX": "", "DISPLAY": "", "TMUX_PANE": ""}


@by_flavor
def test_auto_resolves_to_notify_on_native_windows_and_never_to_sendkeys(flavor, tmp_path):
    """Both senders: `auto` with no tmux pane and no X11 must choose `notify`,
    never the SendKeys-equivalent method, on native Windows. The bash flavour
    is told OS=Windows_NT here explicitly -- this is the one place a bash
    session can legitimately be "native Windows" (Git Bash), and the owner
    decision applies there too."""
    root = _repo(tmp_path)  # method left at the default, "auto"
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    env = dict(_NO_CAPABILITY_ENV, OS="Windows_NT")

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=env)

    assert "would send" in result.stdout, result.stdout + result.stderr
    assert "method: notify" in result.stdout, result.stdout
    assert "sendkeys" not in result.stdout


@by_flavor
def test_notify_dry_run_never_reports_a_delay_number(flavor, tmp_path):
    """`notify` types nothing, so `delaySeconds` buys it no wait -- printing
    the configured number (or a hardcoded `0`)
    would read as a real delay `notify` never takes. The plan prints
    `n/a` text instead; `_repo`'s configured delaySeconds (9, not
    the default 3) proves the printed text is not simply the default."""
    root = _repo(tmp_path, delaySeconds=9)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    env = dict(_NO_CAPABILITY_ENV, OS="Windows_NT")

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=env)

    assert "method: notify" in result.stdout, result.stdout
    assert "delay: n/a (notify sends no keystroke)" in result.stdout, result.stdout
    assert "delay: 9s" not in result.stdout
    assert "delay: 0s" not in result.stdout


@by_flavor
def test_notifys_dry_run_plan_has_no_target_line(flavor, tmp_path):
    """PARITY (item 3): `notify` identifies no window, so LABEL/target is
    always empty for it. `auto-clear.sh` used to print an empty `target:` line
    (`target: ` with nothing after it) regardless; it now omits the line
    entirely."""
    root = _repo(tmp_path)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    env = dict(_NO_CAPABILITY_ENV, OS="Windows_NT")

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=env)

    assert "method: notify" in result.stdout, result.stdout
    assert "target" not in result.stdout, result.stdout


# --- the configured delay, at several values, on the keystroke methods -----
#
# `notify` types nothing, so its own delay handling is covered above; a
# keystroke method (tmux/xdotool) has a real wait, and it is this value --
# not the schema default of 3 -- that must reach both the dry-run plan and
# the sent-log line. Several values, none of them 3, so a hard-coded
# fallback would fail every one of them, not merely the ones that happen to
# differ from the default.


@pytest.mark.parametrize("delay", [1, 4, 6, 9])
@by_flavor
def test_the_configured_delay_reaches_the_dry_run_plan_at_several_values(flavor, tmp_path, delay):
    root = _repo(tmp_path, delaySeconds=delay)
    env = _sendable(flavor, tmp_path, root)
    _write_marker(root)
    _write_handoff(root)

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=env)

    assert "would send" in result.stdout, result.stdout + result.stderr
    assert f"delay: {delay}s" in result.stdout, result.stdout
    assert "delay: 3s" not in result.stdout, result.stdout


@pytest.mark.skipif(_BASH is None, reason="needs bash")
@pytest.mark.skipif(os.name == "nt", reason=(
    "no native tmux (T-0076), and the xdotool sender cannot stand in: this test shims "
    "`bash` on PATH, but Git's bin\\bash.exe launcher prepends /mingw64/bin:/usr/bin, so "
    "the sender's `bash` always resolves to /usr/bin/bash and the shim is never reached"))
@pytest.mark.parametrize("delay", [1, 4, 6, 9])
def test_the_configured_delay_reaches_the_detached_senders_own_sleep_argument(tmp_path, delay):
    """The value handed to the DETACHED sender -- not merely echoed by the
    dry-run plan -- must be the configured delaySeconds. Captures the
    argument itself, never wall-clock elapsed time: a hard-coded `sleep 3`
    still finishes in well under a second regardless of what is configured,
    and a wall-clock assertion could not tell that apart from the real fix.

    A fake `sleep` on PATH would ALSO intercept `_common.sh`'s unrelated
    python-probe watchdog (`crew_py_strict`'s `sleep "$probe_timeout"`),
    which fires at least once per script in this chain and is capped at 3s
    regardless of `delaySeconds` -- confirmed by hand: a naive `sleep` shim
    here logs several extra "3"s that have nothing to do with this delay.
    So this shims `bash` instead, on the ONE call shape unique to the
    generated sender (`setsid/nohup bash "$send_script"`, the only `bash
    SCRIPT` invocation in this chain whose script is NOT named
    `auto-clear.sh` itself -- `context-watch.sh`'s own `bash
    ".../auto-clear.sh" ...` call is the other one, and must run for real or
    nothing downstream happens): reads its `sleep N` line and never actually
    launches it. Everything else execs straight through to the real bash
    unchanged."""
    root = _repo(tmp_path, method="tmux", delaySeconds=delay)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {crew_fixtures.TERMINAL_PID}\n")
    sleep_log = tmp_path / "sleep-calls.log"
    crew_fixtures.write_shim(bindir, "bash", (
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  */auto-clear.sh) exec \"$CREW_TEST_REAL_BASH\" \"$@\" ;;\n"
        "esac\n"
        f'grep "^sleep " "$1" | head -1 | cut -d" " -f2 >> "{sleep_log}"\n'
        "exit 0\n"))
    home = tmp_path / "home"  # `_machine` writes to root.parent/"home" == tmp_path/"home"
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               CLAUDE_PROJECT_DIR=str(root),
               PATH=crew_fixtures.shell_path("sh", [bindir]),
               CREW_TEST_REAL_BASH=_BASH, CREW_AUTOCLEAR_INHIBIT="spawn",
               TMUX="/tmp/fake,1,0", TMUX_PANE="%7", **_bound(root))
    payload = _stop(root, root / ".work" / "irrelevant.jsonl", active=True)

    result = subprocess.run([_BASH, _script("sh", "context-watch")], cwd=str(root), env=env,
                            input=json.dumps(payload), capture_output=True, text=True,
                            timeout=5, check=False)
    deadline = time.time() + 5
    # Wait for the shim's WRITE, not the file: `>>` creates it before `cut`
    # writes, and under a parallel run the read landed in that gap ('' == '1').
    while time.time() < deadline and not (
            sleep_log.exists() and sleep_log.read_text(encoding="utf-8").strip()):
        time.sleep(0.02)

    assert result.returncode == 0, result.stderr
    assert sleep_log.exists(), "the detached sender's bash was never invoked"
    assert sleep_log.read_text(encoding="utf-8").strip() == str(delay)


@by_flavor
def test_auto_does_not_resolve_to_notify_off_windows_with_no_capability(flavor, tmp_path):
    """The mirror case: off native Windows (no `OS=Windows_NT`), with no tmux
    and no X11, `auto` still refuses outright -- it must not paper over a
    genuinely headless Linux/macOS host by notifying instead."""
    root = _repo(tmp_path)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)

    # OS="" (read exactly as unset): on native Windows the wrapper would
    # otherwise inherit this process's OS=Windows_NT and correctly resolve
    # to `notify`, which is the OTHER test's case, not this one.
    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=dict(_NO_CAPABILITY_ENV, OS=""))

    assert "would send" not in result.stdout
    assert "no usable method" in result.stderr


@by_flavor
def test_notify_never_claims_the_session_was_cleared_or_compacted(flavor, tmp_path):
    """Wording: the notify path must say what it did (the handoff is
    written and verified, and it is safe to run the command yourself) and
    never claim success it cannot verify -- no "cleared" or "compacted"
    anywhere in what it prints or logs."""
    root = _repo(tmp_path)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    env = dict(_NO_CAPABILITY_ENV, OS="Windows_NT")

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A), env_extra=env)

    assert result.returncode == 0
    combined = (result.stdout + result.stderr + _log(root)).lower()
    assert "cleared" not in combined, combined
    assert "compacted" not in combined, combined
    assert "safe to run" in combined, combined
    payload = json.loads(result.stdout)
    assert payload == {"systemMessage": payload["systemMessage"]}, result.stdout
    assert (root / ".crew" / (".autoclear-sent-" + SESSION_A)).exists()


@by_flavor
def test_notify_is_not_suppressed_by_the_test_suites_own_inhibit_flag(flavor, tmp_path):
    """CREW_AUTOCLEAR_INHIBIT exists so a test suite never drives the real
    keyboard -- notify never touches a keyboard or a window at all, so it
    fires for real even with the flag set (every `_invoke` call sets it),
    and this is what proves that rather than assuming it."""
    root = _repo(tmp_path)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    env = dict(_NO_CAPABILITY_ENV, OS="Windows_NT")

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A), env_extra=env)

    assert "CREW_AUTOCLEAR_INHIBIT" not in result.stdout + _log(root)
    assert "sent - method notify" in _log(root), _log(root)


# --- narrowing: onlyRepos / onlySessions -------------------------------------
#
# `enabled: true` in the machine file arms every Claude session on the host.
# These two machine-only keys narrow it, and can only narrow it. Every case
# goes through the real wrapper of each flavour, so the parity is measured.
# An unarmed case must be SILENT -- no plan on stdout, no log line -- because
# a session the machine never armed must not learn the feature exists.

def _scoped(flavor, tmp_path, root, session=SESSION_A, **scope):
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **_send_method(flavor), **scope)
    _write_marker(root, session)
    _write_handoff(root)
    return _invoke(flavor, "auto-clear", root, args=("--session", session, "--dry-run"),
                   env_extra=env)


def _armed_or_silent(result, root):
    if "would send" in result.stdout:
        return "armed"
    assert (result.stdout.strip(), _log(root)) == ("", ""), result.stderr + _log(root)
    return "silent"


# A "silent" case never reaches method/window resolution -- in_scope refuses
# first -- so only the "armed" cases below depend on a REAL capability this
# host may not have, whatever `_sendable`'s fake tmux/window stands in for.
# Detect the capability directly rather than trusting the OS name: burn-in
# saw both `method tmux but tmux is not on PATH` and `no window whose title
# ...` on a real, opted-in Windows host, which is exactly what a host with
# neither capability produces even when the narrowing decision is correct.
# W8 removed this probe arguing `_sendable` injects a fake tmux/window
# unconditionally, so no case here could reach a real capability at all -- but
# `_sendable`'s FAKE window/pane only replaces the ENUMERATED window/pane
# list; the ANCESTOR-PID lookup used to decide whether the fake target is
# "owned" (`ancestors()`/`Get-CrewParentId`, real `/proc`, `ps`, `Get-Process`
# or WMI calls) is never faked, and WMI/process introspection can genuinely be
# unavailable on a real Windows host -- a locked-down CI runner with WMI
# disabled by policy is still Windows, so this cannot be an OS-name check
# either. Restored (owner ruling, journaled): the "silent" cases below still
# never skip -- only "armed" ones, which are the only ones this affects.


def _real_tmux_on_path():
    """The REAL PATH's tmux, never `_sendable`'s injected shim: if this host
    truly has no tmux, `resolve_method` refuses by design and no "armed"
    sh-flavour case can ever be proved here."""
    return shutil.which("tmux") is not None


_ROOT_TOKEN = "{root}"
_SCOPE_CASES = [
    ("absent", {}, "armed"),
    ("null", {"onlyRepos": None, "onlySessions": None}, "armed"),
    ("session-listed", {"onlySessions": [SESSION_A]}, "armed"),
    ("session-other", {"onlySessions": [SESSION_B]}, "silent"),
    ("session-case-differs", {"onlySessions": [SESSION_A.upper()]}, "silent"),
    ("sessions-empty", {"onlySessions": []}, "silent"),
    ("repo-listed", {"onlyRepos": [_ROOT_TOKEN]}, "armed"),
    ("repo-trailing-sep", {"onlyRepos": [_ROOT_TOKEN + "/"]}, "armed"),
    # Review round 2 (crew-1.0-r3-autocycle): whitespace is a legal POSIX
    # filename character, so an onlyRepos entry with a trailing space must
    # NOT authorise the space-free repo -- an unlisted repo must never be
    # in scope. crew_autocycle.normalise_repo_path stopped stripping it
    # (see test_a_trailing_space_in_an_only_repos_entry_does_not_authorise_
    # the_bare_path for the direct unit test); this case proves it end to end
    # through the real wrapper.
    ("repo-trailing-space", {"onlyRepos": [_ROOT_TOKEN + " "]}, "silent"),
    # A backslash is a legal POSIX filename character, not a separator on
    # bash's flavour (crew_autocycle.normalise_repo_path, fixed in review
    # round 1 of crew-1.0-burnin-fix4 -- see test_in_scope_does_not_collapse_
    # backslash_and_slash_on_posix for the direct unit test).
    ("repo-backslashes", {"onlyRepos": ["{root\\}"]}, "silent"),
    ("repo-other", {"onlyRepos": ["{root}-other"]}, "silent"),
    ("repo-parent", {"onlyRepos": ["{parent}"]}, "silent"),
    ("repos-empty", {"onlyRepos": []}, "silent"),
    ("repo-relative-dot", {"onlyRepos": ["."]}, "silent"),
    ("repos-not-a-list", {"onlyRepos": _ROOT_TOKEN}, "silent"),
    ("both-match", {"onlyRepos": [_ROOT_TOKEN], "onlySessions": [SESSION_A]}, "armed"),
    ("both-session-misses", {"onlyRepos": [_ROOT_TOKEN], "onlySessions": [SESSION_B]}, "silent"),
    ("both-repo-misses", {"onlyRepos": ["{root}-other"], "onlySessions": [SESSION_A]}, "silent"),
]
# The "sh" expectation above is POSIX's; these two cases differ under the
# Win32 rules the sh flavour's native python applies on Windows.
_SH_WIN32_PATH_RULES = {"repo-trailing-space", "repo-backslashes"}


def _posix_shaped(tmp_path, name):
    """A path the `windows=False` rules accept on every host. POSIX: a real
    directory under `tmp_path`, exactly as before. Native Windows: a
    lexical `/`-rooted path, since `tmp_path` is `C:\\...` there, which the
    POSIX rules refuse as relative -- and `normalise_repo_path` runs no
    realpath when the rules it applies are not this host's, so nothing
    needs to exist."""
    if os.name == "nt":
        return pathlib.PurePosixPath("/tmp/crew-autocycle-scope") / name
    path = tmp_path / name
    path.mkdir()
    return path


def _fill(value, root):
    if isinstance(value, list):
        return [_fill(v, root) for v in value]
    if not isinstance(value, str):
        return value
    return (value.replace("{root\\}", str(root).replace("/", "\\"))
            .replace("{parent}", str(root.parent)).replace(_ROOT_TOKEN, str(root)))


@by_flavor
@pytest.mark.parametrize("case,scope,expect", _SCOPE_CASES, ids=[c[0] for c in _SCOPE_CASES])
def test_the_machine_can_narrow_auto_clear_to_listed_repos_and_sessions(
        flavor, case, scope, expect, tmp_path, request):
    if flavor == "sh" and case in _SH_WIN32_PATH_RULES:
        request.applymarker(pytest.mark.xfail(os.name == "nt", strict=True, reason=(
            "on native Windows the sh flavour's python applies Win32 path rules "
            "(normalise_repo_path windows=os.name == 'nt'), so this entry arms where "
            "POSIX refuses it -- a POSIX/Win32 divergence the owner has not ruled "
            "on (T-0076 spec, Unknowns); the hook is deliberately unchanged")))
    del case
    if expect == "armed":
        # Only an "armed" case reaches method/window resolution -- in_scope
        # refuses every "silent" one first -- so only these depend on a
        # capability this host may genuinely lack.
        if flavor == "sh" and not _real_tmux_on_path():
            pytest.skip("tmux is not on PATH on this host, so this case can "
                        "only be PROVED armed by actually resolving a method "
                        "- see test_in_scope_decides_the_scope_matrix_with_"
                        "no_subprocess_on_every_os for the narrowing decision "
                        "itself, which does not need tmux")
    root = _repo(tmp_path)

    result = _scoped(flavor, tmp_path, root, **{k: _fill(v, root) for k, v in scope.items()})

    assert _armed_or_silent(result, root) == expect


@pytest.mark.parametrize("case,scope,expect", _SCOPE_CASES, ids=[c[0] for c in _SCOPE_CASES])
def test_in_scope_decides_the_scope_matrix_with_no_subprocess_on_every_os(
        case, scope, expect, tmp_path):
    """The exact `_SCOPE_CASES` table the wrapper test above drives through a
    real bash, proved here straight against `crew_autocycle.in_scope` --
    no subprocess, no tmux, no window system, so this runs identically on a
    host that has neither and would otherwise skip every "armed" case above.
    POSIX only (`windows=False`): the "sh" expectation applies, since that is
    the branch a real POSIX `tmp_path` exercises; the Windows branch already
    has its own dedicated in-process cases (`test_in_scope_on_windows_is_
    case_insensitive_for_repos_only` and neighbours). On native Windows the
    root is POSIX-shaped (`_posix_shaped`), so the same rules see the same
    shape of path."""
    del case
    root = _posix_shaped(tmp_path, "repo")
    cfg = {key: _fill(value, root) for key, value in scope.items()}

    result = crew_autocycle.in_scope(cfg, str(root), SESSION_A, windows=False)

    assert result == (expect == "armed")


@by_flavor
def test_a_symlink_to_the_repo_in_only_repos_arms_it(flavor, tmp_path):
    root = _repo(tmp_path)
    link = tmp_path / "link-to-repo"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    result = _scoped(flavor, tmp_path, root, onlyRepos=[str(link)])

    assert _armed_or_silent(result, root) == "armed"


@by_flavor
@pytest.mark.parametrize("key", ["onlyRepos", "onlySessions"])
def test_a_repo_config_cannot_widen_the_machines_narrowing(flavor, key, tmp_path):
    """One key at a time, so neither can hide a widening of the other."""
    mine = {"onlyRepos": [str(tmp_path / "repo")], "onlySessions": [SESSION_A]}
    theirs = {"onlyRepos": [str(tmp_path / "elsewhere")], "onlySessions": [SESSION_B]}
    root = _repo(tmp_path, **{key: mine[key]})

    result = _scoped(flavor, tmp_path, root, **{key: theirs[key]})

    assert _armed_or_silent(result, root) == "silent"


@by_flavor
def test_a_repo_config_listing_itself_arms_nothing_the_machine_did_not(flavor, tmp_path):
    root = _repo(tmp_path, enabled=True, onlyRepos=[str(tmp_path / "repo")])

    result = _scoped(flavor, tmp_path, root, enabled=None)

    assert _armed_or_silent(result, root) == "silent"


@by_flavor
def test_a_repo_opt_out_still_wins_inside_the_narrowing(flavor, tmp_path):
    root = _repo(tmp_path, enabled=False)

    result = _scoped(flavor, tmp_path, root, onlyRepos=[str(root)], onlySessions=[SESSION_A])

    assert _armed_or_silent(result, root) == "silent"


@pytest.mark.parametrize("raw,expect", [
    ("C:\\Repos\\Scratch\\", "c:/repos/scratch"),
    ("c:/repos/scratch", "c:/repos/scratch"),
    ("/c/Repos/Scratch", "c:/repos/scratch"),
    ("C:/Repos/Scratch//", "c:/repos/scratch"),
    ("C:", "c:/"),
    ("C:\\", "c:/"),
    ("\\\\server\\share\\repo\\", "//server/share/repo"),
    ("Repos\\Scratch", ""),
    (".", ""),
    ("", ""),
    (None, ""),
    (["C:\\x"], ""),
])
def test_windows_repo_paths_normalise_to_one_form(raw, expect):
    assert crew_autocycle.normalise_repo_path(raw, windows=True) == expect


@pytest.mark.parametrize("raw,expect", [
    ("/srv/repo/", "/srv/repo"),
    # A backslash is a legal POSIX filename character, not a separator -- it
    # is not the leading "/" an absolute POSIX path needs, so this is refused
    # rather than resolved as "/srv/repo".
    ("\\srv\\repo\\", ""),
    # A literal backslash INSIDE an otherwise-absolute POSIX path survives
    # untouched, rather than collapsing into a slash and matching a
    # different, unlisted directory.
    ("/srv\\repo", "/srv\\repo"),
    ("/", "/"),
    ("srv/repo", ""),
])
def test_posix_repo_paths_normalise_to_one_form(raw, expect):
    assert crew_autocycle.normalise_repo_path(raw, windows=False) == expect


def test_in_scope_on_windows_is_case_insensitive_for_repos_only():
    cfg = {"onlyRepos": ["C:\\Repos\\Scratch"], "onlySessions": ["Abc"]}

    assert crew_autocycle.in_scope(cfg, "c:/repos/scratch/", "Abc", windows=True) is True
    assert crew_autocycle.in_scope(cfg, "c:/repos/scratch/", "abc", windows=True) is False


def test_in_scope_does_not_collapse_backslash_and_slash_on_posix():
    """Review round 1 (crew-1.0-burnin-fix4): normalise_repo_path used to
    replace backslashes with slashes unconditionally, so an onlyRepos entry
    written with a backslash matched a differently-named POSIX repo that
    was never listed. A backslash is an ordinary filename character on
    POSIX, not a separator, and must not be treated as one."""
    cfg = {"onlyRepos": ["/tmp/allowed\\repo"]}

    assert crew_autocycle.in_scope(cfg, "/tmp/allowed/repo", "s", windows=False) is False
    assert crew_autocycle.in_scope(cfg, "/tmp/allowed\\repo", "s", windows=False) is True


# --- review round 2 (crew-1.0-r3-autocycle) --------------------------------


def test_a_trailing_space_in_an_only_repos_entry_does_not_authorise_the_bare_path():
    """Review round 2: normalise_repo_path used to `.strip()` the entry
    before comparing, so an onlyRepos entry that (by typo or otherwise)
    named "<repo> " with a trailing space matched the space-free repo too --
    a repo NOT listed must never come into scope. Whitespace is a legal
    POSIX filename character and two paths that differ only by it are two
    different paths. On native Windows the root is POSIX-shaped
    (`_posix_shaped`): the cwd is `C:\\...` there, which these rules refuse
    outright, so the second assertion could never hold."""
    root = str(_posix_shaped(None, "repo")) if os.name == "nt" else os.getcwd()
    cfg = {"onlyRepos": [root + " "]}

    assert crew_autocycle.in_scope(cfg, root, "s", windows=False) is False
    assert crew_autocycle.in_scope(cfg, root + " ", "s", windows=False) is True


def test_a_drive_letter_path_is_not_absolute_on_posix():
    """Review round 2: the absolute-path check used one regex for both
    platforms, so a Windows-shaped "c:/.." entry read as absolute on POSIX
    too and, being relative to nothing real, matched the current repo
    through realpath's own resolution. A RELATIVE entry (this repo has no
    "c:" root) must be refused, not resolved."""
    root = os.getcwd()
    assert crew_autocycle.normalise_repo_path("c:/..", windows=False) == ""
    assert crew_autocycle.in_scope({"onlyRepos": ["c:/.."]}, root, "s", windows=False) is False


def test_windows_repo_matching_does_not_casefold_a_sharp_s():
    """Review round 2: comparing paths with `str.casefold()` uses Unicode
    special-casing, which maps "straße" and "strasse" to the same string --
    Windows' own case-insensitive path comparison does not. A listed
    "strasse" must not authorise an unlisted "straße"."""
    cfg = {"onlyRepos": [r"C:\Repos\strasse"]}

    assert crew_autocycle.in_scope(
        cfg, "C:\\Repos\\stra\u00dfe", "s", windows=True) is False
    # Ordinary ASCII case-insensitivity still holds.
    assert crew_autocycle.in_scope(
        cfg, "C:\\REPOS\\STRASSE", "s", windows=True) is True


# --- review round 3 (crew-1.0-r4-scope) ------------------------------------


@pytest.mark.skipif(os.name == "nt", reason=(
    "needs a real symlinked tmp dir resolved under the POSIX rules: normalise_repo_path "
    "runs realpath only when windows= matches the host, so windows=False on native "
    "Windows is lexical and refuses the C:\\ tmp_path outright (T-0076)"))
def test_normalise_repo_path_resolves_a_dotdot_after_a_symlinked_component(tmp_path):
    """The Python realpath call must not collapse a `..` lexically: `os.path.realpath` resolves every component of a
    symlink's target, INCLUDING a `..` that comes after another symlinked
    component, against what has actually been resolved on disk so far --
    never against the raw, unresolved target string. `alias -> B/nested`,
    `A/link -> ../alias/../repo`: the real path is `B/repo`; the LEXICAL
    collapse of the target string alone (ignoring that `alias` is a
    symlink) would give the sibling `repo`, which must not be what this
    resolves to."""
    b_dir = tmp_path / "B"
    (b_dir / "nested").mkdir(parents=True)
    (b_dir / "repo").mkdir()
    (tmp_path / "repo").mkdir()
    a_dir = tmp_path / "A"
    a_dir.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(b_dir / "nested", target_is_directory=True)
        (a_dir / "link").symlink_to(
            os.path.join("..", "alias", "..", "repo"), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    resolved = crew_autocycle.normalise_repo_path(str(a_dir / "link"), windows=False)

    assert resolved == crew_autocycle.normalise_repo_path(str(b_dir / "repo"), windows=False)
    assert resolved != crew_autocycle.normalise_repo_path(str(tmp_path / "repo"), windows=False)


# --- the whole cycle: wrap-up -> handoff -> clear -> resume ----------------

@by_flavor
@pytest.mark.parametrize("source", ["clear", "compact"])
def test_write_clear_resume_carries_the_next_action_end_to_end(flavor, source, tmp_path):
    """The handoff's next action is its LAST section, after a body longer than
    the whole resume budget -- the shape a truncating resume used to lose.
    Parametrized over BOTH SessionStart sources auto-clear can trigger a
    reload from -- `/clear` and `/compact` -- so the reload path is proved
    for each, not assumed from the other."""
    root = context_fixtures.make_repo(tmp_path, config={"context": _context_cfg()})
    env = _sendable(flavor, tmp_path, root)
    transcript = _transcript(root, 950_000)

    wrap = _invoke(flavor, "context-watch", root, _stop(root, transcript), env_extra=env)
    _write_handoff(root, "# Handoff\nticket: T-1\n\n## In flight\n" + "- detail line\n" * 400
                   + "\n## Next action\nRun the NEXT-ACTION-TOKEN migration.\n")
    _invoke(flavor, "context-watch", root, _stop(root, transcript, active=True), env_extra=env)
    start = {"session_id": SESSION_B, "source": source, "cwd": str(root), "hook_event_name": "SessionStart",
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
