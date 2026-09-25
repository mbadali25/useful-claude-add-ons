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

No test below reaches SendWait. Most are STRUCTURAL (they parse
`_child_heredoc_source()` as text). Two are behavioural but run only a
SLICE of the child under pwsh -- the focus decision, and the inhibit gate
-- cut to end before the SendWait lines, with `GetForegroundWindow()`
replaced by a value the test chooses; each asserts its slice contains no
SendWait call before spawning anything. A behavioural run of the WHOLE
child on a real locked or headless session is not done, because it would
mean genuinely locking this host's session or a run that risks a REAL
SendWait if it went wrong -- which no test run, sabotage included, may
ever do. `test_auto_clear_review_fixes.py::test_child_binds_and_runs_
under_dash_file_on_pwsh7` (and its 5.1 twin) already prove the FIXED child
still runs correctly end-to-end under a real `-File` invocation, safely,
because that invocation now sets `CREW_AUTOCLEAR_INHIBIT=1` -- see this
file's own `test_the_real_dash_file_binding_harness_sets_the_inhibit_
backstop`, which pins that the harness keeps doing so.

Enumeration of every SendWait call site reachable from any test (checked
mechanically, not asserted in prose -- see
`test_only_two_sendwait_call_sites_exist_and_both_are_inside_the_gated_child`,
which walks every file `git ls-files` reports): a SendWait CALL (matched
by `_SENDWAIT_CALL` below, any case) appears exactly twice in the
whole repository, both at `auto-clear.ps1` inside the `$child` heredoc
(the two lines just above `'@`). The only other matches are two text
needles that structural tests hand to `str.index()` on the child's source
-- one in this file, one in `test_auto_clear_review_fixes.py` -- which are
allow-listed by exact count. The only test that can reach either real
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
import re
import shutil
import subprocess
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PS1 = _ROOT + "/hooks/scripts/auto-clear.ps1"
_PS1_REL = "plugin/crew/hooks/scripts/auto-clear.ps1"

# A keystroke-sending CALL, case-insensitive because PowerShell is:
#  - SendWait or Send after a PowerShell static-member double colon (the
#    SendKeys type literal, or a variable holding it), the member name bare
#    or in single or double quotes, then an opening paren;
#  - SendWait or SendKeys (the WScript.Shell COM method) after a `.`, bare
#    or quoted, then an opening paren.
# A bare `.send(` is deliberately NOT matched: it is every socket, generator
# and HTTP client in the repo. Prose that merely names SendWait ("just
# before SendWait") and identifiers like `..._and_sendwait()` do not match.
# Comments in this file describe the call forms in words rather than
# spelling them, because this file is scanned too; the pattern's own source
# text does not match it (a `(?:` or `|` sits where a call has `::` or `(`).
_SENDWAIT_CALL = re.compile(
    r"(?:::\s*(['\"]?)(?:SendWait|Send)\1|\.\s*(['\"]?)(?:SendWait|SendKeys)\2)\s*\(",
    re.IGNORECASE)

# A tracked file whose BOM names an encoding its bytes then fail to decode as
# (see `_decoded_texts`) is skipped as a binary -- unless its extension says
# it is a script, in which case it is reported as unreadable and the
# enumeration fails: a script this scan cannot read is an unknown, not a
# file with no SendWait in it.
_SCRIPT_EXTENSIONS = frozenset(
    {".ps1", ".psm1", ".psd1", ".sh", ".py", ".cmd", ".bat"})

# Matches that are not call sites: text needles a structural test passes to
# `str.index()` against the child heredoc's source. Pinned by exact count, so
# a real call added to either file (a `pwsh -Command` string, say) still goes
# red. Any file not named here, or in `_PS1_REL`, must have zero matches.
_TEXT_NEEDLE_ALLOWLIST = {
    "plugin/crew/tests/test_auto_clear_review_fixes.py": 1,
    "plugin/crew/tests/test_sendkeys_structural_gate.py": 1,
}


def _repo_toplevel():
    return subprocess.run(
        ["git", "-C", _ROOT, "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True).stdout.strip()


_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"),
)


def _decoded_texts(raw):
    """The texts `raw` is scanned as; [] only when a BOM names an encoding
    the bytes then fail to decode as.

    A UTF-16/UTF-32 BOM (Windows PowerShell 5.1's `Out-File` / `>` default
    is UTF-16LE with a BOM) is decoded as it says. Otherwise UTF-8, and if
    that decodes without a NUL it is the one text. If UTF-8 fails, or yields
    NULs -- BOM-less UTF-16LE of ASCII is VALID UTF-8, one NUL per
    character, so a clean UTF-8 decode is not proof the file was read as
    written -- both UTF-16 byte orders are tried, and Latin-1 is added last:
    it decodes any bytes and keeps every ASCII byte as itself, so a
    BOM-less ANSI (cp1252) script, which is what 5.1 reads a BOM-less file
    as, is still scanned rather than skipped."""
    for bom, codec in _BOMS:
        if raw.startswith(bom):
            try:
                return [raw.decode(codec)]
            except UnicodeDecodeError:
                return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and "\x00" not in text:
        return [text]
    texts = [] if text is None else [text]
    for codec in ("utf-16-le", "utf-16-be"):
        try:
            texts.append(raw.decode(codec))
        except UnicodeDecodeError:
            pass
    texts.append(raw.decode("latin-1"))
    return texts


def _tracked_sendwait_matches():
    """Every tracked file's SendWait-call offsets, read from the working
    tree. Returns (matches_by_path, files_scanned, unreadable_scripts). A
    path git lists but the working tree lacks (a sparse or mid-edit
    checkout) is skipped: it cannot hold a call. A file `_decoded_texts`
    cannot read is skipped as a binary unless its extension is in
    `_SCRIPT_EXTENSIONS`, where it goes into `unreadable_scripts` instead."""
    top = _repo_toplevel()
    listed = subprocess.run(
        ["git", "-C", top, "ls-files", "-z"],
        check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    matches, scanned, unreadable = {}, 0, []
    for rel in filter(None, listed):
        try:
            with open(os.path.join(top, rel), "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        texts = _decoded_texts(raw)
        if not texts:
            if os.path.splitext(rel)[1].lower() in _SCRIPT_EXTENSIONS:
                unreadable.append(rel)
            continue
        scanned += 1
        found = max(([m.start() for m in _SENDWAIT_CALL.finditer(text)]
                     for text in texts), key=len)
        if found:
            matches[rel] = found
    return matches, scanned, unreadable


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
    """Enumeration, checked rather than merely asserted in prose: every file
    `git ls-files` reports is scanned, the whole repo has exactly two
    SendWait calls, and both are inside the child heredoc -- so gating the
    child heredoc's own last statement before them is a COMPLETE fix, not
    one that leaves a sibling call site ungated. A scan that read nothing,
    or never read auto-clear.ps1, fails rather than passing vacuously."""
    matches, scanned, unreadable = _tracked_sendwait_matches()
    assert scanned > 0, (
        "git ls-files yielded no readable tracked file -- the repo-wide "
        "SendWait scan read nothing, so its silence would prove nothing")
    assert not unreadable, (
        f"tracked scripts whose BOM names an encoding they fail to decode as: "
        f"{unreadable} -- an unreadable script is an unknown, not a file "
        "without a SendWait call")

    strays = {
        path: len(offsets) for path, offsets in matches.items()
        if path != _PS1_REL
        and len(offsets) != _TEXT_NEEDLE_ALLOWLIST.get(path, 0)}
    missing = {
        path: expected for path, expected in _TEXT_NEEDLE_ALLOWLIST.items()
        if path not in matches}
    assert not strays and not missing, (
        f"SendWait call pattern outside auto-clear.ps1's gated child "
        f"(scanned {scanned} tracked files): unexpected {strays}, "
        f"allow-listed needle gone {missing} -- a new call site must be "
        "gated and this enumeration re-verified; a moved needle must have "
        "its allowlist count updated")

    source = _ps1_source()
    marker = "$child = @'\n"
    start = source.index(marker) + len(marker)
    end = source.index("\n'@", start)
    all_positions = matches.get(_PS1_REL, [])

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


def test_the_real_dash_file_binding_harness_sets_the_inhibit_backstop(tmp_path):
    """Pins that `test_auto_clear_review_fixes.py`'s harness for the ONLY
    test path that spawns the real child (the `-File` binding tests) hands
    CREW_AUTOCLEAR_INHIBIT to the process it spawns -- a deterministic
    backstop so those tests cannot reach SendWait regardless of this host's
    foreground-window/session-lock state.

    Behavioural, not textual: the harness runs with its `subprocess`
    replaced by a recorder, so nothing is spawned, and the test asserts on
    the keyword arguments the child spawn was actually called with. A
    harness that still builds the env but drops `env=env` from the spawn,
    or spawns with an env lacking the variable, goes red here."""
    import test_auto_clear_review_fixes as harness  # pylint: disable=import-outside-toplevel

    calls = []

    def recorder(args, **kwargs):
        calls.append((args, kwargs))
        stdout = '["-File", "child.ps1"]' if isinstance(args, list) else ""
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    fake = types.SimpleNamespace(run=recorder, CompletedProcess=subprocess.CompletedProcess)
    original = harness.subprocess
    harness.subprocess = fake
    try:
        harness._run_real_dash_file_binding(  # pylint: disable=protected-access
            "engine-not-spawned", tmp_path, True)
    finally:
        harness.subprocess = original

    spawns = [kwargs for args, kwargs in calls if isinstance(args, str)]
    assert len(spawns) == 1, f"expected one child spawn, recorded: {calls}"
    assert (spawns[0].get("env") or {}).get("CREW_AUTOCLEAR_INHIBIT"), (
        "_run_real_dash_file_binding spawned the child without "
        f"CREW_AUTOCLEAR_INHIBIT in the env it passed: {spawns[0]!r} -- this "
        "is the ONLY test path that reaches a real SendWait call site, and "
        "it must always be deterministically inhibited")


_PWSH = shutil.which("pwsh") or shutil.which("powershell")
_FG_CALL = "[CrewAC.Win]::GetForegroundWindow().ToInt64()"
_SLICE_PRELUDE = (
    "function Write-CrewChildNote { param($m) Write-Output \"NOTE: $m\" }\n"
    "[long]$Hwnd = [long]$env:CREW_TEST_HWND\n"
    "$Delay = 0\n"
    "$Text = '/clear'\n"
)


def _run_child_slice(tmp_path, body, env_overrides):
    """Runs `body` -- a slice of the child heredoc that must end before any
    SendWait -- under pwsh with a stub Write-CrewChildNote, then prints
    PROCEEDED if the slice fell through. Returns stdout."""
    code = "\n".join(line for line in body.splitlines()
                     if not line.lstrip().startswith("#"))
    forbidden = [word for word in ("windows.forms", "add-type", "wscript.shell")
                 if word in code.lower()]
    assert not _SENDWAIT_CALL.search(code) and not forbidden, (
        f"refusing to run a child slice that could reach a keystroke "
        f"({forbidden}): {body!r}")
    script = tmp_path / "slice.ps1"
    script.write_text(_SLICE_PRELUDE + body + "\nWrite-Output 'PROCEEDED'\n",
                      encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CREW_AUTOCLEAR_INHIBIT"}
    env.update(env_overrides)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)],
        env=env, capture_output=True, text=True, check=False, timeout=60)
    assert result.returncode == 0, f"slice failed: {result.stderr}"
    return result.stdout


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh or powershell to run the child slice")
@pytest.mark.parametrize("foreground,hwnd,declines", [
    (0, 0, True),     # locked/headless session, unresolved target: the bug
    (0, 42, True),    # locked/headless session, resolved target
    (7, 42, True),    # another window has focus
    (42, 42, False),  # the target still has focus: the only send case
])
def test_the_focus_decision_declines_unless_the_target_is_the_nonzero_foreground(
        tmp_path, foreground, hwnd, declines):
    """The DECISION, not text proximity: everything from the `$fg =`
    assignment up to the tab recheck is run under pwsh with
    GetForegroundWindow() replaced by `foreground`, and must decline
    ("lost focus", no fall-through) in exactly the three cases above. An
    `-or` turned into `-and`, or the `$fg -eq 0` test split into its own
    `if` with an empty body, both change which rows decline."""
    child = _child_heredoc_source()
    start = child.index("$fg = ")
    end = child.index("$recheck = Get-CrewChildTabRecheck", start)
    body = child[start:end]
    assert body.count(_FG_CALL) == 1, body
    body = body.replace(_FG_CALL, "[long]$env:CREW_TEST_FG")

    out = _run_child_slice(tmp_path, body, {
        "CREW_TEST_FG": str(foreground), "CREW_TEST_HWND": str(hwnd)})

    assert (("lost focus" in out and "PROCEEDED" not in out) if declines
            else (out.strip() == "PROCEEDED")), (
        f"fg={foreground} hwnd={hwnd}: expected "
        f"{'a decline' if declines else 'a fall-through'}, got {out!r}")


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh or powershell to run the child slice")
@pytest.mark.parametrize("inhibit,declines", [("1", True), (None, False)])
def test_the_inhibit_gate_exits_before_the_send_when_set(tmp_path, inhibit, declines):
    """Everything from the child's `if ($env:CREW_AUTOCLEAR_INHIBIT)` up to
    the first SendWait line, run under pwsh: with the variable set it must
    log the decline AND stop there; unset, it must fall through (so the
    gate is conditional, not an unconditional exit that would also hide a
    broken condition). An exit moved out of the block -- or made
    unreachable after it -- logs "declined" and then proceeds, and goes red."""
    child = _child_heredoc_source()
    start = child.index("if ($env:CREW_AUTOCLEAR_INHIBIT)")
    first_call = _SENDWAIT_CALL.search(child, start)
    assert first_call, "no SendWait call after the inhibit gate"
    body = child[start:child.rindex("\n", start, first_call.start())]

    out = _run_child_slice(
        tmp_path, body, {} if inhibit is None else {"CREW_AUTOCLEAR_INHIBIT": inhibit})

    assert (("CREW_AUTOCLEAR_INHIBIT is set" in out and "PROCEEDED" not in out)
            if declines else (out.strip() == "PROCEEDED")), (
        f"CREW_AUTOCLEAR_INHIBIT={inhibit!r}: expected "
        f"{'a decline that stops' if declines else 'a fall-through'}, got {out!r}")
