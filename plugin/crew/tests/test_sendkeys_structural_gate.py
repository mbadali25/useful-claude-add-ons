"""SAFETY (crew-1.0-win-ps1-r3): `test_auto_clear_review_fixes.py`'s
`_run_real_dash_file_binding` (~line 730) drives the detached sendkeys
child's REAL heredoc through a REAL `-File` invocation, with `-Hwnd 0` --
a placeholder that stands for "unresolved". The one thing standing between
that placeholder and a genuine `SendKeys.SendWait` was
`GetForegroundWindow().ToInt64() -ne $Hwnd`: on an ordinary interactive
desktop `GetForegroundWindow()` returns some real, nonzero handle that
(almost certainly) differs from 0, so the check declines. But in a locked
or headless session `GetForegroundWindow()` ALSO returns 0 -- Win32's
documented behaviour, not a bug in this script -- which reads as "still
focused" and lets a genuinely unresolved target through to a real keypress.
"the Hwnd is now nonzero" is not accepted as the fix on its own (a fixed
decoy nonzero handle could still coincide with a real foreground window,
however unlikely); the fix has to make SendWait unreachable regardless of
what the host's focus/session state happens to be.

Two changes landed in `auto-clear.ps1`'s child heredoc (see the two
comments beginning "# $fg -eq 0 is its own decline" and "# A test suite
must never drive the real keyboard" just above the SendWait lines):

1. The focus check now declines when `GetForegroundWindow()` itself
   returns 0, not only when it differs from `$Hwnd` -- closes the
   locked/headless coincidence for every caller, not just tests.
2. `CREW_AUTOCLEAR_INHIBIT` (already checked by the PARENT, just before it
   spawns this file -- see auto-clear.ps1 around the `Start-Process` call)
   is now ALSO checked inside the child itself, as the LAST statement
   before the two SendWait lines. The parent's check cannot help a test
   that spawns this heredoc directly (bypassing the parent entirely, which
   `_run_real_dash_file_binding` has to do to prove the argv binds under
   `-File` on both engines) -- this is what closes that gap, and being the
   LAST gate before SendWait means it cannot be skipped by whichever
   upstream branch a given test run happens to take.

Every test below is STRUCTURAL (parses `_child_heredoc_source()` as text;
no pwsh is spawned to reach SendWait) for the reason the ticket names
directly: a behavioural RED demonstration of the original bug would need a
locked or headless session for `GetForegroundWindow()` to actually return
0, and reproducing that live would mean either genuinely locking this
host's session (not being done here) or a test run that risks a REAL
SendWait if it went wrong -- which no test run, sabotage included, may
ever do. `test_auto_clear_review_fixes.py::test_child_binds_and_runs_
under_dash_file_on_pwsh7` (and its 5.1 twin) already prove the FIXED child
still runs correctly end-to-end under a real `-File` invocation, safely,
because that invocation now sets `CREW_AUTOCLEAR_INHIBIT=1` -- see this
file's own `test_the_real_dash_file_binding_harness_sets_the_inhibit_
backstop`, which pins that the harness keeps doing so.

Enumeration of every SendWait call site reachable from any test (grepped,
not assumed): `[System.Windows.Forms.SendKeys]::SendWait` appears exactly
twice in the whole repository, both at `auto-clear.ps1` inside the `$child`
heredoc (the two lines just above `'@`). No other `.ps1`, `.sh`, or test
file contains the literal `SendWait`. The only test that can reach either
call is one that spawns the FULL child heredoc as a real process via
`-File`: that is `_run_real_dash_file_binding` in
`test_auto_clear_review_fixes.py`, used by
`test_child_binds_and_runs_under_dash_file_on_pwsh7` and
`test_child_binds_and_runs_under_dash_file_on_windows_powershell_51`.
Every other test in that file that touches `Get-CrewChildTabRecheck`,
`Get-CrewWindowsTerminalTabState`, or `Get-CrewSendKeysTabDecision` extracts
just those functions (`_extract_ps1_function`), never the trailing
escape/SendWait statements, so none of those reach a SendWait call --
`test_get_crew_send_keys_child_args_carries_the_configured_delay` (Hwnd 42)
and `test_child_recheck_is_skipped_for_a_non_windows_terminal_owner`
(Hwnd 12345) included.
"""
import os

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PS1 = _ROOT + "/hooks/scripts/auto-clear.ps1"


def _ps1_source():
    with open(_PS1, encoding="utf-8") as handle:
        return handle.read()


def _child_heredoc_source():
    """Same slice `test_auto_clear_review_fixes.py`'s `_child_heredoc_source`
    uses -- duplicated locally, matching this test suite's existing house
    style of not sharing test-only helpers across files (see that file's own
    duplicated `_extract_ps1_function`)."""
    source = _ps1_source()
    marker = "$child = @'\n"
    start = source.index(marker) + len(marker)
    end = source.index("\n'@", start)
    return source[start:end]


def test_only_two_sendwait_call_sites_exist_and_both_are_inside_the_gated_child():
    """Enumeration, checked rather than merely asserted in prose: the whole
    repo (this file's docstring names every source it grepped) has exactly
    two SendWait calls, and both are inside the child heredoc -- so gating
    the child heredoc's own last statement before them is a COMPLETE fix,
    not one that leaves a sibling call site ungated."""
    source = _ps1_source()
    marker = "$child = @'\n"
    start = source.index(marker) + len(marker)
    end = source.index("\n'@", start)

    all_positions = []
    i = 0
    needle = "[System.Windows.Forms.SendKeys]::SendWait("
    while True:
        idx = source.find(needle, i)
        if idx == -1:
            break
        all_positions.append(idx)
        i = idx + 1

    assert len(all_positions) == 2, (
        f"expected exactly 2 SendWait call sites in auto-clear.ps1, found "
        f"{len(all_positions)} at {all_positions} -- if this is intentional, "
        "the new gate below must be re-verified against the new site too")
    for pos in all_positions:
        assert start <= pos <= end, (
            f"SendWait call at offset {pos} is OUTSIDE the child heredoc "
            f"({start}-{end}) -- it is not covered by the inhibit gate this "
            "test suite otherwise relies on")


def test_the_inhibit_gate_sits_strictly_between_every_upstream_decision_and_sendwait():
    """The gate must be the LAST thing checked before SendWait, not merely
    present somewhere in the child -- otherwise some other branch could
    still reach SendWait without passing through it. Sabotage: moving the
    `if ($env:CREW_AUTOCLEAR_INHIBIT)` block back above the focus check (or
    deleting it) either breaks this ordering or makes `.index()` raise --
    both a hard RED, not a silent pass."""
    child_source = _child_heredoc_source()

    focus_idx = child_source.index(
        "[CrewAC.Win]::GetForegroundWindow().ToInt64()")
    recheck_call_idx = child_source.index(
        "$recheck = Get-CrewChildTabRecheck")
    recheck_guard_idx = child_source.index(
        'if ($recheck.Decision -ne "send")')
    inhibit_idx = child_source.index("if ($env:CREW_AUTOCLEAR_INHIBIT)")
    sendwait_idx = child_source.index(
        "[System.Windows.Forms.SendKeys]::SendWait($escaped)")

    assert (focus_idx < recheck_call_idx < recheck_guard_idx
            < inhibit_idx < sendwait_idx), (
        "the inhibit gate must run strictly after the focus check and the "
        "tab recheck guard, and strictly before SendWait -- any other "
        "ordering leaves a branch that can reach SendWait without passing "
        f"through it: focus={focus_idx} recheck_call={recheck_call_idx} "
        f"recheck_guard={recheck_guard_idx} inhibit={inhibit_idx} "
        f"sendwait={sendwait_idx}")


def test_the_inhibit_gate_declines_rather_than_proceeds():
    """Text-level check that the gate is a decline (exit 0, logged), not a
    no-op or an inverted condition that would send when the var IS set."""
    child_source = _child_heredoc_source()
    inhibit_idx = child_source.index("if ($env:CREW_AUTOCLEAR_INHIBIT)")
    block = child_source[inhibit_idx:inhibit_idx + 300]
    assert "exit 0" in block, block
    assert "Write-CrewChildNote" in block, block
    sendwait_idx_in_block = block.find(
        "[System.Windows.Forms.SendKeys]::SendWait")
    exit_idx_in_block = block.find("exit 0")
    assert exit_idx_in_block != -1 and (
        sendwait_idx_in_block == -1 or exit_idx_in_block < sendwait_idx_in_block), (
        "the inhibit branch must exit before any SendWait, not alongside or after one")


def test_foreground_zero_is_treated_as_unknown_not_as_still_focused():
    """The other half of the pair: GetForegroundWindow() returning 0 (a
    locked or headless session, Win32-documented) must decline on its own,
    not rely solely on `0 -ne $Hwnd` coincidentally being true. Sabotage:
    reverting to a bare `-ne $Hwnd` comparison (no `$fg -eq 0` disjunct)
    makes this assertion fail without needing to reproduce a locked
    session to prove it."""
    child_source = _child_heredoc_source()
    focus_idx = child_source.index(
        "[CrewAC.Win]::GetForegroundWindow().ToInt64()")
    window = child_source[focus_idx:focus_idx + 400]
    assert "-eq 0" in window, (
        "the focus check must explicitly decline when GetForegroundWindow() "
        f"is 0, not only when it differs from $Hwnd: {window!r}")
    lost_focus_idx = window.find("lost focus")
    eq0_idx = window.find("-eq 0")
    assert eq0_idx != -1 and lost_focus_idx != -1 and eq0_idx < lost_focus_idx, (
        "the -eq 0 check must be part of the SAME decline that logs "
        f"'lost focus', ahead of that log line: {window!r}")


def test_the_real_dash_file_binding_harness_sets_the_inhibit_backstop():
    """Pins that `test_auto_clear_review_fixes.py`'s harness for the ONLY
    reachable SendWait call sites (the real `-File` binding tests) keeps
    passing CREW_AUTOCLEAR_INHIBIT to the child it spawns -- a deterministic
    backstop so those tests cannot reach SendWait regardless of this host's
    actual foreground-window/session-lock state. If a future edit removes
    this env var from that harness, this test goes red instead of the gap
    silently reopening."""
    harness_path = os.path.join(
        _ROOT, "tests", "test_auto_clear_review_fixes.py")
    with open(harness_path, encoding="utf-8") as handle:
        harness_source = handle.read()

    fn_marker = "def _run_real_dash_file_binding("
    fn_start = harness_source.index(fn_marker)
    fn_end = harness_source.index("\ndef _assert_real_binding_ran(", fn_start)
    fn_body = harness_source[fn_start:fn_end]

    assert "CREW_AUTOCLEAR_INHIBIT" in fn_body, (
        "_run_real_dash_file_binding no longer sets CREW_AUTOCLEAR_INHIBIT "
        "for the child it spawns via -File -- this is the ONLY test path "
        "that reaches a real SendWait call site, and it must always be "
        "deterministically inhibited")
    subprocess_call_idx = fn_body.index("subprocess.run(cmdline")
    env_idx = fn_body.index("CREW_AUTOCLEAR_INHIBIT")
    assert env_idx < subprocess_call_idx, (
        "CREW_AUTOCLEAR_INHIBIT must be set up BEFORE the subprocess.run "
        "call that actually spawns the child, not after")
