"""`_crew_gate_pgid_of`, the proof step the rule-cancellation race depends on.

BLOCK (review): `verify-gate.sh`'s rule loop records `$BASHPID` (the rule's
own dedicated subshell, running under `set -m`) into the shared pgid file
BEFORE that subshell has backgrounded anything -- the only way
`_crew_gate_cleanup_rule_pgid` has a target at all if the gate is signalled
before the rule itself (`RULE_PID`) even exists. The subshell's `set -m`
re-groups it into its OWN process group on SOME hosts (job-control shells
commonly do this to manage a controlling terminal) but not on others; the
old code recorded `$BASHPID` as a process-GROUP id unconditionally, so on a
host where the re-group did NOT happen, `kill -TERM -- "-$BASHPID"` at that
exact window either signalled a process group that does not exist (a silent
no-op -- the rule was never interrupted) or, by coincidence of numbering,
some group this script never started. `_crew_gate_pgid_of` is what the fix
uses to tell the two cases apart before recording anything: verified as its
own leader, `$BASHPID` is recorded as a GROUP; otherwise as a bare PID, so
cleanup signals the ONE process it can prove exists instead of guessing at a
group.

This module tests `_crew_gate_pgid_of` DIRECTLY, extracted out of the real
file with `awk` rather than hand-copied -- a hand copy is exactly the
"BYTE-FOR-BYTE... a hand-copy with no guard" trap `_common.sh` warns about
for `role-write-guard.sh`'s own private python resolver, and the extraction
here means this test always exercises the ACTUAL function text, never a
stale duplicate of it. A full end-to-end reproduction of the race itself
(signalling the gate in the microsecond window between the two `printf`
calls) is not something a test can hit on demand; this is the deterministic
half, and test_verify_gate_stop_gate_record.py's test_34h/test_34i are the
integration half -- both already exercise whichever branch this helper
actually takes on the host they run on (this repo's own CI host does NOT
re-group the subshell, so they exercise the `p` branch on every run; a host
that does re-group would exercise `g`; either way `_crew_gate_pgid_of` is
what decides which, and this module is what proves it decides correctly on
both real shapes).
"""
import os
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

_BASH = shutil.which("bash")

pytestmark = [
    pytest.mark.skipif(_BASH is None, reason="needs bash"),
    pytest.mark.skipif(os.name == "nt" or not os.path.isdir("/proc"),
                        reason="POSIX /proc-based pgid verification only"),
]


def _extract_function():
    """The live `_crew_gate_pgid_of` body, read fresh out of verify-gate.sh
    on every test run -- never a copy that could drift out of sync with
    what the gate actually executes."""
    with open(_SH, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(
        r"^_crew_gate_pgid_of\(\) \{\n(.*?\n)^\}\n", text, re.S | re.M)
    assert match, (
        "_crew_gate_pgid_of not found in verify-gate.sh in the expected "
        "single-line-brace shape - this extraction is string-based and "
        "needs updating if that function's framing ever changes"
    )
    return "_crew_gate_pgid_of() {\n" + match.group(1) + "}\n"


def _run(bash_snippet):
    return subprocess.run(
        [_BASH, "-c", _extract_function() + bash_snippet],
        capture_output=True, text=True, check=False, timeout=30)


def test_reports_its_own_pid_as_its_own_pgid_for_a_setsid_leader():
    """A `setsid`-started process is ALWAYS its own group leader by
    construction (the same POSIX guarantee `popen_gate`'s own comment cites
    for `start_new_session=True`) -- the verified case this function's `g`
    branch exists to confirm."""
    if shutil.which("setsid") is None:
        pytest.skip("needs setsid")
    result = _run(
        "tmp=$(mktemp); "
        "setsid sh -c 'echo $$ > \"$1\"; sleep 5' _ \"$tmp\" & disown; "
        "deadline=$(( $(date +%s) + 5 )); "
        "while [ ! -s \"$tmp\" ] && [ \"$(date +%s)\" -lt \"$deadline\" ]; do "
        "  sleep 0.05; "
        "done; "
        "pid=$(cat \"$tmp\"); "
        "echo \"$(_crew_gate_pgid_of \"$pid\") $pid\"; "
        "kill -TERM -- \"-$pid\" 2>/dev/null; "
        "rm -f \"$tmp\""
    )
    assert result.returncode == 0, result.stderr
    reported, actual_pid = result.stdout.strip().split()
    assert reported == actual_pid, (
        f"a setsid leader's own pgid must read back as its own pid - got "
        f"{reported!r} for pid {actual_pid!r}. stderr: {result.stderr}"
    )


def test_reports_an_ordinary_childs_inherited_pgid_not_its_own_pid():
    """An ORDINARY background child (no `setsid`, no `set -m` re-group)
    shares its parent's process group -- the unverified case this
    function's `p` branch exists to catch, so the caller does not record a
    bare pid as though it were a safe group-kill target."""
    result = _run(
        "sleep 5 & child=$!; "
        "own=$(_crew_gate_pgid_of \"$$\"); "
        "reported=$(_crew_gate_pgid_of \"$child\"); "
        "echo \"$reported $child $own\"; "
        "kill \"$child\" 2>/dev/null"
    )
    assert result.returncode == 0, result.stderr
    reported, child_pid, own_pgid = result.stdout.strip().split()
    assert reported != child_pid, (
        "an ordinary (non-setsid) background child must NOT read back as "
        f"its own pgid - got {reported!r} == its own pid {child_pid!r}. "
        f"stderr: {result.stderr}"
    )
    assert reported == own_pgid, (
        f"an ordinary child's pgid must match the pgid of the shell that "
        f"backgrounded it (both inherited from the same group) - got "
        f"{reported!r} for the child vs {own_pgid!r} for the parent. "
        f"stderr: {result.stderr}"
    )
