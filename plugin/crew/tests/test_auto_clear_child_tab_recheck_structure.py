"""Structural (no-execution) regression for Get-CrewChildTabRecheck.

`test_auto_clear_review_fixes.py::test_child_rechecks_tab_safety_after_the_
delay_before_typing` drives this function for real, through a live pwsh
process against a real window handle -- but it is `skipif`'d off any host
that is not Windows (System.Windows.Forms/UIAutomation are Windows-only), so
it never runs on Linux CI at all. That left the historical defect it guards
against -- the detached sendkeys child treating every window as safe to type
into once focus matched, with no tab awareness whatsoever -- covered on
exactly one platform.

This test reads the heredoc SOURCE instead of executing it: no pwsh, no
Windows Forms, runs everywhere. It asserts the one structural property that
makes the function's fallthrough safe: the IsWindowsTerminal guard is the
FIRST statement in the function body, so nothing can answer "send"
unconditionally before that guard -- and no reachable path is ambiguous
between the two things that legitimately return "send" (a non-Windows-
Terminal owner, or Get-CrewSendKeysTabDecision's own tab-count == 1 case) and
a bare, always-taken one.

Sabotage (see plugin/crew/tests/sabotage_autocycle.py): prepending an
unconditional `return @{ Decision = "send"; Reason = "" }` ahead of the
IsWindowsTerminal guard reproduces the exact historical bug and turns this
test red -- on Linux, where the execution-based twin above cannot run at all.
"""
import os

import context  # noqa: F401  pylint: disable=unused-import
from test_auto_cycle import _extract_ps1_function

_PS1 = os.path.join(context._ROOT, "hooks", "scripts", "auto-clear.ps1")  # pylint: disable=protected-access


def _ps1_source():
    with open(_PS1, encoding="utf-8") as handle:
        return handle.read()


def _child_heredoc_source():
    """The detached sender is a separate process, built as a literal
    here-string and spawned via a temp file. Get-CrewChildTabRecheck lives
    only inside it (there is no parent-side copy), but slicing it out keeps
    this test reading the same thing the child process actually runs rather
    than the whole file, the way `test_auto_clear_review_fixes.py`'s own
    `_child_heredoc_source` does."""
    source = _ps1_source()
    marker = "$child = @'\n"
    start = source.index(marker) + len(marker)
    end = source.index("\n'@", start)
    return source[start:end]


def test_get_crew_child_tab_recheck_cannot_short_circuit_to_send():
    child_source = _child_heredoc_source()
    func = _extract_ps1_function(child_source, "Get-CrewChildTabRecheck")

    body = func[func.index("{") + 1:].lstrip()
    assert body.startswith('if (-not $IsWindowsTerminal)'), (
        "Get-CrewChildTabRecheck's first statement must be the "
        "IsWindowsTerminal guard -- anything unconditional ahead of it "
        "(an early `return @{ Decision = \"send\" }`, say) would short-"
        "circuit every post-delay recheck regardless of tab state:\n" + func)

    send_returns = func.count('return @{ Decision = "send"; Reason = "" }')
    assert send_returns == 1, (
        "exactly one `return @{ Decision = \"send\"; Reason = \"\" }` is "
        "expected -- the IsWindowsTerminal guard's own fallthrough. A "
        f"second occurrence means the function can answer \"send\" without "
        f"the guard governing it. Found {send_returns}:\n" + func)
