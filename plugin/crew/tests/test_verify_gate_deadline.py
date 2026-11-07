"""crew 1.2.116: the Stop gate keeps the hook deadline, persists as it goes,
diffs from origin/<default>, and reclaims a lock whose holder is dead.

Measured 2026-11-07 on a Windows desktop: the Stop gate took 862s on a clean
origin/main against the hook's 600s limit (rc 0, nothing stuck). Four defects
compounded, and each has a must-block and a must-allow case here:

1. NO DEADLINE CHECK. Rules were chosen cheapest-first from ESTIMATED prices,
   then each ran to completion with no clock at all. The gate now holds each
   rule's price against the time left before CREW_HOOK_DEADLINE (less a
   margin) and defers, by name, a rule that would not fit.
2. END-ONLY PERSISTENCE. The timings cache and the quiet log were written only
   when the run ended, and the hook kills with taskkill /F / SIGKILL, so a
   killed run recorded nothing and the next turn was killed the same way. Both
   are now written as the run goes, and the command in flight is recorded so a
   kill at the deadline prices it.
3. LOCAL-MAIN BASE. The diff base was `git merge-base HEAD main` on the LOCAL
   main, 31 commits behind origin/main in one worktree. It is now
   origin/<default> when that ref exists.
4. STALE-LOCK BACKOFF. A killed holder's lock backed every later Stop off
   ("NOTHING WAS VERIFIED") until its deadline. A lock whose holder process no
   longer exists is now reclaimed at once; a live or unanswerable one still
   holds.

Every case builds a throwaway repo under tmp_path and touches no real config.
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook  # noqa: E402  pylint: disable=wrong-import-order
import verify_record  # noqa: E402  pylint: disable=wrong-import-order

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

_T = crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S
# One gate run here can spawn python several times per rule (the per-rule
# progress write); on a loaded Windows host the 120s suite bound was measured
# too short for a run that then finished correctly. Bounded, never unbounded.
_GATE_T = 300


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, timeout=_T)


def _repo(tmp_path, rules, name="repo"):
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}), encoding="utf-8")
    # A Stop budget far above every price here, so what defers a rule in these
    # cases is the hook deadline, never the budget. The deadlines below leave
    # minutes of slack, not seconds: gate start-up alone was measured at 36s
    # on a loaded Windows host (2026-11-07) and must not decide a case.
    (root / ".crew" / "config.json").write_text(json.dumps(
        {"verify": {"stopBudgetSeconds": 5000}}), encoding="utf-8")
    return root


def _out(tmp_path):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return out


def _posix(path):
    return str(path).replace("\\", "/")


def _env(root, out, deadline_s=None, margin=None, verbose=True, **extra):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OUT_DIR=_posix(out))
    for k in ("CREW_HOOK_DEADLINE", "CREW_VERIFY_DEADLINE_MARGIN", "CREW_VERIFY_VERBOSE"):
        env.pop(k, None)
    if deadline_s is not None:
        env["CREW_HOOK_DEADLINE"] = str(int(deadline_s * 1000))
    if margin is not None:
        env["CREW_VERIFY_DEADLINE_MARGIN"] = str(margin)
    # Explicit either way: crew_fixtures' gate spawners default it to 1.
    env["CREW_VERIFY_VERBOSE"] = "1" if verbose else "0"
    env.update(extra)
    return env


def _run(root, env, *args):
    return crew_fixtures.run_gate([_BASH, _SH] + list(args), input="{}", cwd=str(root), env=env,
                                  capture_output=True, text=True, check=False, timeout=_GATE_T)


def _rule(paths, run, seconds=None):
    r = {"paths": paths, "run": run, "reach": "local", "why": "fixture"}
    if seconds is not None:
        r["seconds"] = seconds
    return r


def _timings(root):
    try:
        return json.loads((root / ".crew" / ".verify-gate.timings.json").read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError):
        return {}


# --- 1. the deadline ------------------------------------------------------

_FAST = _rule(["a.py"], ['touch "$OUT_DIR/fast"'], seconds=1)
_SLOW = _rule(["a.py"], ['touch "$OUT_DIR/slow"'], seconds=900)


def test_a_rule_that_would_pass_the_hook_deadline_is_deferred_by_name(tmp_path):
    """MUST-BLOCK. Both rules fit the fixture's Stop budget, but at most 300s
    are left before the hook deadline once the 60s margin is kept: the 900s
    rule must not start, must be named, and the run must not be recorded as
    verified."""
    root = _repo(tmp_path, [_FAST, _SLOW])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 60 + 300))
    assert result.returncode == 0, result.stderr
    assert "deferred: would pass the hook deadline" in result.stderr, result.stderr
    assert 'touch "$OUT_DIR/slow"' in result.stderr, (
        "the deferred rule must be NAMED. " + result.stderr)
    assert "priced 900s" in result.stderr, result.stderr
    assert (out / "fast").exists(), "the rule that fits must still run. " + result.stderr
    assert not (out / "slow").exists(), (
        "the rule that would pass the deadline RAN - the gate kept no clock. " + result.stderr)
    assert not (root / ".crew" / ".verify-verified-at").exists(), (
        "a run that deferred a rule was recorded as verified. " + result.stderr)
    assert not (root / ".crew" / ".verify-gate.fingerprint").exists(), result.stderr
    assert "would pass the hook deadline, and have not been checked" in result.stderr, result.stderr


def test_rules_that_fit_the_deadline_all_run_and_verify(tmp_path):
    """MUST-ALLOW, the pair of the case above: a deadline far away defers
    nothing, and the clean run is recorded as verified."""
    root = _repo(tmp_path, [_FAST, _SLOW])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 60 + 1500))
    assert result.returncode == 0, result.stderr
    assert "would pass the hook deadline" not in result.stderr, result.stderr
    assert (out / "fast").exists() and (out / "slow").exists(), result.stderr
    assert (root / ".crew" / ".verify-verified-at").exists(), result.stderr


def test_an_unpriced_rule_with_no_time_left_is_deferred_not_treated_as_free(tmp_path):
    """MUST-BLOCK. No `seconds` and no cached measurement: the price is
    unknown, and an unknown is not zero. With the deadline already inside the
    margin it must be deferred and say why."""
    root = _repo(tmp_path, [_rule(["a.py"], ['touch "$OUT_DIR/unpriced"'])])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 10))
    assert result.returncode == 0, result.stderr
    assert "has no price and no time is left" in result.stderr, result.stderr
    assert not (out / "unpriced").exists(), result.stderr
    assert not (root / ".crew" / ".verify-verified-at").exists(), result.stderr


def test_an_unpriced_rule_runs_while_time_is_left(tmp_path):
    """MUST-ALLOW: an unknown price is not infinity either."""
    root = _repo(tmp_path, [_rule(["a.py"], ['touch "$OUT_DIR/unpriced"'])])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 600))
    assert result.returncode == 0, result.stderr
    assert (out / "unpriced").exists(), result.stderr


def test_an_unreadable_deadline_is_said_and_defers_nothing(tmp_path):
    """The deadline cannot be told: say so, run as before the guard existed.
    Silently deferring would hide checks; silently ignoring would hide that
    the guard was off."""
    root = _repo(tmp_path, [_FAST, _SLOW])
    out = _out(tmp_path)
    env = _env(root, out)
    env["CREW_HOOK_DEADLINE"] = "soon"
    result = _run(root, env)
    assert result.returncode == 0, result.stderr
    assert "the hook deadline cannot be told" in result.stderr, result.stderr
    assert (out / "slow").exists(), result.stderr


def test_all_is_not_held_to_a_hook_deadline(tmp_path):
    """--all is /crew:verify's run, never the hook's: an inherited deadline
    must not defer anything there."""
    root = _repo(tmp_path, [_FAST, _SLOW])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 5), "--all")
    assert result.returncode == 0, result.stderr
    assert "would pass the hook deadline" not in result.stderr, result.stderr
    assert (out / "slow").exists(), result.stderr


def test_the_deadline_the_gate_reads_is_its_own_rows_kill_time_within_the_margin():
    """CREW_HOOK_DEADLINE is the DISPATCH deadline; the dispatcher kills the
    verify-gate row at min(row timeout, time left). The gate reads the former,
    which is safe only while the gap between them stays well inside the
    margin: verify-gate must be Stop's largest row (so event_timeout is its
    timeout + EVENT_SLACK) and EVENT_SLACK - DEADLINE_MARGIN must be small
    against verify-gate.sh's own DEADLINE_MARGIN."""
    stop = [row for row in crew_hook.TABLE if row.event == "Stop"]
    gate = [row for row in stop if row.script == "verify-gate.sh"]
    assert len(gate) == 1
    assert gate[0].timeout == max(row.timeout for row in stop), (
        "verify-gate is no longer Stop's largest row, so CREW_HOOK_DEADLINE can sit far past "
        "its own kill time - pass the row's deadline to the gate instead")
    gap = crew_hook.event_timeout("Stop") - crew_hook.DEADLINE_MARGIN - gate[0].timeout
    with open(_SH, encoding="utf-8") as fh:
        margin = int(re.search(r"^DEADLINE_MARGIN=(\d+)$", fh.read(), re.M).group(1))
    assert 0 <= gap <= margin // 4, (gap, margin)


# --- 2. persistence during the run ------------------------------------------

_FIRST = _rule(["a.py"], ["true"], seconds=1)
# Runs second (dearer), and copies what the first rule left on disk.
_PROBE = _rule(["a.py"], [
    'cp .crew/.verify-gate.timings.json "$OUT_DIR/timings.json" 2>/dev/null || echo none > "$OUT_DIR/timings.json"',
    'cp .crew/.verify-gate.inflight.json "$OUT_DIR/inflight.json" 2>/dev/null || echo none > "$OUT_DIR/inflight.json"',
    'cp .crew/.verify-gate.log "$OUT_DIR/log.txt" 2>/dev/null || echo none > "$OUT_DIR/log.txt"',
], seconds=2)


def test_timings_and_the_in_flight_command_are_on_disk_before_the_run_ends(tmp_path):
    """MUST-BLOCK end-only persistence. While the second rule runs, the first
    rule's timing must already be cached and the second's command recorded as
    in flight - what a run killed right then leaves for the next one."""
    root = _repo(tmp_path, [_FIRST, _PROBE])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 600))
    assert result.returncode == 0, result.stderr
    seen = (out / "timings.json").read_text(encoding="utf-8").strip()
    assert seen != "none", "no timings cache existed while the second rule ran. " + result.stderr
    first_key = verify_record.rule_key(_FIRST)
    assert json.loads(seen)["rules"].get(first_key, 0) >= 1, (
        "the first rule's timing was not persisted before the run ended: " + seen)
    inflight = json.loads((out / "inflight.json").read_text(encoding="utf-8"))
    assert inflight["cmd"].startswith("cp .crew/.verify-gate.inflight.json"), inflight
    assert inflight["keys"] == [verify_record.rule_key(_PROBE)], inflight
    assert isinstance(inflight["started"], int) and isinstance(inflight["deadline"], int), inflight
    assert not (root / ".crew" / ".verify-gate.inflight.json").exists(), (
        "a run that finished left its in-flight record behind")


def test_the_quiet_log_is_written_while_the_run_goes(tmp_path):
    """MUST-BLOCK end-only persistence of the quiet log: mid-run it already
    holds the first rule and says the run had not finished."""
    root = _repo(tmp_path, [_FIRST, _PROBE])
    out = _out(tmp_path)
    result = _run(root, _env(root, out, deadline_s=time.time() + 600, verbose=False))
    assert result.returncode == 0, result.stderr
    log = (out / "log.txt").read_text(encoding="utf-8")
    assert log.strip() != "none", "no log existed mid-run. " + result.stderr
    assert "RUN NOT FINISHED" in log, log
    assert re.search(r"verify-gate: \d+s  true$", log, re.M), log
    final = (root / ".crew" / ".verify-gate.log").read_text(encoding="utf-8")
    assert "RUN NOT FINISHED" not in final, "the finished run's log still reads as unfinished"


def _inflight(root, keys, started, deadline, cmd="sleep 999"):
    (root / ".crew" / ".verify-gate.inflight.json").write_text(json.dumps(
        {"cmd": cmd, "keys": keys, "started": started, "deadline": deadline}), encoding="utf-8")


def test_a_run_killed_at_the_deadline_prices_its_rule_for_the_next_stop(tmp_path):
    """MUST-BLOCK the never-self-correcting loop: a leftover in-flight record
    from a run killed at its deadline raises that rule's price, and with that
    price the rule is deferred by name instead of being killed again."""
    slow = _rule(["a.py"], ['touch "$OUT_DIR/slow"'], seconds=5)
    root = _repo(tmp_path, [slow])
    out = _out(tmp_path)
    key = verify_record.rule_key(slow)
    now = int(time.time())
    _inflight(root, [key], now - 300, now - 10)
    result = _run(root, _env(root, out, deadline_s=time.time() + 60 + 60))
    assert "killed at the hook deadline" in result.stderr, result.stderr
    assert _timings(root).get(key) == 290, _timings(root)
    assert "deferred: would pass the hook deadline" in result.stderr or \
        "permanently over budget" in result.stderr, result.stderr
    assert not (out / "slow").exists(), result.stderr
    assert not (root / ".crew" / ".verify-gate.inflight.json").exists()


def test_a_run_that_ended_before_its_deadline_reprices_nothing(tmp_path):
    """MUST-ALLOW: a deadline still in the future means the run ended some
    other way; how long it ran is unknown, and the price is left alone."""
    slow = _rule(["a.py"], ['touch "$OUT_DIR/slow"'], seconds=5)
    root = _repo(tmp_path, [slow])
    out = _out(tmp_path)
    key = verify_record.rule_key(slow)
    now = int(time.time())
    _inflight(root, [key], now - 30, now + 500)
    result = _run(root, _env(root, out, deadline_s=time.time() + 600))
    assert "nothing was re-priced" in result.stderr, result.stderr
    assert (out / "slow").exists(), result.stderr
    assert _timings(root).get(key, 0) < 290


# --- 3. the diff base --------------------------------------------------------

def _behind_main(tmp_path):
    """A repo whose LOCAL main is one commit behind origin/main, with HEAD on
    a feature branch cut from origin/main that changes only a.py."""
    rules = [_rule(["a.py"], ['touch "$OUT_DIR/a-ran"']),
             _rule(["x.py"], ['touch "$OUT_DIR/x-ran"'])]
    root = _repo(tmp_path, rules)
    (root / "a.py").unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "map")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "main")
    (root / "x.py").write_text("merged elsewhere", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "someone else's merged work")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "reset", "-q", "--hard", "HEAD~1")
    _git(root, "fetch", "-q", "origin")
    _git(root, "switch", "-q", "-c", "feat", "origin/main")
    (root / "a.py").write_text("x = 2", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the branch's own change")
    return root


def test_the_base_is_origin_main_not_a_stale_local_main(tmp_path):
    """MUST-BLOCK the local-main base: x.py came in through origin/main, not
    this branch, and must not be in scope."""
    root = _behind_main(tmp_path)
    out = _out(tmp_path)
    result = _run(root, _env(root, out))
    assert result.returncode == 0, result.stderr
    assert (out / "a-ran").exists(), result.stderr
    assert not (out / "x-ran").exists(), (
        "a file merged into origin/main was in scope - the base was the stale local main. "
        + result.stderr)
    assert "merge-base of HEAD with origin/main (remote-tracking)" in result.stderr, result.stderr


def test_with_no_origin_the_local_branch_is_the_base_and_says_so(tmp_path):
    """MUST-ALLOW: no remote at all is the ordinary fixture/solo-repo case."""
    root = _repo(tmp_path, [_rule(["a.py"], ['touch "$OUT_DIR/a-ran"'])])
    (root / "a.py").unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "map")
    _git(root, "switch", "-q", "-c", "feat")
    (root / "a.py").write_text("x = 2", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")
    out = _out(tmp_path)
    result = _run(root, _env(root, out))
    assert result.returncode == 0, result.stderr
    assert (out / "a-ran").exists(), result.stderr
    assert "merge-base of HEAD with main (local; no usable origin/main)" in result.stderr, result.stderr


# --- 4. a lock whose holder is dead ------------------------------------------

_RUN = _rule(["a.py"], ["echo RAN"], seconds=8)


def _dead_process():
    """(scheme, pid, stamp) for a process that existed and is gone."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    pid = proc.pid
    stamp = int(time.time())
    if os.name != "nt":
        stamp = int(open("/proc/%d/stat" % pid, encoding="ascii").read().rsplit(")", 1)[1].split()[19])
    proc.kill()
    proc.wait(timeout=30)
    return ("win" if os.name == "nt" else "proc"), pid, stamp


def _live_process():
    pid = os.getpid()
    if os.name == "nt":
        return "win", pid, int(time.time())
    return "proc", pid, int(open("/proc/%d/stat" % pid, encoding="ascii").read().rsplit(")", 1)[1].split()[19])


def _held_lock(root, owner):
    """A lock that the deadline and age rules both read as HELD: a deadline
    300s ahead and a fresh token. Only the owner can let it go."""
    lock = root / ".crew" / ".verify-gate.lock"
    lock.mkdir(parents=True)
    token = "sh-424242-%d-1" % int(time.time())
    (lock / "token").write_text(token + "\n", encoding="utf-8")
    (lock / "deadline").write_text(str(int(time.time()) + 300), encoding="utf-8")
    if owner is not None:
        scheme, pid, stamp, tok = owner
        (lock / "owner").write_text("%s %s %s %s\n" % (scheme, pid, stamp, tok or token), encoding="utf-8")
    return lock


@pytest.mark.skipif(os.name != "nt" and not os.path.isdir("/proc"), reason="needs /proc or Windows")
def test_a_lock_whose_holder_is_dead_is_reclaimed_at_once(tmp_path):
    """MUST-ALLOW, the defect: the holder was killed (no trap ran) and its
    process is gone. The deadline says 300s more; the gate must not wait."""
    root = _repo(tmp_path, [_RUN])
    scheme, pid, stamp = _dead_process()
    _held_lock(root, (scheme, pid, stamp, None))
    result = _run(root, _env(root, _out(tmp_path)))
    assert "backed off" not in result.stderr, (
        "a lock whose holder process no longer exists backed the gate off. " + result.stderr)
    assert "whose process no longer exists" in result.stderr, result.stderr
    assert "echo RAN" in result.stderr, result.stderr


@pytest.mark.skipif(os.name != "nt" and not os.path.isdir("/proc"), reason="needs /proc or Windows")
def test_a_lock_whose_holder_is_alive_still_holds(tmp_path):
    """MUST-BLOCK reclaiming a live holder: two gates in one turn is what the
    lock exists to prevent. Fail closed."""
    root = _repo(tmp_path, [_RUN])
    scheme, pid, stamp = _live_process()
    _held_lock(root, (scheme, pid, stamp, None))
    result = _run(root, _env(root, _out(tmp_path)))
    assert "backed off" in result.stderr, result.stderr
    assert "may run for another" in result.stderr, result.stderr


@pytest.mark.parametrize("owner", [
    None,                                   # a pre-1.2.116 lock: no owner file
    ("win", "abc", "1", None),              # unparseable
    ("bogus", "1", "1", None),              # unknown scheme
    "mismatched-token",                     # an owner beside another run's token
])
def test_an_owner_that_cannot_be_trusted_keeps_the_old_rules(tmp_path, owner):
    """MUST-BLOCK an unknown collapsing into "dead": anything short of a
    readable owner, for THIS token, proved gone, backs off as before."""
    root = _repo(tmp_path, [_RUN])
    if owner == "mismatched-token":
        scheme, pid, stamp = _dead_process()
        owner = (scheme, pid, stamp, "sh-1-1-other")
    _held_lock(root, owner)
    result = _run(root, _env(root, _out(tmp_path)))
    assert "backed off" in result.stderr, result.stderr


def _kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       check=False, timeout=30)
    else:
        crew_fixtures.kill_process_group(proc)
    proc.wait(timeout=30)


@pytest.mark.wallclock
@pytest.mark.skipif(os.name != "nt" and not os.path.isdir("/proc"), reason="needs /proc or Windows")
def test_a_hard_killed_gate_leaves_nothing_that_blocks_or_misprices_the_next(tmp_path):
    """END TO END, the way the hook does it: a real gate is hard-killed (the
    whole tree, no trap) mid-rule at a short deadline. The next Stop must not
    back off on the corpse's lock, and must price the killed rule from the
    in-flight record instead of starting it into the same kill."""
    slow = _rule(["a.py"], ["sleep 60"], seconds=1)
    root = _repo(tmp_path, [slow])
    out = _out(tmp_path)
    # 30s: start-up (bash, python, the matcher) must not use the window up
    # before the rule starts, even on a loaded Windows host.
    deadline = time.time() + 30
    env = _env(root, out, deadline_s=deadline, margin=0)
    holder = crew_fixtures.popen_gate([_BASH, _SH], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, cwd=str(root), env=env, text=True)
    try:
        holder.stdin.write("{}")
        holder.stdin.close()
        inflight = root / ".crew" / ".verify-gate.inflight.json"
        owner = root / ".crew" / ".verify-gate.lock" / "owner"
        bound = time.monotonic() + 60
        while not (inflight.exists() and owner.exists()):
            assert holder.poll() is None, "the holder ended before its rule started"
            assert time.monotonic() < bound, "the holder never started its rule"
            time.sleep(0.2)
    finally:
        _kill_tree(holder)
    assert (root / ".crew" / ".verify-gate.lock").is_dir(), "the kill left no lock - nothing to test"
    while time.time() < deadline + 1:
        time.sleep(0.2)
    # 5s left once the 60s margin is kept: the re-priced rule (>= 8s) must be
    # deferred by name, not started into the same kill.
    result = _run(root, _env(root, out, deadline_s=time.time() + 60 + 5))
    assert "backed off" not in result.stderr, result.stderr
    assert "whose process no longer exists" in result.stderr, result.stderr
    assert "killed at the hook deadline while running sleep 60" in result.stderr, result.stderr
    assert _timings(root).get(verify_record.rule_key(slow), 0) >= 8, _timings(root)
    assert "deferred: would pass the hook deadline" in result.stderr, result.stderr
