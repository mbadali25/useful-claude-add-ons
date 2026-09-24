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
                       capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True,
                   capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root,
                   check=True, capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
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
    return crew_fixtures.run_gate(
        _cmd(flavour), input="{}", cwd=str(root), env=_env(root),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _lock(root):
    return root / ".crew" / ".verify-gate.lock"


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_longer_than_the_ttl_keeps_its_lock(flavour, tmp_path):
    """MUST-ALLOW, and the defect itself: the holder is still working, well
    past the TTL, and the challenger must stand down rather than run a second
    gate over the same turn.

    Synchronised on the lock's own files, not a fixed sleep: a `sleep(4)`
    here flaked 1/5 on a loaded Windows host, because it was really guessing
    two things at once -- how long process start-up plus the mkdir-and-write
    that acquires the lock takes on THIS machine (pwsh alone was measured at
    0.8-1.4s a case elsewhere in this suite, see
    docs/review/06-windows-burn-in.md, and that is before the lock is even
    touched), and that 4s would land past the 3s TTL once it had. A slow
    enough start-up made the first guess wrong before the second guess's
    margin mattered. Waiting for `token`/`deadline` to exist removes the
    first guess; computing the remaining wait from the token's own recorded
    `mtime` removes the second."""
    root = _repo(tmp_path)
    holder = crew_fixtures.popen_gate(
        _cmd(flavour), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, cwd=str(root), env=_env(root), text=True)
    try:
        holder.stdin.write("{}")
        holder.stdin.close()

        # lock_extend() (both flavours) runs immediately after the lock is
        # acquired, well before the 6s rule -- so this loop resolves in
        # however long start-up plus one mkdir actually took, not a guess.
        token_file = _lock(root) / "token"
        deadline_file = _lock(root) / "deadline"
        sync_deadline = time.time() + 15
        while not (token_file.exists() and deadline_file.exists()):
            assert holder.poll() is None, (
                "the holder exited before publishing a deadline at all"
            )
            assert time.time() < sync_deadline, (
                "the holder never published a deadline within 15s"
            )
            time.sleep(0.05)

        # The property under test is that a challenger arriving AFTER the
        # TTL still backs off because of the published deadline, not the age
        # window -- so wait out the TTL measured from the token's own
        # mtime, rather than assuming a fixed sleep landed past it.
        remaining = float(_TTL) - (time.time() - token_file.stat().st_mtime)
        if remaining > 0:
            time.sleep(remaining)
        assert holder.poll() is None, "the holder finished too early to test"

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
            crew_fixtures.kill_process_group(holder)


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


# A rule long enough that the holder is demonstrably still inside it when the
# challenger arrives: states 8s (so the window is max(3, 2*8) = 16s) and sleeps
# 10, against the 3s TTL. The gap between 3 and 16 is the whole subject.
_CROSS_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 8, "run": ["sleep 10"],
               "why": "states 8s, sleeps 10s, against a 3s TTL"}],
    "default": [], "unmapped": "ignore",
}


@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="cross-flavour agreement needs both on the same machine",
)
def test_each_flavour_honours_a_deadline_the_other_published(tmp_path):
    """The whole point of the lock. A deadline one flavour writes has to mean
    the same thing to the other, or the pair reclaims each other's live locks
    and both run.

    THE WRITER ACTUALLY WRITES IT. This case used to fabricate both halves --
    it created the lock directory itself, wrote a token, wrote a deadline, and
    named the flavours only in the failure message. Nothing in it ran the
    writer, so removing deadline publication from both gates left it green:
    the token it planted was FRESH, so the age window alone forced the
    back-off it asserted. It was a test that passed without the feature it is
    named after, which is the vacuous shape sabotage.py exists to find and
    which sabotage.py could not find here, because no mutation of the source
    could reach it.

    So the holder is a real gate process of the WRITER flavour, the deadline
    on disk is the one that gate published, and the token's age is asserted to
    be PAST the TTL before the challenger runs -- which is what makes the
    back-off attributable to the deadline and to nothing else.
    """
    for writer, reader in (("ps1", "sh"), ("sh", "ps1")):
        root = _repo(tmp_path / (writer + "-to-" + reader), _CROSS_RULE)
        holder = subprocess.Popen(  # pylint: disable=consider-using-with
            _cmd(writer), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd=str(root), env=_env(root),
            text=True)
        try:
            holder.stdin.write("{}")
            holder.stdin.close()
            time.sleep(6)
            assert holder.poll() is None, (
                writer + " finished before the challenger could arrive, so "
                "nothing was held and this case proves nothing"
            )

            token = _lock(root) / "token"
            deadline = _lock(root) / "deadline"
            assert deadline.exists(), (
                "the " + writer + " flavour published no deadline, so the "
                "challenger has only the age window"
            )
            age = time.time() - token.stat().st_mtime
            assert age > float(_TTL), (
                "the premise: the token has to be OLDER than the " + _TTL
                + "s TTL, or the age window would force the back-off on its "
                "own and the deadline would never be consulted. age="
                + str(age)
            )

            result = _run(reader, root)
            assert "backed off" in result.stderr, (
                "the " + reader + " flavour ignored a deadline the " + writer
                + " flavour published, so it would reclaim a live lock. "
                + result.stderr
            )
            assert "may run for another" in result.stderr, (
                "and it has to back off on the DEADLINE, not on the age "
                "window -- the token is already past the TTL. "
                + result.stderr
            )
        finally:
            try:
                holder.wait(timeout=40)
            except subprocess.TimeoutExpired:
                holder.kill()


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

# reach: local - this probe reads the lock's own deadline file, which may
# or may not exist yet at reach-scan time depending on lock-acquisition
# timing; declaring it avoids that race turning an unrelated probe flaky
# under the round-4 scanner's existing-repo-file check.
_DEADLINE_PROBE_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 8, "reach": "local", "run": [
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

# reach: local - the twin of _DEADLINE_PROBE_RULE's note above.
_NO_COST_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "reach": "local", "run": [
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
    result = crew_fixtures.run_gate(
        _cmd(flavour), input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
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


# ---------------------------------------- a deadline that cannot be parsed
#
# MEANS NOT HELD. The gate used to read this file with `tr -dc "0-9"`, which
# DELETES what it does not like rather than refusing it, so `-9999999999`
# became `9999999999` -- a deadline in the year 2286 -- and the gate backed
# off with "may run for another 8210194761s", verifying nothing, for ever.
#
# That is this repository's recurring defect inverted: not an unknown
# collapsing into the permissive value, but a malformed value being REPAIRED
# into one. Same answer either way -- when the input cannot be read, assume
# the lock is NOT held and fall through to the age window.

_MALFORMED_DEADLINES = {
    # The reported case, verbatim, and the only one that ever reached
    # production behaviour: measured at 8210194761s of declared runway.
    "negative-huge": "-9999999999",
    # The same defect at the smallest size, so a fix that special-cases the
    # big number rather than the sign is caught.
    "negative-one": "-1",
    "not-a-number": "abc",
    "two-numbers": "12 34",
    "scientific": "1e10",
    "empty": "",
}


def _abandoned_lock(root, deadline_text):
    """A lock whose token is 600s old -- far past the 3s TTL -- carrying the
    given deadline. The age window alone would reclaim this lock, so a
    back-off can only have come from the deadline."""
    lock = _lock(root)
    lock.mkdir(parents=True)
    (lock / "token").write_text("abandoned-holder", encoding="utf-8")
    (lock / "deadline").write_text(deadline_text, encoding="utf-8")
    old = time.time() - 600
    os.utime(lock / "token", (old, old))
    os.utime(lock, (old, old))
    return lock


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("case", sorted(_MALFORMED_DEADLINES))
def test_an_unparseable_deadline_is_not_a_held_lock(flavour, case, tmp_path):
    """MUST-BLOCK. Every one of these must reclaim and RUN."""
    root = _repo(tmp_path)
    _abandoned_lock(root, _MALFORMED_DEADLINES[case])

    result = _run(flavour, root)
    assert "backed off" not in result.stderr, (
        "a deadline of " + repr(_MALFORMED_DEADLINES[case]) + " was read as a "
        "live holder on a token 600s past the TTL. An unparseable value must "
        "mean NOT HELD; coercing it into a number is how -9999999999 became a "
        "deadline in 2286. " + result.stderr
    )
    assert "echo RAN" in result.stderr or "sleep" in result.stderr, (
        "having reclaimed the lock the gate must actually RUN the rule. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_parseable_future_deadline_still_holds_the_lock(flavour, tmp_path):
    """MUST-ALLOW, and the pair to every case above -- same aged token, same
    fixture, the ONLY difference being that the deadline parses. Without this
    a fix that simply stopped reading the file would pass all six."""
    root = _repo(tmp_path)
    _abandoned_lock(root, str(int(time.time()) + 30))

    result = _run(flavour, root)
    assert "backed off" in result.stderr, (
        "a well-formed deadline 30s in the future is a lock that IS held, "
        "even on a token past the TTL -- that is the entire mechanism. "
        + result.stderr
    )
    assert "may run for another" in result.stderr, result.stderr


@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="parity needs both flavours on the same machine",
)
@pytest.mark.parametrize("value", ["9999999999", "0012", "2147483647"])
def test_both_flavours_read_the_same_deadline_the_same_way(value, tmp_path):
    """The values where the two implementations used to part company, and the
    reason the PowerShell half now casts to [long] rather than [int].

    Measured before the fix, on an aged token with a deadline of 9999999999:
    bash backed off and PowerShell RAN, because [int] overflows Int32 and the
    catch silently produced 0. That is not a synthetic input -- every
    legitimate deadline crosses Int32 max on 2038-01-19, after which the pair
    would have disagreed about every live lock on every machine.

    `0012` is the other side of it: pure digits, so both accept it, and both
    have to read it as twelve rather than as octal ten.
    """
    verdicts = {}
    for flavour in ("sh", "ps1"):
        root = _repo(tmp_path / (flavour + "-" + value))
        _abandoned_lock(root, value)
        result = _run(flavour, root)
        verdicts[flavour] = "backed off" in result.stderr

    assert verdicts["sh"] == verdicts["ps1"], (
        "the two flavours disagreed about a deadline of " + value
        + ": sh backed off=" + str(verdicts["sh"]) + ", ps1 backed off="
        + str(verdicts["ps1"]) + ". A lock one flavour honours and the other "
        "reclaims is two gates running the same turn."
    )


# ------------------------------------------- the TTL seam is read as DECIMAL
#
# `08` and `09` are all digits, so they pass the gate's filter and then die
# inside `$(( ))`, which reads a leading zero as octal. Measured before the
# fix: two `value too great for base (error token is "08")` lines and NO
# deadline published -- the test seam silently disabling the mechanism it
# exists to exercise, while the gate still exited 0.
#
# Probed from INSIDE a running rule, not after the run: the deadline file
# lives in the lock directory, which the holder's own trap removes on the way
# out, so a check made afterwards reads "absent" on a healthy gate too.

# reach: local - the twin of _DEADLINE_PROBE_RULE's note above; this is
# the one that actually surfaced the race (intermittent, since it depends
# on whether the lock's deadline file exists yet at scan time).
_TTL_PROBE_RULE = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "reach": "local", "run": [
        "date +%s > now.txt",
        "cat .crew/.verify-gate.lock/deadline > seen.txt 2>&1 "
        "|| echo ABSENT > seen.txt",
    ], "why": "reads the published deadline from inside the run"}],
    "default": [], "unmapped": "ignore",
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_zero_prefixed_ttl_is_decimal_and_still_publishes_a_deadline(
        flavour, tmp_path):
    root = _repo(tmp_path, _TTL_PROBE_RULE)
    result = crew_fixtures.run_gate(
        _cmd(flavour), input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
                 CREW_VERIFY_LOCK_TTL="08"),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    assert "value too great for base" not in result.stderr, (
        "`08` reached shell arithmetic as an octal literal. " + result.stderr
    )
    seen = (root / "seen.txt").read_text(encoding="utf-8").strip()
    assert seen != "ABSENT", (
        "no deadline was published at all, so a rule longer than the TTL "
        "would lose its lock -- and the gate still exited "
        + str(result.returncode) + " without saying so. " + result.stderr
    )
    assert seen.isdigit(), (
        "the deadline file should hold an epoch: " + repr(seen) + " "
        + result.stderr
    )
    # 08 read as decimal is EIGHT. Read as anything else -- or silently
    # dropped back to the compiled 180s default -- the window moves, so the
    # published deadline is what pins the value rather than the absence of an
    # error message.
    #
    # A bound of "< 170" (ported from e0278bc9) proved only "not the untouched
    # 180s default" -- it also passed a TTL misread as, say, 80 (10x the
    # requested 8, exactly the shape an octal/base misparse or a stray
    # multiplier would produce), which is precisely the silent-wrong-value
    # failure this test exists to catch. window must be MONOTONIC (checked
    # first) and DERIVED FROM 8, not merely "somewhere under 180".
    #
    # NOT wall-clock-speed-dependent: `before` used to be read by the TEST,
    # ahead of spawning the subprocess, so a slow host's fork/exec overhead
    # (launching bash.exe or pwsh and every rule-matcher subprocess, not a
    # calculation bug -- up to 12-16s observed on a slow Windows/Git-Bash
    # host) counted against the same 40s budget meant to catch a misparse.
    # A host slow enough to delay startup past 32s flaked this even though
    # the TTL was read correctly. `now.txt` is instead the gate's OWN
    # published start time: `date +%s`, run from INSIDE the rule, by the
    # same process that computed the deadline, so the difference is pure
    # TTL arithmetic with no process-spawn overhead in it at all.
    now = int((root / "now.txt").read_text(encoding="utf-8").strip())
    window = int(seen) - now
    assert window > 0, (
        "the published deadline is not after the moment the gate started, "
        "so lock_extend did not actually publish a forward-moving deadline. "
        "window=" + str(window) + "s " + result.stderr
    )
    assert window < 40, (
        "`CREW_VERIFY_LOCK_TTL=08` produced a window of " + str(window)
        + "s -- not close enough to a decimal-8 TTL (max(8, 2*0)) to rule "
        "out a silent misparse to 80 (an octal/base error) or a fallback to "
        "the untouched 180s compiled default. " + result.stderr
    )
