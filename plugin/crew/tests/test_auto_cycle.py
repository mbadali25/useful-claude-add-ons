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
import pathlib
import shutil
import subprocess
import tempfile
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


def _owner_stub(tmp_path, windows):
    """Maps every stubbed window's (fake) pid to a made-up, non-WindowsTerminal
    process name, so the ps1 flavour's owner-safety check (which calls the
    real `Get-Process`, unstubbable on a pid nothing is running under) can
    resolve a window's uniqueness without also exercising that unrelated
    safety check -- a pid this stub does not name still falls through to the
    real `Get-Process` and still declines if that lookup fails, unchanged."""
    path = tmp_path / "owners.json"
    path.write_text(json.dumps({str(w["pid"]): "notepad" for w in windows}), encoding="utf-8")
    return {"CREW_AUTOCLEAR_OWNER_STUB": str(path)}


def _sendable(flavor, tmp_path, root):
    """A target each flavour can identify uniquely: a tmux pane whose pid is
    this test process (an ancestor of the script) for bash, and one stubbed
    window owned by this test process for PowerShell.

    `method="sendkeys"` is explicit for ps1: since `auto` now resolves to
    `notify` on native Windows (the owner decision this method never
    exercises), a helper whose whole job is a WINDOW target has to ask for
    the method that still uses one."""
    if flavor == "sh":
        bindir = tmp_path / "fakebin"
        crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {os.getpid()}\n",
                                 f"@echo off\r\necho {os.getpid()}\r\n")
        _machine(root, method="tmux")
        return crew_fixtures.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7")
    _machine(root, method="sendkeys")
    return _windows(tmp_path, [{"id": 4242, "pid": os.getpid(), "title": "Claude Code"}])


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


@pytest.mark.skipif(_BASH is None, reason="needs bash")
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
    `tmux` is genuinely invoked by the real (harmless) detached sender."""
    root = _repo(tmp_path, method="tmux", delaySeconds=30)
    _machine(root)
    _write_marker(root)
    _write_handoff(root)
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {os.getpid()}\n")
    home = tmp_path / "home"  # `_machine` writes to root.parent/"home" == tmp_path/"home"
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               CLAUDE_PROJECT_DIR=str(root),
               PATH=crew_fixtures.shell_path("sh", [bindir]),
               TMUX="/tmp/fake,1,0", TMUX_PANE="%7")
    payload = _stop(root, root / ".work" / "irrelevant.jsonl", active=True)

    started = time.time()
    result = subprocess.run([_BASH, _script("sh", "context-watch")], cwd=str(root), env=env,
                            input=json.dumps(payload), capture_output=True, text=True,
                            timeout=5, check=False)
    elapsed = time.time() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 5, elapsed
    assert "sent - method tmux" in _log(root), _log(root) + result.stderr


@by_flavor
def test_the_forced_continuation_reaches_auto_clear_with_no_repo_config_json(flavor, tmp_path):
    """crew 1.0 F4 reachability fix. Before it, `context-watch.sh:81` /
    `context-watch.ps1:25` stood the whole hook down on a missing
    `.crew/config.json`, so a `.crew/` directory the machine had still opted
    in for (a fresh checkout, or one that ran `/crew:init` for something
    other than auto-clear) never reached the forced-continuation handover
    below -- even though auto-clear.sh/.ps1's OWN gate now arms on `.crew/`
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
    _machine(root, method="tmux" if flavor == "sh" else "sendkeys", delay=4)
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
    _machine(root, method="tmux" if flavor == "sh" else "sendkeys", delaySeconds="4")
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
    _machine(root, method="tmux" if flavor == "sh" else "sendkeys", delaySeconds="soon")
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
        env = {**_windows(tmp_path, windows), **_owner_stub(tmp_path, windows)}
        # Explicit: `auto` now resolves to `notify` on native Windows and
        # never touches window resolution at all, so this window-targeting
        # matrix has to request `sendkeys` by name to exercise it.
        _machine(root, method="sendkeys", windowTitle=title or None)
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


# --- Resolve-CrewLinkRoot: drive/UNC/rootless symlink targets ----------------
#
# auto-clear.ps1 has its own hand-rolled symlink walker (crew_autocycle.py
# uses os.path.realpath and has no equivalent code at all), and the piece
# that classifies a symlink TARGET's root cannot be integration-tested here:
# [System.IO.Path]::GetPathRoot's answer for a drive letter or a UNC share
# depends on the ACTUAL OS the .NET runtime is on, and Get-Item's own
# `.LinkTarget` lookup needs the component to exist for REAL on THIS
# filesystem at every hop -- neither is true on Linux/macOS for a Windows
# drive letter. So this extracts and runs the live function directly
# (never a hand-copied duplicate) rather than driving it through a real
# symlink chain, which only a real Windows host can do end to end.

def _extract_ps1_function(source, name):
    """Pull `function <name>(...) { ... }`'s exact text out of a .ps1 file by
    brace-counting. The rest of auto-clear.ps1 is a live Stop hook and every
    path through it ends in `exit`, which would kill the whole pwsh process
    if the file were dot-sourced whole just to reach one function."""
    marker = f"function {name}("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for i in range(brace_start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting {name} from the source")


_RESOLVE_CREW_LINK_ROOT_CASES = [
    ("C:/repo", "C:/", "repo", False),
    ("//srv/share/repo", "//srv/share/", "repo", False),
    ("//srv/share", "//srv/share/", "", False),
    ("/repo", None, "repo", True),
    ("repo", None, None, None),
    ("../rel", None, None, None),
]


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh")
@pytest.mark.parametrize("target,root,remainder,rootless", _RESOLVE_CREW_LINK_ROOT_CASES,
                         ids=[c[0] for c in _RESOLVE_CREW_LINK_ROOT_CASES])
def test_resolve_crew_link_root_classifies_drive_unc_and_rootless_targets(
        target, root, remainder, rootless):
    """Regression, Codex FIX|auto-clear.ps1:211: a drive-root-relative target
    (`\\repo`, i.e. `/repo` once backslashes are replaced) used to be read
    as fully qualified and become the WHOLE new root, throwing the alias's
    own drive away -- `C:\\alias -> \\repo` resolved to `\\repo`, not
    `C:\\repo`. A rootless target must instead take the link's OWN drive
    (Rootless=True, Root=$null, and the caller keeps its current root); a
    real drive letter or a UNC share stays fully qualified as itself
    (Rootless=False); an ordinary relative target gets no classification at
    all (None)."""
    # `target` is interpolated as a single-quoted literal, not passed as an
    # argument: `pwsh -Command <script> <arg>...` joins every extra arg onto
    # the SAME command line rather than binding them to $args, so a leading
    # "/" in `target` parses as a second, unrelated command.
    assert "'" not in target
    source = pathlib.Path(_script("ps1", "auto-clear")).read_text(encoding="utf-8")
    func = _extract_ps1_function(source, "Resolve-CrewLinkRoot")
    script = (func + f"\n$r = Resolve-CrewLinkRoot '{target}'\n"
              "if ($null -eq $r) { Write-Output 'NONE' } "
              "else { Write-Output \"$($r.Root)|$($r.Remainder)|$($r.Rootless)\" }\n")
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=False, timeout=30, stdin=subprocess.DEVNULL)
    out = result.stdout.strip()

    if root is None and remainder is None:
        assert out == "NONE", result.stderr
    else:
        assert out == f"{root or ''}|{remainder}|{rootless}", result.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
# A fixed id for this process's pid: under pytest-xdist each worker has its
# own pid, and ids that differ between workers abort the whole run.
@pytest.mark.parametrize("pane_pid,sent", [pytest.param(os.getpid(), True, id="own-pid-True"),
                                           pytest.param(999999, False, id="999999-False")])
def test_a_tmux_pane_must_be_the_one_running_this_session(pane_pid, sent, tmp_path):
    root = _repo(tmp_path)
    env = _sendable("sh", tmp_path, root)
    crew_fixtures.write_shim(tmp_path / "fakebin", "tmux", f"#!/bin/sh\necho {pane_pid}\n",
                             f"@echo off\r\necho {pane_pid}\r\n")
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
# `sendkeys` -------------------------------------------------------------

_NO_CAPABILITY_ENV = {"TMUX": "", "DISPLAY": "", "TMUX_PANE": ""}


@by_flavor
def test_auto_resolves_to_notify_on_native_windows_and_never_to_sendkeys(flavor, tmp_path):
    """Both senders: `auto` with no tmux pane and no X11 must choose `notify`,
    never the SendKeys-equivalent method, on native Windows. ps1 is always
    told OS=Windows_NT by `_invoke`; sh is told the same here explicitly --
    this is the one place a bash session can legitimately be "native
    Windows" (Git Bash), and the owner decision applies there too."""
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
    the configured number (or, as `auto-clear.ps1` used to, a hardcoded `0`)
    would read as a real delay `notify` never takes. Both flavours print the
    identical `n/a` text instead; `_repo`'s configured delaySeconds (9, not
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
    always empty for it. `auto-clear.ps1` has never printed a `target:` line
    there; `auto-clear.sh` used to print an empty one (`target: ` with
    nothing after it) regardless. Both now omit the line entirely."""
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
# keystroke method (tmux/sendkeys) has a real wait, and it is this value --
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
    crew_fixtures.write_shim(bindir, "tmux", f"#!/bin/sh\necho {os.getpid()}\n")
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
               CREW_TEST_REAL_BASH=_BASH,
               TMUX="/tmp/fake,1,0", TMUX_PANE="%7")
    payload = _stop(root, root / ".work" / "irrelevant.jsonl", active=True)

    result = subprocess.run([_BASH, _script("sh", "context-watch")], cwd=str(root), env=env,
                            input=json.dumps(payload), capture_output=True, text=True,
                            timeout=5, check=False)
    deadline = time.time() + 5
    while time.time() < deadline and not sleep_log.exists():
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

    result = _invoke(flavor, "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=dict(_NO_CAPABILITY_ENV))

    if flavor == "sh":
        # The .sh flavour has no forced OS -- it genuinely reads whatever
        # $OS this test process happens to have, which is never Windows_NT
        # in this suite's own environment.
        assert "would send" not in result.stdout
        assert "no usable method" in result.stderr
    else:
        # `_invoke` always forces OS=Windows_NT for ps1 -- that IS this
        # flavour's native platform, so `auto` resolves to `notify` here
        # regardless, and that is the correct answer, not a refusal.
        assert "method: notify" in result.stdout, result.stdout


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


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh")
@pytest.mark.skipif(not os.path.isdir("/proc"), reason=(
    "proves the fake process's name via /proc/<pid>/comm, which only exists on Linux -- "
    "real Windows Terminal needs no rename trick, and this is not the place to test that"))
def test_sendkeys_declines_and_falls_back_to_notify_when_the_owner_is_windows_terminal(tmp_path):
    """requirement: `sendkeys` must resolve the owning window, then decline
    rather than type when it cannot verify the window is showing the ONLY
    tab -- Windows Terminal hosts every tab in one window and nothing short
    of UI Automation (not a dependency here) can ask it which tab is
    active, so a window OWNED BY Windows Terminal always declines. Proved
    against a REAL process whose executable is literally named
    `WindowsTerminal` (a renamed `bash`, invoked so it does not exec-replace
    itself away) -- `Get-Process -Id ...).ProcessName` reads that name from
    the OS, not from a stub, so this is not the window-list fake and is the
    one thing in this file that has to run a real subprocess to prove."""
    exe = shutil.which("bash")
    if exe is None:
        pytest.skip("needs bash to build the fake WindowsTerminal process")
    root = _repo(tmp_path)
    wtbin = tmp_path / "wtbin" / "WindowsTerminal"
    wtbin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(exe, wtbin)
    wtbin.chmod(0o755)
    proc = subprocess.Popen([str(wtbin), "-c", "trap : TERM; sleep 30 & wait"])
    try:
        deadline = time.time() + 5
        while time.time() < deadline and _proc_comm(proc.pid) != "WindowsTerminal":
            time.sleep(0.05)
        assert _proc_comm(proc.pid) == "WindowsTerminal", (
            "the renamed process never reported comm=WindowsTerminal on this host")
        _machine(root, method="sendkeys", windowTitle="Claude")
        env = _windows(tmp_path, [{"id": 1, "pid": proc.pid, "title": "Claude - a tab"}])
        _write_marker(root)
        _write_handoff(root)

        dry = _invoke("ps1", "auto-clear", root, args=("--session", SESSION_A, "--dry-run"),
                     env_extra=env)
        result = _invoke("ps1", "auto-clear", root, args=("--session", SESSION_A), env_extra=env)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert "would decline" in dry.stdout, dry.stdout + dry.stderr
    assert "cannot verify the active tab" in dry.stdout
    assert result.returncode == 0
    log = _log(root)
    assert "declined sendkeys" in log, log
    assert "cannot verify the active tab" in log
    assert "sent notify instead" in log
    payload = json.loads(result.stdout)
    assert "safe to run" in payload["systemMessage"]
    assert "cleared" not in payload["systemMessage"]


def _proc_comm(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="ascii") as handle:
            return handle.read().strip()
    except OSError:
        return ""


# --- narrowing: onlyRepos / onlySessions -------------------------------------
#
# `enabled: true` in the machine file arms every Claude session on the host.
# These two machine-only keys narrow it, and can only narrow it. Every case
# goes through the real wrapper of each flavour, so the parity is measured.
# An unarmed case must be SILENT -- no plan on stdout, no log line -- because
# a session the machine never armed must not learn the feature exists.

def _scoped(flavor, tmp_path, root, session=SESSION_A, **scope):
    env = _sendable(flavor, tmp_path, root)
    _machine(root, **({"method": "tmux"} if flavor == "sh" else {}), **scope)
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


_OWNER_WINDOW_CAPABLE = None


def _pwsh_can_resolve_an_owner_window():
    """Probes the REAL (non-stubbed) window walk once: does any window on
    this host belong to an ancestor of this process? A non-interactive
    runner -- a scheduled task, a headless CI agent -- has none, and no
    "armed" ps1-flavour case can be proved there either, independent of
    whether the narrowing decision itself is right. Memoized: this spawns a
    real pwsh and is not free. Requests `sendkeys` explicitly: `auto` no
    longer reaches window resolution at all (it resolves to `notify` on
    native Windows), so a probe of the WINDOW capability has to ask for the
    method that still uses one."""
    global _OWNER_WINDOW_CAPABLE  # pylint: disable=global-statement
    if _OWNER_WINDOW_CAPABLE is not None:
        return _OWNER_WINDOW_CAPABLE
    if _PWSH is None:
        _OWNER_WINDOW_CAPABLE = False
        return False
    scratch = tempfile.mkdtemp(prefix="crew-owner-window-probe-")
    try:
        base = pathlib.Path(scratch)
        root = crew_fixtures.make_repo(base, config={"context": {"warnAt": 0.8}}, git=False)
        _machine(root, method="sendkeys")
        env = dict(os.environ, HOME=str(base / "home"), USERPROFILE=str(base / "home"),
                   CLAUDE_PROJECT_DIR=str(root), CREW_AUTOCLEAR_INHIBIT="1", OS="Windows_NT")
        result = subprocess.run(
            [_PWSH, "-NoProfile", "-NonInteractive", "-File", _script("ps1", "auto-clear"),
             "-Force", "-DryRun", "-Root", str(root)],
            cwd=str(root), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False, timeout=30)
        _OWNER_WINDOW_CAPABLE = "would send" in result.stdout
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return _OWNER_WINDOW_CAPABLE


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
    # the_bare_path for the direct unit test); this case proves
    # auto-clear.ps1's ConvertTo-CrewScopePath now matches, end to end,
    # through the real wrapper of each flavour.
    ("repo-trailing-space", {"onlyRepos": [_ROOT_TOKEN + " "]}, "silent"),
    # A backslash is a legal POSIX filename character, not a separator on
    # bash's flavour (crew_autocycle.normalise_repo_path, fixed in review
    # round 1 of crew-1.0-burnin-fix4 -- see test_in_scope_does_not_collapse_
    # backslash_and_slash_on_posix for the direct unit test). auto-clear.ps1
    # keeps its existing backslash handling -- real Windows paths always use
    # backslash as a separator, so ps1's answer is unchanged and correct
    # there; only bash's answer flips with this fix.
    ("repo-backslashes", {"onlyRepos": ["{root\\}"]}, {"sh": "silent", "ps1": "armed"}),
    ("repo-other", {"onlyRepos": ["{root}-other"]}, "silent"),
    ("repo-parent", {"onlyRepos": ["{parent}"]}, "silent"),
    ("repos-empty", {"onlyRepos": []}, "silent"),
    ("repo-relative-dot", {"onlyRepos": ["."]}, "silent"),
    ("repos-not-a-list", {"onlyRepos": _ROOT_TOKEN}, "silent"),
    ("both-match", {"onlyRepos": [_ROOT_TOKEN], "onlySessions": [SESSION_A]}, "armed"),
    ("both-session-misses", {"onlyRepos": [_ROOT_TOKEN], "onlySessions": [SESSION_B]}, "silent"),
    ("both-repo-misses", {"onlyRepos": ["{root}-other"], "onlySessions": [SESSION_A]}, "silent"),
]


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
        flavor, case, scope, expect, tmp_path):
    del case
    if isinstance(expect, dict):
        expect = expect[flavor]
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
        if flavor == "ps1" and not _pwsh_can_resolve_an_owner_window():
            pytest.skip("no window on this host belongs to any ancestor of "
                        "this process (a non-interactive runner), so this "
                        "case can only be PROVED armed by actually resolving "
                        "one - see test_in_scope_decides_the_scope_matrix_"
                        "with_no_subprocess_on_every_os for the narrowing "
                        "decision itself, which does not need a window")
    root = _repo(tmp_path)

    result = _scoped(flavor, tmp_path, root, **{k: _fill(v, root) for k, v in scope.items()})

    assert _armed_or_silent(result, root) == expect


@pytest.mark.parametrize("case,scope,expect", _SCOPE_CASES, ids=[c[0] for c in _SCOPE_CASES])
def test_in_scope_decides_the_scope_matrix_with_no_subprocess_on_every_os(
        case, scope, expect, tmp_path):
    """The exact `_SCOPE_CASES` table the wrapper test above drives through a
    real bash/pwsh, proved here straight against `crew_autocycle.in_scope` --
    no subprocess, no tmux, no window system, so this runs identically on a
    host that has neither and would otherwise skip every "armed" case above.
    POSIX only (`windows=False`): the "sh" expectation applies, since that is
    the branch a real POSIX `tmp_path` exercises; the Windows branch already
    has its own dedicated in-process cases (`test_in_scope_on_windows_is_
    case_insensitive_for_repos_only` and neighbours)."""
    del case
    if isinstance(expect, dict):
        expect = expect["sh"]
    root = tmp_path / "repo"
    root.mkdir()
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
def test_a_chained_relative_symlink_in_only_repos_resolves_from_its_own_parent(flavor, tmp_path):
    """A/link1 -> ../B/link2 -> inner/repo: each hop must resolve against the
    symlink that names it. Review round 1 (crew-1.0-burnin-fix4):
    auto-clear.ps1's own Resolve-CrewRealPath resolved every hop against the
    FIRST link's parent, so this chain silently resolved to A/inner/repo
    instead of B/inner/repo and disabled auto-clear for a listed repo.
    crew_autocycle.py has no equivalent bug -- it uses os.path.realpath --
    so this is ps1-only."""
    if flavor != "ps1":
        pytest.skip("only auto-clear.ps1 has its own symlink-chase implementation")
    b_dir = tmp_path / "B"
    root = _repo(b_dir / "inner")
    a_dir = tmp_path / "A"
    a_dir.mkdir()
    try:
        (b_dir / "link2").symlink_to(os.path.join("inner", "repo"), target_is_directory=True)
        (a_dir / "link1").symlink_to(os.path.join("..", "B", "link2"), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    result = _scoped(flavor, tmp_path, root, onlyRepos=[str(a_dir / "link1")])

    assert _armed_or_silent(result, root) == "armed"


@by_flavor
def test_a_symlinked_component_inside_a_substituted_target_still_resolves(flavor, tmp_path):
    """alias -> B, A/link -> ../alias/inner/repo: `alias` is a symlink
    INSIDE the target `link` substitutes to, not a symlink named directly
    by the path being walked. Review round 2 (crew-1.0-r3-autocycle):
    auto-clear.ps1's Resolve-CrewRealPath only re-chased a symlink chain
    hanging off the ORIGINAL path component ("link"); once its target was
    substituted, "alias" inside that substituted string was walked as an
    ordinary directory name and never itself resolved, so the listed path
    stayed under `alias` and did not match a run from `B/inner/repo`.
    crew_autocycle.py has no equivalent bug -- os.path.realpath resolves
    every component of a substituted target too -- so this is ps1-only."""
    if flavor != "ps1":
        pytest.skip("only auto-clear.ps1 has its own symlink-chase implementation")
    b_dir = tmp_path / "B"
    root = _repo(b_dir / "inner")
    a_dir = tmp_path / "A"
    a_dir.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(b_dir, target_is_directory=True)
        (a_dir / "link").symlink_to(
            os.path.join("..", "alias", "inner", "repo"), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    result = _scoped(flavor, tmp_path, root, onlyRepos=[str(a_dir / "link")])

    assert _armed_or_silent(result, root) == "armed"


@by_flavor
def test_a_dotdot_after_a_symlinked_component_resolves_before_it_collapses(flavor, tmp_path):
    """alias -> B/nested, A/link -> ../alias/../repo: the substituted target
    string has a ".." AFTER the symlinked component "alias", not before it.
    Review round 3 (crew-1.0-r4-scope): auto-clear.ps1 built that substituted
    target with .NET's GetFullPath, which collapses ".." purely LEXICALLY --
    "alias/.." cancelled to nothing before the walk ever asked whether
    "alias" is itself a symlink -- so A/link resolved to the lexical sibling
    "repo" instead of the real "B/repo", and an unrelated, unlisted repo
    sitting at that lexical path got armed by a listing that never named it.
    crew_autocycle.py has no equivalent bug -- os.path.realpath resolves
    every component, ".." included, against what the walk has actually
    reached so far -- so this is ps1-only."""
    if flavor != "ps1":
        pytest.skip("only auto-clear.ps1 has its own symlink-chase implementation")
    b_dir = tmp_path / "B"
    (b_dir / "nested").mkdir(parents=True)
    real_root = _repo(b_dir)
    decoy_root = _repo(tmp_path)
    a_dir = tmp_path / "A"
    a_dir.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(b_dir / "nested", target_is_directory=True)
        (a_dir / "link").symlink_to(
            os.path.join("..", "alias", "..", "repo"), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    decoy_result = _scoped(flavor, tmp_path, decoy_root, onlyRepos=[str(a_dir / "link")])
    real_result = _scoped(flavor, tmp_path, real_root, session=SESSION_B,
                           onlyRepos=[str(a_dir / "link")])

    # The invariant: an unlisted repo must never be in scope. The decoy sits
    # at the LEXICAL result of the old, buggy collapse; only the real,
    # symlink-resolved repo was ever listed.
    assert _armed_or_silent(decoy_result, decoy_root) == "silent"
    assert _armed_or_silent(real_result, real_root) == "armed"


@by_flavor
def test_a_symlink_cycle_in_only_repos_fails_closed(flavor, tmp_path):
    """A self-referential symlink in an onlyRepos entry must never resolve
    to a partial path that happens to match something real. Review round 2
    raised auto-clear.ps1's old 8-hop-per-component bound (too low for a
    legitimate long chain, and silently kept whatever partial path it had
    reached on exceeding it) to a single bound across the whole walk, and
    made exceeding THAT an explicit failure -- the entry normalises to ""
    and therefore matches nothing, rather than arming (or silently
    disarming) on an unresolvable value."""
    if flavor != "ps1":
        pytest.skip("crew_autocycle.py's os.path.realpath is cycle-safe by construction")
    loop_dir = tmp_path / "loop"
    loop_dir.mkdir()
    loop_link = loop_dir / "loop"
    try:
        loop_link.symlink_to(loop_link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")
    root = _repo(tmp_path)

    result = _scoped(flavor, tmp_path, root, onlyRepos=[str(loop_link)])

    assert _armed_or_silent(result, root) == "silent"


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
    different paths."""
    root = os.getcwd()
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


def test_normalise_repo_path_resolves_a_dotdot_after_a_symlinked_component(tmp_path):
    """The Python twin's realpath call must not share auto-clear.ps1's
    lexical-collapse bug: `os.path.realpath` resolves every component of a
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
