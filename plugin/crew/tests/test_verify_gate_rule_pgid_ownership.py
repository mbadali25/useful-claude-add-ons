"""`_crew_gate_pid_is_our_child`, the proof required before a `p`-mode
sidecar entry is ever signalled.

BLOCK (Codex): the rule loop's `_crew_gate_cleanup_rule_pgid` trap reads a
sidecar file naming, in `p` mode, a bare PID -- the rule's own dedicated
subshell, recorded that way exactly when it is NOT its own process-group
leader (see test_verify_gate_rule_pgid_mode.py). A bare PID carries no proof
of identity: once that subshell has exited and been reaped by the rule
loop's own `wait` (test_verify_gate_stop_gate_record.py's own case list does
not cover this because it never needs to -- the race is between the trap
firing and the loop's cleanup of the sidecar, not between rules), its pid
number is free for the OS to hand to a brand-new, entirely unrelated
process. Signalling that number without first checking anything reaches
whatever the OS gave it to next.

The fix is two changes to the shipped script, both exercised here:

  (a) the sidecar's GUARD VARIABLE (`_CREW_GATE_RULE_PGID_FILE`) is now
      cleared as the very next statement after the rule loop captures its
      subshell's exit status -- closing the window between "this subshell's
      pid is free for reuse" and "the trap would refuse to act on it"
      to a single assignment, not a truncate-then-clear pair with other
      statements between them.
  (b) `_crew_gate_pid_is_our_child`, tested directly below, is now the
      required proof BEFORE any bare pid is signalled at all -- TERM,
      the aliveness recheck, and the KILL that follows both go through it.
      It reads the candidate pid's own ppid via `ps` (portable across
      Linux/macOS/Git Bash) and refuses to signal unless that ppid is this
      shell's own `$$`, the one relationship every `p`-mode id is
      guaranteed to have when it is genuinely still the gate's own rule
      subshell. `ps` unavailable, or the pid already gone, reads as
      "cannot tell" and also refuses -- never a guess.

This module tests (b) directly, extracted out of the real file with a
regex rather than hand-copied, for the same reason
test_verify_gate_rule_pgid_mode.py gives: a hand copy can drift from what
the gate actually executes and this extraction cannot.
"""
import os
import re
import shlex
import shutil
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

_BASH = shutil.which("bash")
_PS = shutil.which("ps")

pytestmark = [
    pytest.mark.skipif(_BASH is None, reason="needs bash"),
    pytest.mark.skipif(_PS is None, reason="needs ps"),
    pytest.mark.skipif(os.name == "nt", reason="POSIX process semantics only"),
]

_FUNCTION_NAMES = ("_crew_gate_pid_is_our_child", "_crew_gate_cleanup_rule_pgid")


def _extract_functions(sabotage_remove_ownership_check=False):
    """The live bodies of both functions, read fresh out of verify-gate.sh
    on every test run. `sabotage_remove_ownership_check` strips the
    `_crew_gate_pid_is_our_child "$_crew_id" && ` guard out of every call
    site inside `_crew_gate_cleanup_rule_pgid`, reproducing the pre-fix
    shape (a bare `kill` on whatever pid the sidecar names, no proof
    required) so the suite can confirm it goes red against that shape."""
    with open(_SH, encoding="utf-8") as handle:
        text = handle.read()
    bodies = []
    for name in _FUNCTION_NAMES:
        match = re.search(
            rf"^{re.escape(name)}\(\) \{{\n(.*?\n)^\}}\n", text, re.S | re.M)
        assert match, (
            f"{name} not found in verify-gate.sh in the expected "
            "single-line-brace shape - this extraction is string-based and "
            "needs updating if that function's framing ever changes"
        )
        bodies.append(f"{name}() {{\n" + match.group(1) + "}\n")
    combined = "".join(bodies)
    if sabotage_remove_ownership_check:
        sabotaged = combined.replace(
            '_crew_gate_pid_is_our_child "$_crew_id" && ', "")
        assert sabotaged != combined, (
            "sabotage found nothing to remove - the guard string this test "
            "strips out no longer matches the shipped source"
        )
        combined = sabotaged
    return combined


def _run(bash_snippet, sabotage_remove_ownership_check=False):
    functions = _extract_functions(sabotage_remove_ownership_check)
    return subprocess.run(
        [_BASH, "-c", functions + bash_snippet],
        capture_output=True, text=True, check=False, timeout=30)


def test_cleanup_signals_a_bare_pid_that_really_is_our_child():
    """Must-allow: an ordinary background child of THIS bash process,
    recorded in `p` mode exactly as the real rule loop records its own
    subshell, must still be terminated -- the ownership proof must not
    refuse a legitimate target."""
    result = _run(
        "sleep 30 & child=$!; "
        "tmp=$(mktemp); printf 'p %s\\n' \"$child\" > \"$tmp\"; "
        "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
        "_crew_gate_cleanup_rule_pgid; "
        "sleep 0.4; "
        "if kill -0 \"$child\" 2>/dev/null; then echo ALIVE; else echo GONE; fi; "
        "rm -f \"$tmp\""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "GONE", (
        "cleanup must terminate a bare pid that genuinely is this shell's "
        f"own child - stdout: {result.stdout!r} stderr: {result.stderr}"
    )


def test_cleanup_does_not_signal_a_bare_pid_that_is_not_our_child():
    """Must-refuse: a process this TEST started (its parent is pytest, not
    the bash shell that runs cleanup) stands in for "an unrelated process
    the OS handed a reused pid to" -- the shape the BLOCK finding names.
    Cleanup must not signal it."""
    with subprocess.Popen(["sleep", "30"]) as unrelated:
        try:
            pid = shlex.quote(str(unrelated.pid))
            result = _run(
                f"tmp=$(mktemp); printf 'p %s\\n' {pid} > \"$tmp\"; "
                "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
                "_crew_gate_cleanup_rule_pgid; "
                "rm -f \"$tmp\""
            )
            assert result.returncode == 0, result.stderr
            time.sleep(0.4)
            assert unrelated.poll() is None, (
                "cleanup signalled a bare pid it never forked - "
                f"stderr: {result.stderr}"
            )
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)


def test_sabotage_removing_the_ownership_check_kills_the_unrelated_process():
    """Reintroduce the pre-fix bug (strip the ownership guard out of every
    call site) and confirm the suite goes red exactly the way CLAUDE.md
    requires of a fix to a guard: the same unrelated process from the
    must-refuse case above is now signalled, because nothing checks it is
    ours before `kill` runs."""
    with subprocess.Popen(["sleep", "30"]) as unrelated:
        try:
            pid = shlex.quote(str(unrelated.pid))
            result = _run(
                f"tmp=$(mktemp); printf 'p %s\\n' {pid} > \"$tmp\"; "
                "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
                "_crew_gate_cleanup_rule_pgid; "
                "rm -f \"$tmp\"",
                sabotage_remove_ownership_check=True,
            )
            assert result.returncode == 0, result.stderr
            time.sleep(0.4)
            assert unrelated.poll() is not None, (
                "sabotage did not reproduce the bug - the unrelated process "
                "survived even with the ownership guard removed, so this "
                "test would not have caught the original defect"
            )
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)
