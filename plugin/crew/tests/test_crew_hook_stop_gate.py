"""The Stop gate and the guards, driven through the REAL dispatcher (L-0869 G1, G2, G4).

Every other verify-gate, scope-guard, approval-hook and completion-audit suite
spawns the script directly. That is necessary and it is not the claim. Since
L-0727 slice 2 the only thing that runs those four on Windows is
`crew-hook.ps1`, and L-0869 deleted their `.ps1` twins, so the dispatcher is
now the *single* path to them on that platform. Nothing asserted that path for
the Stop gate or for the three guards:

  G1  `CREW_HOOK_TRACE_FILE` is read by `test_crew_hook_windows.py`,
      `test_crew_hook_faults.py` and `sabotage_crew_hook.py`, and none of the
      three drives the Stop gate. No test anywhere proved that a Stop event
      reaches `verify-gate.sh` **once**, blocks on a tree the record does not
      cover, or writes the record when it passes.
  G2  `test_verify_gate_lock_concurrent.py` now races two gates, but it races
      them as `bash verify-gate.sh`. The race that happens in production is two
      Stop *events*, each going through the dispatcher, and the dispatcher adds
      a layer (its own timeout, its deadline, its child plumbing) that can lose
      the lock on its own.
  G4  Of the PreToolUse guards only `cloud-guard.sh` was ever driven through
      the dispatcher (`test_crew_hook_windows.py:188`). `scope-guard.sh`,
      `approval-hook.sh` and `completion-audit.sh` were not.

Two cases the task listed are NOT re-written here, because they already exist
and a third copy would be duplication, not coverage:

  * Git Bash absent on an armed host -> exit 2 naming Git for Windows, and
    unarmed -> exit 0, are
    `test_crew_hook_windows.py::test_armed_with_no_git_bash_the_blocking_events_exit_2_naming_git_for_windows`
    and `::test_unarmed_with_no_git_bash_the_blocking_events_exit_0`, both
    parametrized over `Stop`. What they do NOT assert is that the refusal
    happens *before* any child runs, so that one case is added below.
  * The no-python POSIX path is `test_crew_hook_faults.py`'s
    (`::test_with_no_python_the_scripts_own_fallbacks_decide`), which is
    explicitly `skipif(WINDOWS)` - "the no-python POSIX path is not a Windows
    path (B10)". The Windows dispatcher resolves python itself
    (`crew-hook.ps1:390-399`), and nothing covered that, so it is added below.

This file is NOT Windows-only. `crew-hook.ps1` runs under pwsh on a POSIX host
with `OS=Windows_NT` (what `crew_hook_harness.run_launcher` sets up), so the
Linux gate exercises the same dispatcher and the same `.sh` children. The one
difference there is which rows `select` picks for a `PowerShell` tool call, and
no case here sends one.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_hook_harness as h
import crew_ticket
import record_golden_hooks as rgh
import scope_fixtures

pytestmark = [
    h.needs_pwsh,
    pytest.mark.skipif(h.BASH is None, reason="needs bash - the dispatcher's children are .sh"),
]

# One case here cannot run in the pwsh-on-POSIX model; its docstring carries
# the measurement. Spec A10 makes the win-repo-2 run the evidence for it, so a
# skip THERE is a failed acceptance, not a pass.
native_only = pytest.mark.skipif(
    not h.WINDOWS,
    reason="needs a real Windows host: the python handoff to approval-hook.sh is wrong "
           "under pwsh-on-POSIX (measured, see the test's docstring), and spec A10 makes "
           "the native run the evidence")

# The dispatcher's Stop row allows the gate 600s. A rule here is `exit 0` or a
# 3s sleep, so anything near this is a hang, not a slow host.
_LAUNCHER_TIMEOUT = 300

_RECORD = os.path.join(".crew", ".verify-gate.record.json")
_LOCK = os.path.join(".crew", ".verify-gate.lock")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=str(root), check=True, capture_output=True, text=True,
                   stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _gate_repo(tmp_path, rules, name="repo"):
    """A minimal ARMED repo with no active ticket: `.crew/config.json` is what
    `crew_hook.armed` reads, and with no ticket the completion audit does not
    audit, so the only thing that can decide the Stop is the verify gate.

    One untracked `.py` makes `git ls-files --others` report a changed file, so
    the gate reaches its matcher instead of exiting early on an empty set.
    """
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps({}), encoding="utf-8")
    _set_rules(root, rules)
    home = tmp_path / (name + "-home")
    (home / ".claude").mkdir(parents=True)
    return str(root), str(home)


def _set_rules(root, rules):
    with open(os.path.join(str(root), ".crew", "verify.json"), "w", encoding="utf-8") as handle:
        json.dump({"rules": rules, "unmapped": "warn"}, handle)


def _stop_payload(root, session="s-1"):
    return json.dumps({"hook_event_name": "Stop", "session_id": session, "cwd": str(root),
                       "stop_hook_active": False}).encode()


def _stop(root, home, trace):
    return h.run_launcher("ps1", "Stop", _stop_payload(root), root, home,
                          env_extra={"CREW_HOOK_TRACE_FILE": str(trace)},
                          timeout=_LAUNCHER_TIMEOUT)


def _children(trace):
    """The script names the dispatcher recorded, one per child it ran."""
    if not os.path.exists(str(trace)):
        return []
    return [line.split()[1] for line in h.read_text(str(trace)).splitlines() if len(line.split()) > 1]


def _counter_rule(outside, name="runs.txt"):
    """A rule that appends one line per execution, to an ABSOLUTE path
    OUTSIDE the repository.

    A relative `>> runs.txt` does not work: a rule's working directory is the
    gate's, not the repo root, so the file lands somewhere the test never
    looks and the run counts as zero - which reads as "the lock held" and
    would make the lock case pass for the wrong reason.

    Outside the repo, because a marker written INSIDE it changes the tree, the
    fingerprint moves, and the next Stop re-runs the rule for a perfectly
    correct reason - which looks exactly like a record that was not read.
    `test_verify_gate_lock_concurrent.py` sidesteps this by having its smoke
    script resolve the path from `$0`; a rule has no `$0`, so it takes the
    path spelled out.

    `reach: local` is load-bearing too. A `>>` makes the rule "shell syntax in
    an undeclared rule", which Stop reach-EXCLUDES - it exits 0 having run
    nothing, the marker is never written, and a zero count reads as "the lock
    held". Declaring the reach is what makes the rule actually run.
    """
    marker = os.path.join(str(outside), name)
    posix = crew_fixtures.windows_to_posix(marker) if h.WINDOWS else marker
    return marker, {"paths": ["**/*.py"], "reach": "local",
                    "run": [f'printf "ran\\n" >> "{posix}"']}


def _runs(marker):
    if not os.path.exists(marker):
        return []
    with open(marker, encoding="utf-8") as handle:
        return handle.read().split()


def _record_entries(root):
    path = os.path.join(str(root), _RECORD)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# --- the Stop gate through the dispatcher: must block ---------------------------

def test_a_stop_whose_record_does_not_cover_the_tree_blocks_and_runs_the_gate_once(tmp_path):
    """G1, must-block. A changed `.py` with no record entry covering it is the
    "stale or missing record" state: the gate must RUN the rule rather than
    read the absent record as a pass, and the failing rule must block the turn.

    `verify-gate.sh` exactly once is half the assertion. The dispatcher picks
    one flavour per row; a regression that ran both the row and a twin, or ran
    the row twice, would double the whole rule set over one tree and is
    invisible to an exit-code-only test.
    """
    root, home = _gate_repo(tmp_path, [{"paths": ["**/*.py"], "run": ["exit 1"]}])
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _stop(root, home, trace)

    ran = _children(trace)
    assert code == 2, f"stderr: {err}"
    assert ran.count("verify-gate.sh") == 1, ran
    assert "verify-gate.ps1" not in ran, ran


def test_a_stop_that_blocks_does_not_leave_the_lock_behind(tmp_path):
    """A blocked turn is the path that most easily leaks a holder: the gate
    exits non-zero and an early `exit` that skipped the trap would leave the
    lock on disk, silently ungating every later Stop."""
    root, home = _gate_repo(tmp_path, [{"paths": ["**/*.py"], "run": ["exit 1"]}])
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _stop(root, home, trace)

    assert code == 2, err
    assert not os.path.exists(os.path.join(root, _LOCK)), "the blocked gate leaked its lock"


# --- the Stop gate through the dispatcher: must allow ---------------------------

def test_a_stop_whose_rule_passes_exits_zero_and_writes_the_pass_record(tmp_path):
    """G1, must-allow. Exit 0, one `verify-gate.sh` child, and a record ON DISK.

    The record's `rules` map holds what is still OWED - chronic, skipped and
    reach-excluded rules (`verify_record.py:20-24`) - so a turn where the only
    rule passed records `{}`: nothing owed. Both halves matter. A missing file
    is the failure finding 22 in `test_verify_gate_stop_gate_record.py` names:
    a sync that never ran reading as "succeeded" while the markers advance on a
    record nobody wrote. A NON-empty map would mean a passing rule was filed as
    an outstanding obligation.
    """
    root, home = _gate_repo(tmp_path, [{"paths": ["**/*.py"], "run": ["exit 0"]}])
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _stop(root, home, trace)

    ran = _children(trace)
    entries = _record_entries(root)
    assert code == 0, f"stderr: {err}"
    assert ran.count("verify-gate.sh") == 1, ran
    assert entries is not None, f"no record was written; stderr: {err}"
    assert entries.get("rules") == {}, entries


def test_a_second_stop_on_an_unchanged_tree_reads_the_fresh_record_instead_of_rerunning(tmp_path):
    """G1, must-allow, the half an exit code cannot show. The rule appends a
    line per execution. A fresh record covering an unchanged tree means the
    second Stop must not run it again - and must still exit 0 rather than
    treating "nothing to do" as "nothing verified"."""
    root, home = _gate_repo(tmp_path, [])
    marker, rule = _counter_rule(tmp_path)
    _set_rules(root, [rule])
    codes = []
    for index in range(2):
        trace = tmp_path / f"trace-{index}.crew-trace"
        code, _, err = _stop(root, home, trace)
        codes.append((code, err))

    lines = _runs(marker)
    assert [code for code, _ in codes] == [0, 0], codes
    assert len(lines) == 1, f"the rule ran {len(lines)} time(s); the second Stop re-ran a fresh record"


# --- the lock, through two concurrent dispatchers (G2) ---------------------------

def _stop_proc(root, home, trace, session):
    """One Stop EVENT through the launcher, payload fed, stdout/stderr piped.

    The payload goes in and stdin is CLOSED immediately, and the result is
    collected later with `wait()` + `.read()`, never `communicate(input=...)`:
    that call owns stdin itself and raises ValueError on a pipe the caller
    already closed - the trap `test_verify_gate_lock_concurrent.py`'s header
    documents.
    """
    env = rgh.env_for(str(root), str(home))
    if not h.WINDOWS:
        env["OS"] = "Windows_NT"
    env["CREW_HOOK_TRACE_FILE"] = str(trace)
    proc = crew_fixtures.popen_gate(
        h.launcher_argv("ps1", "Stop"), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=str(root), env=env)
    proc.stdin.write(_stop_payload(root, session=session))
    proc.stdin.close()
    return proc


def _wait_for_lock(root, bound_s=180):
    """True once the gate has taken the lock. Polling for the lock is what
    makes the contention DETERMINISTIC rather than a hope about timing: see
    the lock case's docstring for the two hold lengths that were not enough."""
    lock = os.path.join(str(root), _LOCK)
    deadline = time.monotonic() + bound_s
    while time.monotonic() < deadline:
        if os.path.exists(lock):
            return True
        time.sleep(0.2)
    return False


def test_only_one_of_two_concurrent_stop_events_runs_the_gate_and_neither_leaks_the_lock(tmp_path):
    """G2. The rule appends one line per execution and then holds, so a loser
    cannot arrive after the work finished and the lock was already cleaned up.

    The run count alone is NOT enough, and the sabotage run proved it: with
    the lock made per-process (`LOCK=...lock.$$`) this case stayed GREEN,
    because two gates that end up running one after the other leave the
    second one a fresh fingerprint to skip on - one run, for a reason that has
    nothing to do with the lock. So the assertion that makes this a LOCK test
    is the loser's own words: backing off prints "backed off" and "NOTHING WAS
    VERIFIED" on stderr (`test_verify_gate_lock_sh.py:140`, the ambiguity
    fixed in crew 0.19.65). Exactly one of the two Stops must say it. Drop the
    lock and nobody does.

    The second Stop is launched once the first HOLDS the lock, rather than at
    the same instant. Starting both together does not work: each dispatcher
    spends over ten seconds starting pwsh and probing for python before it
    reaches the gate, so the two arrive badly staggered and by how much varies
    with what else is running. At a 3s hold and at a 12s hold the second gate
    arrived after the first had finished; at 40s it contended when the case
    ran alone and did NOT when the whole file ran. A test that is a lock test
    only on a quiet host is not one. Polling for the lock makes the contention
    a fact of the fixture, and both Stops are still live at once, which is what
    the production race is.
    """
    root, home = _gate_repo(tmp_path, [])
    marker, rule = _counter_rule(tmp_path)
    rule["run"] = [rule["run"][0] + " && sleep 40"]
    _set_rules(root, [rule])
    trace = tmp_path / "trace.crew-trace"

    # DISTINCT session ids. Two Stops carrying the same id are one turn to
    # anything upstream of the lock, which would make the race unreachable.
    procs = [_stop_proc(root, home, trace, "s-0")]
    try:
        assert _wait_for_lock(root), (
            "the first Stop never took the lock, so nothing was contended and "
            "this case would have passed without testing the lock at all")
        procs.append(_stop_proc(root, home, trace, "s-1"))
    except BaseException:
        for proc in procs:
            crew_fixtures.kill_process_group(proc)
        raise
    errs = []
    for proc in procs:
        try:
            proc.wait(timeout=_LAUNCHER_TIMEOUT)
        except subprocess.TimeoutExpired:
            crew_fixtures.kill_process_group(proc)
            raise
        errs.append(proc.stderr.read().decode("utf-8", "replace"))

    backed_off = [err for err in errs if "backed off" in err]
    assert len(backed_off) == 1, (
        "exactly one of the two Stops must have found the other's lock and "
        f"backed off; stderr: {errs}")
    assert "NOTHING WAS VERIFIED" in backed_off[0], backed_off[0]

    lines = _runs(marker)
    assert len(lines) == 1, (
        f"the rule ran {len(lines)} time(s); both Stops got past the lock. "
        f"exit codes: {[p.returncode for p in procs]}")
    assert not os.path.exists(os.path.join(root, _LOCK)), "the winner leaked its lock"
    assert all(proc.returncode == 0 for proc in procs), \
        f"a backed-off loser must not fail the turn: {[p.returncode for p in procs]}"


# --- the dispatcher refuses BEFORE running a child ------------------------------

def test_an_armed_stop_with_no_python_exits_2_naming_python_and_runs_no_child(tmp_path):
    """The Windows dispatcher resolves python itself (`crew-hook.ps1:390-399`)
    and fails closed when it cannot. `test_crew_hook_faults.py`'s no-python
    case is `skipif(WINDOWS)` by design - "the no-python POSIX path is not a
    Windows path (B10)" - so this is the only cover for the dispatcher's own
    refusal. An EMPTY PATH is the honest model: nothing named python, python3
    or py is reachable.
    """
    root, home = _gate_repo(tmp_path, [{"paths": ["**/*.py"], "run": ["exit 0"]}])
    trace = tmp_path / "trace.crew-trace"
    empty = tmp_path / "emptybin"
    empty.mkdir()

    code, _, err = h.run_launcher("ps1", "Stop", _stop_payload(root), root, home,
                                  path=str(empty), env_extra={"CREW_HOOK_TRACE_FILE": str(trace)},
                                  timeout=_LAUNCHER_TIMEOUT)

    assert code == 2, f"an armed Stop with no python must fail closed; stderr: {err}"
    assert "python" in err.lower(), err
    assert _children(trace) == [], f"a refusal must not have run a gate: {_children(trace)}"


def test_an_unarmed_stop_with_no_python_exits_0(tmp_path):
    """The other half of fail-closed: it must not turn an ungoverned repo into
    a broken one."""
    root, home = _gate_repo(tmp_path, [{"paths": ["**/*.py"], "run": ["exit 0"]}])
    # The WHOLE `.crew` directory, not just config.json: with no python the
    # launcher answers "armed?" itself, and `Test-CrewArmed`
    # (`crew-hook.ps1:328`) treats the bare directory's presence as governed.
    # Deleting only the config file leaves the repo armed and this case would
    # have asserted the opposite of what it names.
    shutil.rmtree(os.path.join(root, ".crew"))
    trace = tmp_path / "trace.crew-trace"
    empty = tmp_path / "emptybin"
    empty.mkdir()

    code, _, err = h.run_launcher("ps1", "Stop", _stop_payload(root), root, home,
                                  path=str(empty), env_extra={"CREW_HOOK_TRACE_FILE": str(trace)},
                                  timeout=_LAUNCHER_TIMEOUT)

    assert code == 0, f"an unarmed repo must not be refused; stderr: {err}"


# --- the completion audit through the dispatcher (G4) ---------------------------

def _audited_repo(tmp_path):
    """An armed repo with T-1 ready (activated, approved as a user, scope base
    recorded), so the only thing that can decide the Stop is the completion
    audit.

    The fixture's own `.crew/verify.json` is used UNCHANGED. Rewriting it to
    add a passing rule is the obvious move and it is wrong: the file is
    force-added by `build_repo`, so any later edit is a tracked change outside
    T-1's `src/**` Touch, and the completion audit then blocks on the test's
    own fixture - `.crew/verify.json` named as the violation - rather than on
    what the case is about. Committing the edit and re-recording the scope base
    did not clear it either. The map as shipped declares environments and no
    rules, which is enough: the verify gate has nothing to run and exits 0, so
    the audit is still the only thing deciding the Stop.
    """
    return rgh.build_repo(str(tmp_path), True)


def _record_base(root, ticket):
    subprocess.run([sys.executable, os.path.join(h.SCRIPTS, "scope_base.py"),
                    "--root", str(root), "--record", ticket],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)


def test_a_stop_with_a_stale_approval_is_blocked_by_the_completion_audit(tmp_path):
    """G4, must-block. The receipt approved `src/**`; rewriting the spec's
    Touch to `**` after approval makes the receipt stale, which the audit must
    refuse by name. Asserting the MESSAGE, not just exit 2, is what separates
    this from the verify gate blocking for its own reason."""
    root, home = _audited_repo(tmp_path)
    with open(os.path.join(root, "src", "app.py"), "w", encoding="utf-8") as handle:
        handle.write("x = 3\n")
    spec = os.path.join(root, ".work", "tickets", "T-1", "spec.md")
    with open(spec, encoding="utf-8") as handle:
        text = handle.read()
    with open(spec, "w", encoding="utf-8") as handle:
        handle.write(text.replace("`src/**`", "`**`"))
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _stop(root, home, trace)

    ran = _children(trace)
    assert code == 2, f"stderr: {err}"
    assert "not approved" in err, err
    assert ran.count("completion-audit.sh") == 1, ran


def test_a_stop_with_a_clean_receipt_and_an_in_scope_change_is_allowed(tmp_path):
    """G4, must-allow. An in-scope edit under a current receipt passes, and the
    audit still ran - an allow that skipped the audit entirely would pass this
    test's exit code and is what the child count rules out."""
    root, home = _audited_repo(tmp_path)
    with open(os.path.join(root, "src", "app.py"), "w", encoding="utf-8") as handle:
        handle.write("x = 2\n")
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _stop(root, home, trace)

    ran = _children(trace)
    assert code == 0, f"stderr: {err}"
    assert ran.count("completion-audit.sh") == 1, ran


# --- scope-guard and approval-hook through the dispatcher (G4) ------------------

def _edit_payload(root, rel):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                       "tool_input": {"file_path": os.path.join(str(root), rel)},
                       "cwd": str(root), "session_id": "s-1"}).encode()


def _pre_tool_use(root, home, rel, trace):
    return h.run_launcher("ps1", "PreToolUse", _edit_payload(root, rel), root, home,
                          env_extra={"CREW_HOOK_TRACE_FILE": str(trace)},
                          timeout=_LAUNCHER_TIMEOUT)


def test_an_edit_outside_the_touch_list_is_denied_through_the_dispatcher(tmp_path):
    """G4. T-1 is approved for `src/**`; `other/keep.py` is outside it.
    scope-guard refuses by exit code, not a `permissionDecision` payload (see
    notes.md's A10 item 6), so the exit code IS the decision here."""
    root, home = _audited_repo(tmp_path)
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _pre_tool_use(root, home, "other/keep.py", trace)

    ran = _children(trace)
    assert code == 2, f"an out-of-Touch edit must be denied; stderr: {err}"
    assert ran.count("scope-guard.sh") == 1, ran
    assert "scope-guard.ps1" not in ran, ran


def test_an_edit_inside_the_touch_list_is_allowed_through_the_dispatcher(tmp_path):
    """The other half: the same guard, the same dispatcher, one path inside the
    Touch list. Without this the deny case above is satisfied by a guard that
    denies everything."""
    root, home = _audited_repo(tmp_path)
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _pre_tool_use(root, home, "src/app.py", trace)

    ran = _children(trace)
    assert code == 0, f"an in-Touch edit must be allowed; stderr: {err}"
    assert ran.count("scope-guard.sh") == 1, ran


def _approve_prompt(root):
    return json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "/crew:approve T-2",
                       "cwd": str(root), "session_id": "s-1", "prompt_id": "p-1"}).encode()


def test_an_edit_under_an_unapproved_ticket_is_refused_and_a_real_receipt_unblocks_it(tmp_path):
    """G4, the half that runs everywhere. An ACTIVE ticket is not an APPROVED
    one: T-2 exists unapproved in the armed fixture, and activating it makes
    an edit inside its OWN Touch list (`src/**`) refused anyway. The receipt
    the approval hook writes is what changes the decision, and the decision is
    read by scope-guard through the dispatcher both times.

    The approval itself is taken in-process here (`scope_fixtures.approve_as_user`
    -> `approval_hook.handle`, which writes `approved_via: user-prompt`, not a
    forged receipt). Driving the `/crew:approve` prompt through the launcher is
    the next test, which needs a real Windows host - see its reason.
    """
    root, home = _audited_repo(tmp_path)
    crew_ticket.activate(root, "T-2")
    trace = tmp_path / "before.crew-trace"

    before, _, before_err = _pre_tool_use(root, home, "src/app.py", trace)

    assert before == 2, f"an edit under an unapproved ticket must be refused; stderr: {before_err}"
    assert _children(trace).count("scope-guard.sh") == 1, _children(trace)

    scope_fixtures.approve_as_user(pathlib.Path(root), "T-2")
    _record_base(root, "T-2")

    after_trace = tmp_path / "after.crew-trace"
    after, _, after_err = _pre_tool_use(root, home, "src/app.py", after_trace)

    assert after == 0, f"with T-2 approved the same edit must pass; stderr: {after_err}"
    assert _children(after_trace).count("scope-guard.sh") == 1, _children(after_trace)


@native_only
def test_the_approval_hook_records_an_approval_through_the_dispatcher(tmp_path):
    """G4, the approval hook itself. `approval-hook.sh` is a **UserPromptSubmit**
    row (`crew_hook.TABLE:70`), so "through the dispatcher" means the
    `/crew:approve` prompt, not a PreToolUse Edit as spec item 6 words it.

    WHY THIS ONE NEEDS A REAL WINDOWS HOST, measured rather than assumed. The
    rest of this file runs under pwsh on Linux with `OS=Windows_NT`, and did -
    12 of 13 cases passed there, including every other `.sh` child that needs
    python. This one does not, and the model is what breaks, not the hook:

        approval-hook.sh: line 28: /: Is a directory
        crew: /crew:approve was NOT recorded -- approval_hook.py did not run
        to a decision (exit 126).

    `$PY` arrives as `/`, where `crew_py_strict` invoked directly in the same
    WSL (bare, under a minimal env, and with `OS=Windows_NT`) answers
    `/usr/bin/python3` every time. So the python handoff from a pwsh-on-POSIX
    dispatcher to THIS child is wrong in the fake-OS model; on Windows, where
    the dispatcher actually runs, the case passes. Left as a follow-up rather
    than chased here: a harness PR lands alone, and nothing in production runs
    `crew-hook.ps1` on a POSIX host.
    """
    root, home = _audited_repo(tmp_path)
    crew_ticket.activate(root, "T-2")
    trace = tmp_path / "approve.crew-trace"

    code, _, err = h.run_launcher("ps1", "UserPromptSubmit", _approve_prompt(root), root, home,
                                  env_extra={"CREW_HOOK_TRACE_FILE": str(trace)},
                                  timeout=_LAUNCHER_TIMEOUT)

    ran = _children(trace)
    assert code == 0, f"the approval prompt itself must not be refused; stderr: {err}"
    assert ran.count("approval-hook.sh") == 1, ran
    assert "approval-hook.ps1" not in ran, ran
    receipt = os.path.join(crew_ticket.common_dir(root), "crew", "tickets", "T-2", "approval.json")
    assert os.path.exists(receipt), f"the hook ran but recorded nothing; stderr: {err}"
    with open(receipt, encoding="utf-8") as handle:
        assert json.load(handle).get("approved_via") == "user-prompt", receipt
    _record_base(root, "T-2")

    after_trace = tmp_path / "after.crew-trace"
    after, _, after_err = _pre_tool_use(root, home, "src/app.py", after_trace)

    assert after == 0, f"after the approval hook approved T-2 the same edit must pass; stderr: {after_err}"


def test_the_fixture_approves_through_the_real_hook_not_a_hand_written_receipt(tmp_path):
    """A guard on this file's own fixture. notes.md records that a hand-written
    `.crew/active-ticket` gave `decision=(none) exit=0` for BOTH an in-Touch
    and an out-of-Touch edit - the signature of a guard that never saw a
    ticket. If `scope_fixtures.ready` ever stops producing a real
    `user-prompt` receipt, every allow case above becomes vacuous and this is
    the test that says so."""
    root, _ = _audited_repo(tmp_path)

    ticket, source, _ = crew_ticket.resolve_active(root)

    assert (ticket, source) == ("T-1", "active-ticket"), (ticket, source)
    # The receipt lives in the COMMON git dir, not beside the spec
    # (`crew_ticket.py:32`), so a worktree and its main checkout share one
    # approval.
    receipt = os.path.join(crew_ticket.common_dir(root), "crew", "tickets", "T-1", "approval.json")
    assert os.path.exists(receipt), "scope_fixtures.ready wrote no approval receipt"
    with open(receipt, encoding="utf-8") as handle:
        assert json.load(handle).get("approved_via") == "user-prompt", receipt
