"""`_crew_gate_group_is_ours`, the proof required before a `g`-mode sidecar
entry is ever signalled.

BLOCK (Codex): the rule loop's `_crew_gate_cleanup_rule_pgid` trap reads a
sidecar file naming, in `g` mode, a process-GROUP id -- unlike `p`-mode ids
(see test_verify_gate_rule_pgid_ownership.py), a `g` line was signalled
unconditionally, with no ownership proof at all. A rule's own group can
empty naturally the instant `wait "$RULE_PID"` returns inside its subshell
(every member has exited), which frees that PGID for the OS to hand to a
brand-new, entirely unrelated process -- concretely, anything that calls
`setsid`, which always becomes both session leader AND group leader of a
FRESH session distinct from this gate's own. A stale sidecar entry plus
that reuse means the trap would TERM/KILL a group this gate never started.

The fix: `_crew_gate_group_is_ours`, tested directly below, is now the
required proof before any `g`-mode id is signalled -- TERM, the aliveness
recheck, and the KILL that follows all go through it. It reads the
candidate group leader's session id (`_crew_gate_sid_of`) and refuses to
signal unless that session id equals this shell's own -- every group this
gate ever creates stays in the SAME session (job-control `set -m`
re-groups, never `setsid`), so a `setsid`-created replacement is exactly
the shape this rejects. Either session id unreadable reads as "cannot
tell" and also refuses -- never a guess.
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
_SETSID = shutil.which("setsid")

pytestmark = [
    pytest.mark.skipif(_BASH is None, reason="needs bash"),
    pytest.mark.skipif(_PS is None, reason="needs ps"),
    pytest.mark.skipif(os.name == "nt", reason="POSIX process semantics only"),
]

_FUNCTION_NAMES = (
    "_crew_gate_sid_of",
    "_crew_gate_group_is_ours",
    "_crew_gate_cleanup_rule_pgid",
)


def _extract_functions(sabotage_remove_ownership_check=False):
    """The live bodies of all three functions, read fresh out of
    verify-gate.sh on every test run. `sabotage_remove_ownership_check`
    strips the `_crew_gate_group_is_ours "$_crew_id" && ` guard out of
    every `g`-mode call site inside `_crew_gate_cleanup_rule_pgid`,
    reproducing the pre-fix shape (a bare `kill` on whatever group the
    sidecar names, no proof required) so the suite can confirm it goes red
    against that shape."""
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
            '_crew_gate_group_is_ours "$_crew_id" && ', "")
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


def test_cleanup_signals_a_group_that_really_is_our_own():
    """Must-allow: an ordinary background job of THIS bash process, put in
    its own process group by `set -m` exactly as the real rule loop does,
    must still be terminated -- the ownership proof must not refuse a
    legitimate target."""
    result = _run(
        "set -m; sleep 30 & child=$!; set +m; "
        "tmp=$(mktemp); printf 'g %s\\n' \"$child\" > \"$tmp\"; "
        "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
        "_crew_gate_cleanup_rule_pgid; "
        "sleep 0.4; "
        "if kill -0 \"$child\" 2>/dev/null; then echo ALIVE; else echo GONE; fi; "
        "rm -f \"$tmp\""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "GONE", (
        "cleanup must terminate a group that genuinely belongs to this "
        f"shell's own session - stdout: {result.stdout!r} stderr: {result.stderr}"
    )


@pytest.mark.skipif(_SETSID is None, reason="needs setsid")
def test_cleanup_does_not_signal_an_unrelated_setsid_group():
    """Must-refuse: a `setsid` group stands in for "an unrelated replacement
    group the OS handed a recycled PGID to" -- the shape the BLOCK finding
    names. Cleanup must not signal it."""
    with subprocess.Popen([_SETSID, "sleep", "30"]) as unrelated:
        try:
            pid = shlex.quote(str(unrelated.pid))
            result = _run(
                f"tmp=$(mktemp); printf 'g %s\\n' {pid} > \"$tmp\"; "
                "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
                "_crew_gate_cleanup_rule_pgid; "
                "rm -f \"$tmp\""
            )
            assert result.returncode == 0, result.stderr
            time.sleep(0.4)
            assert unrelated.poll() is None, (
                "cleanup signalled an unrelated setsid group it never "
                f"started - stderr: {result.stderr}"
            )
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)


@pytest.mark.skipif(_SETSID is None, reason="needs setsid")
def test_sabotage_removing_the_group_ownership_check_kills_the_unrelated_group():
    """Reintroduce the pre-fix bug (strip the ownership guard out of every
    `g`-mode call site) and confirm the suite goes red exactly the way
    CLAUDE.md requires of a fix to a guard: the same unrelated setsid group
    from the must-refuse case above is now signalled, because nothing
    checks it is ours before `kill` runs."""
    with subprocess.Popen([_SETSID, "sleep", "30"]) as unrelated:
        try:
            pid = shlex.quote(str(unrelated.pid))
            result = _run(
                f"tmp=$(mktemp); printf 'g %s\\n' {pid} > \"$tmp\"; "
                "_CREW_GATE_RULE_PGID_FILE=\"$tmp\"; "
                "_crew_gate_cleanup_rule_pgid; "
                "rm -f \"$tmp\"",
                sabotage_remove_ownership_check=True,
            )
            assert result.returncode == 0, result.stderr
            time.sleep(0.4)
            assert unrelated.poll() is not None, (
                "sabotage did not reproduce the bug - the unrelated setsid "
                "group survived even with the ownership guard removed, so "
                "this test would not have caught the original defect"
            )
        finally:
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)
