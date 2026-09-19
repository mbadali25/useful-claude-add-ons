"""A rule longer than the TTL must not lose its lock mid-run.

From the Codex review of 0.19.65-0.19.70, the fourth FIX. Cutting LOCK_TTL to
180s in 0.19.65 was justified by a HEARTBEAT, but the heartbeat fires BETWEEN
rules -- `lock_touch` is called after each one -- so a SINGLE rule that takes
longer than the TTL still lets the other flavour reclaim a live lock and run
concurrently: two gates, two verdicts, one turn, which is the exact thing the
lock exists to prevent.

It is not hypothetical here. This repo's own `.crew/verify.json` declares a
185s rule (the whole crew suite) against a 180s TTL.

**The mechanism, and why it is not the one that was asked for.** The reviewer
preferred a background toucher running DURING the rule. That was not taken,
and the reason is measurable rather than stylistic: a backgrounded process is
ORPHANED when its parent is SIGKILLed, and an orphan that keeps refreshing the
token means the lock never goes stale and verification is disabled
permanently. Bounding that needs either a pid liveness check -- measured
unreliable on this platform, recorded in verify-gate.sh's own 2026-09-13 note,
where a hard-killed Git Bash pid reported ALIVE at +0.5s, +5s and +15s -- or a
pipe-EOF trick whose PowerShell equivalent is different machinery, which is
the .sh/.ps1 drift this pair exists to avoid.

Instead the holder PUBLISHES A DEADLINE sized from the map's own measured
numbers: `max(LOCK_TTL, 2 x the largest stated cost among the selected
rules)`. Same arithmetic in both shells, no background process, bounded by
construction.

**The cost, stated rather than hidden:** a hard-killed holder now holds the
lock for up to that window instead of LOCK_TTL -- 370s rather than 180s on
this repo. Bounded, proportionate to what the map says the work takes, and the
back-off announces itself, so the window is visible rather than silent.

**The residual gap, not closed:** a rule with NO stated cost contributes 0, so
a map with no `seconds` keeps exactly the old behaviour and an unstated rule
longer than the TTL can still lose its lock. Giving it a `seconds` closes it.

`CREW_VERIFY_LOCK_TTL` is a test seam so these cases cost seconds rather than
minutes. It is read from the environment and deliberately not from config: a
repo setting it would be quietly changing how long one flavour waits for the
other.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None,
                                                reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]

# TTL of 3s against a rule that STATES 8s and sleeps 6s. The window is
# max(3, 2*8) = 16s, so a challenger arriving after the TTL but inside the
# window must still back off. Small numbers on purpose: the property is the
# arithmetic, and burning 240 real seconds to assert it would make this the
# slowest case in the suite for no extra evidence.
_TTL = "3"
_LONG_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 8, "run": ["sleep 6"],
               "why": "states 8s, sleeps 6s, against a 3s TTL"}],
    "default": [], "unmapped": "ignore",
}


def _repo(tmp_path, verify_map=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root,
                   check=True, capture_output=True, text=True)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(
        json.dumps(verify_map if verify_map is not None else _LONG_RULE),
        encoding="utf-8")
    return root


def _cmd(flavour):
    if flavour == "sh":
        return [_BASH, _SH]
    return [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]


def _env(root):
    return dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
                CREW_VERIFY_LOCK_TTL=_TTL)


def _run(flavour, root):
    return subprocess.run(
        _cmd(flavour), input="{}", cwd=str(root), env=_env(root),
        capture_output=True, text=True, check=False)


def _lock(root):
    return root / ".crew" / ".verify-gate.lock"


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_longer_than_the_ttl_keeps_its_lock(flavour, tmp_path):
    """MUST-ALLOW, and the defect itself: the holder is still working, well
    past the TTL, and the challenger must stand down rather than run a second
    gate over the same turn."""
    root = _repo(tmp_path)
    holder = subprocess.Popen(  # pylint: disable=consider-using-with
        _cmd(flavour), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, cwd=str(root), env=_env(root), text=True)
    try:
        holder.stdin.write("{}")
        holder.stdin.close()
        # Past the 3s TTL, comfortably inside the 16s window, and while the
        # 6s rule is still running.
        time.sleep(4)
        assert holder.poll() is None, "the holder finished too early to test"
        deadline_file = _lock(root) / "deadline"
        assert deadline_file.exists(), (
            "the holder published no deadline, so the challenger has only the "
            "age window and will reclaim a live lock"
        )

        challenger = _run(flavour, root)
        assert "backed off" in challenger.stderr, (
            "a live holder past the TTL lost its lock: two gates would run "
            "the same turn. " + challenger.stderr
        )
        assert "may run for another" in challenger.stderr, (
            "the back-off should name the holder's declared window. "
            + challenger.stderr
        )
    finally:
        try:
            holder.wait(timeout=30)
        except subprocess.TimeoutExpired:
            holder.kill()


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_expired_deadline_is_still_reclaimed(flavour, tmp_path):
    """MUST-BLOCK, and what stops the fix becoming a lock that can never go
    stale. A holder that died leaves a deadline in the past; the gate must
    take the lock and actually run."""
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    (lock / "token").write_text("abandoned-holder", encoding="utf-8")
    (lock / "deadline").write_text(str(int(time.time()) - 60),
                                   encoding="utf-8")
    old = time.time() - 600
    os.utime(lock / "token", (old, old))
    os.utime(lock, (old, old))

    result = _run(flavour, root)
    assert "backed off" not in result.stderr, (
        "a lock whose declared deadline has passed is abandoned and must be "
        "reclaimed, or a killed holder wedges the gate for ever. "
        + result.stderr
    )
    assert "sleep 6" in result.stderr, (
        "having reclaimed the lock the gate must actually RUN the rule. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_lock_with_no_deadline_falls_back_to_the_age_window(flavour, tmp_path):
    """Backwards compatibility, and it is load-bearing during a rollout: a
    lock written by a version that never published a deadline must age exactly
    as it used to rather than being treated as held for ever."""
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    (lock / "token").write_text("old-version-holder", encoding="utf-8")
    assert not (lock / "deadline").exists()
    old = time.time() - 600
    os.utime(lock / "token", (old, old))
    os.utime(lock, (old, old))

    result = _run(flavour, root)
    assert "backed off" not in result.stderr, (
        "no deadline and a token 600s older than the 3s TTL is a stale lock; "
        "it must be reclaimed by the age window. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_fresh_lock_with_no_deadline_still_backs_off(flavour, tmp_path):
    """The other half of the fallback: inside the age window, still held."""
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    (lock / "token").write_text("old-version-holder", encoding="utf-8")
    now = time.time()
    os.utime(lock / "token", (now, now))

    result = _run(flavour, root)
    assert "backed off" in result.stderr, (
        "a lock with no deadline but a token newer than the TTL is still "
        "held. " + result.stderr
    )


@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="cross-flavour agreement needs both on the same machine",
)
def test_each_flavour_honours_a_deadline_the_other_published(tmp_path):
    """The whole point of the lock. A deadline one flavour writes has to mean
    the same thing to the other, or the pair reclaims each other's live locks
    and both run."""
    for writer, reader in (("ps1", "sh"), ("sh", "ps1")):
        root = _repo(tmp_path / (writer + "-to-" + reader))
        lock = _lock(root)
        lock.mkdir(parents=True)
        (lock / "token").write_text(writer + "-holder", encoding="utf-8")
        (lock / "deadline").write_text(str(int(time.time()) + 30),
                                       encoding="utf-8")

        result = _run(reader, root)
        assert "backed off" in result.stderr, (
            "the " + reader + " flavour ignored a deadline the " + writer
            + " flavour published, so it would reclaim a live lock. "
            + result.stderr
        )


# --- the in-rule refresh, proven from inside a running rule -----------------
#
# Every must-allow case above pre-ages a token or deadline with os.utime and
# asserts on the gate READING it. That proves the challenger honours a
# deadline once one exists; it proves nothing about whether the HOLDER keeps
# republishing one DURING its own run, because none of those cases ever runs
# a rule -- deleting lock_extend's in-rule call entirely (keeping only the
# one before the first rule) would pass every case above unchanged. This is
# the same gap `test_the_heartbeat_actually_rewrites_the_token_during_a_run`
# closed for the heartbeat in test_verify_gate_lock_sh.py, applied to the
# deadline: read the deadline file's mtime, spend real time INSIDE the run,
# read it again.

_DEADLINE_PROBE_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 8, "run": [
        "stat -c %Y .crew/.verify-gate.lock/deadline > d0.txt",
        "sleep 3",
        "stat -c %Y .crew/.verify-gate.lock/deadline > d1.txt",
    ], "why": "probes whether the deadline is refreshed mid-run"}],
    "default": [], "unmapped": "ignore",
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_deadline_is_republished_during_a_run_not_only_once(flavour, tmp_path):
    """MUST-ALLOW. `seconds: 8` gives lock_window something to size a
    16s window from (max(TTL, 2*8)), so the deadline file exists before the
    first probe command runs. A working in-rule republish (lock_extend after
    EVERY command, not only before the first) puts the second reading a full
    sleep later than the first; a version that republishes only before the
    first rule leaves both readings identical, because nothing touches the
    file again until the run ends.
    """
    root = _repo(tmp_path, _DEADLINE_PROBE_RULE)
    result = _run(flavour, root)
    assert result.returncode == 0, (
        f"the probe rule should pass. stdout: {result.stdout} "
        f"stderr: {result.stderr}"
    )

    d0 = (root / "d0.txt").read_text(encoding="utf-8").strip()
    d1 = (root / "d1.txt").read_text(encoding="utf-8").strip()
    assert d0 and d1, f"the probe did not record the deadline mtime: {d0!r} {d1!r}"
    drift = int(d1) - int(d0)
    assert drift >= 2, (
        "the deadline file was not rewritten during the run: its mtime moved "
        f"{drift}s across a 3s in-rule sleep, so a version that republishes "
        "the deadline only BEFORE the first rule (and never after) would "
        f"pass this too. stdout: {result.stdout} stderr: {result.stderr}"
    )


# --- CREW_VERIFY_LOCK_TTL narrows only, never widens ------------------------
#
# The seam exists so the suite can make the window SMALLER than 180s and
# finish in seconds. It must never let a stray or malicious env var make a
# live repo's window LARGER -- that would mean a killed holder's lock stands
# for longer than the compiled default, silently, because nobody would think
# to look for an env var as the cause. And an unparseable value has to fall
# back to the compiled default, not to zero: zero would make every lock look
# expired the instant it is read, disabling the lock outright.
#
# A rule with NO stated `seconds` gives lock_window nothing to add, so the
# published window equals LOCK_TTL exactly (max(LOCK_TTL, 2*0)). Reading
# `deadline - now` right after the gate publishes it (both read from inside
# the run, so no real waiting) isolates LOCK_TTL without burning wall-clock
# time on the 180s default case.

_NO_COST_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "run": [
        "date +%s > now.txt",
        "cat .crew/.verify-gate.lock/deadline > deadline.txt",
    ], "why": "no stated cost, isolates LOCK_TTL in the published window"}],
    "default": [], "unmapped": "ignore",
}


def _published_window(flavour, tmp_path, env_ttl):
    root = _repo(tmp_path, _NO_COST_RULE)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    if env_ttl is None:
        env.pop("CREW_VERIFY_LOCK_TTL", None)
    else:
        env["CREW_VERIFY_LOCK_TTL"] = env_ttl
    result = subprocess.run(
        _cmd(flavour), input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        f"the probe rule should pass. stdout: {result.stdout} "
        f"stderr: {result.stderr}"
    )
    now = int((root / "now.txt").read_text(encoding="utf-8").strip())
    deadline = int((root / "deadline.txt").read_text(encoding="utf-8").strip())
    return deadline - now


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_lock_ttl_env_var_narrows_the_window(flavour, tmp_path):
    """Sanity check for the seam's intended direction: a smaller value is
    honoured."""
    window = _published_window(flavour, tmp_path, "3")
    assert 0 <= window <= 5, (
        f"CREW_VERIFY_LOCK_TTL=3 should publish a ~3s window, got {window}s"
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_lock_ttl_env_var_cannot_widen_past_the_default(flavour, tmp_path):
    """MUST-BLOCK the widening direction. An env var asking for a window
    LARGER than the compiled 180s default must be ignored, not honoured."""
    window = _published_window(flavour, tmp_path, "99999")
    assert 170 <= window <= 190, (
        "CREW_VERIFY_LOCK_TTL=99999 widened the published window to "
        f"{window}s instead of clamping to the 180s compiled default -- a "
        "killed holder now wedges the gate for over a day."
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_lock_ttl_env_var_unparseable_falls_back_to_the_default_not_zero(
        flavour, tmp_path):
    """MUST-BLOCK. An unparseable value must fall back to the compiled
    default, not to zero -- zero would make every lock look expired the
    instant it is read, which disables the lock rather than shortening it."""
    window = _published_window(flavour, tmp_path, "not-a-number")
    assert 170 <= window <= 190, (
        "an unparseable CREW_VERIFY_LOCK_TTL published a "
        f"{window}s window instead of falling back to the 180s compiled "
        "default."
    )
