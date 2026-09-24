"""Regression tests for three defects a review pass (gpt-5.6-sol, on the
range 485a1b08..3f347d52) found in the auto-clear/context-watch pair:

1. `auto-clear.ps1` (~line 582): a failure to determine the process that
   owns the `sendkeys` target window was swallowed by an empty `catch {}`,
   leaving `$ownerProcessName` as `""` -- which is not `"WindowsTerminal"`,
   so the check read that as PROOF the window is safe and let `sendkeys`
   proceed against an unknown safety predicate. Unknown must decline.
2. `auto-clear.ps1` (~line 691): `Start-Process -ArgumentList` joins its
   array into ONE command-line string with plain spaces, not per-element
   quoting, so a `-Root` (or `-Text`) value containing a space silently
   splits into two argv entries in the detached sender's own parsed
   arguments. Tested at the string level (this suite runs on Linux; the
   quoting has to be correct for the ACTUAL Win32 argv-splitting algorithm,
   not merely "looks quoted"), by round-tripping through a reference
   implementation of that same algorithm.
3. `context-watch.sh` (~line 103): a `mktemp` failure used to redirect
   `auto-clear.sh`'s stdout -- the ONE real path that carries the `notify`
   systemMessage -- to `/dev/null`, and by the time that redirection ran,
   `auto-clear.sh` had already claimed the one-per-session SENT_MARKER, so
   the message was lost and a retry would refuse before printing anything
   again. Fixed by removing the mktemp dependency (and its failure mode)
   entirely.
"""
import json
import os
import shutil
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_PS1 = _ROOT + "/hooks/scripts/auto-clear.ps1"
_WATCH_SH = _ROOT + "/hooks/scripts/context-watch.sh"
_BASH = crew_fixtures.resolve_bash()
_PWSH_ANY = shutil.which("pwsh")


# ============================================================================
# FIX 1 -- an unresolvable window owner must decline sendkeys, not proceed
# ============================================================================


def _windows_stub(tmp_path, windows):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(windows), encoding="utf-8")
    return {"CREW_AUTOCLEAR_WINDOW_STUB": str(path)}


def _ps1_repo(tmp_path, method="sendkeys", window_title="Claude"):
    session = "sess-fix1"
    cfg = {"context": {"warnAt": 0.8, "handoffPath": ".work/HANDOFF.md"}}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    (crew / "config.json").write_text(json.dumps({"context": {"autoClear": {
        "enabled": True, "method": method, "windowTitle": window_title}}}), encoding="utf-8")
    (root / ".crew" / (".handoff-requested-" + session)).write_text(json.dumps({
        "session_id": session, "requested_at": time.time() - 30,
        "trusted": True, "why": "measured"}), encoding="utf-8")
    handoff = root / ".work" / "HANDOFF.md"
    handoff.write_text(
        "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
        "## Done\n- a thing\n\n## Next action\nDo the next thing.\n", encoding="utf-8")
    os.utime(handoff, (time.time() + 5, time.time() + 5))
    return root, session


def _run_ps1(root, session, env_extra, *extra_args):
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    env.update(env_extra)
    return subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-File", _PS1,
         "-Root", str(root), "-Session", session, *extra_args],
        cwd=str(root), env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False)


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_sendkeys_declines_when_the_window_owner_cannot_be_determined(tmp_path):
    """A window owned by a pid that no longer exists (or cannot be queried)
    is exactly as unsafe as one confirmed owned by Windows Terminal -- an
    unknown owner must decline and fall back to notify, never proceed on
    the assumption that "could not tell" means "safe". `999999` is not a
    real pid on any host this suite runs on; `Get-Process -Id 999999` is
    proved to throw `Cannot find a process with the process identifier
    999999` at the top of this test, so the case is genuine, not assumed."""
    proof = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-Command",
         "try { Get-Process -Id 999999 -ErrorAction Stop; 'FOUND' } "
         "catch { 'THREW' }"],
        capture_output=True, text=True, check=False)
    assert proof.stdout.strip() == "THREW", (
        "pid 999999 unexpectedly resolved to a real process on this host - "
        "pick a different unresolvable pid for this test")

    root, session = _ps1_repo(tmp_path)
    env = _windows_stub(tmp_path, [{"id": 1, "pid": 999999, "title": "Claude - a tab"}])

    dry = _run_ps1(root, session, env, "-DryRun")
    result = _run_ps1(root, session, env)

    assert "would decline sendkeys" in dry.stdout, dry.stdout + dry.stderr
    assert "cannot determine the process" in dry.stdout, dry.stdout
    assert "would send" not in dry.stdout, dry.stdout
    assert result.returncode == 0
    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "declined sendkeys" in log, log
    assert "cannot determine the process" in log, log
    assert "sent notify instead" in log, log
    payload = json.loads(result.stdout)
    assert "safe to run" in payload["systemMessage"]
    assert "cleared" not in payload["systemMessage"]


# ============================================================================
# FIX 2 -- Start-Process argv quoting (string-level: no real spawn needed)
# ============================================================================


def _extract_ps1_function(source, name):
    """Pulls one `function <name> { ... }` block out of the source by brace
    balance, so the test can drive JUST that helper through `pwsh -Command`
    without running the rest of auto-clear.ps1 (which needs a real Windows
    session to get anywhere near this function)."""
    marker = f"function {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    i = brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces extracting {name}")


def _win_argv_split(cmdline):
    """Reference implementation of the MS C runtime / CommandLineToArgvW
    argv-splitting algorithm -- the SAME algorithm every native Windows
    child process (pwsh, a .NET Main(string[])) uses to split its OWN
    command line back apart. Used ONLY to verify ConvertTo-CrewWin32Arg's
    quoting round-trips; verified below against the four worked examples
    from Microsoft's own "Parsing C++ Command-Line Arguments" docs before
    it is trusted for anything else."""
    args = []
    i, n = 0, len(cmdline)
    while i < n and cmdline[i] in " \t":
        i += 1
    while i < n:
        cur = []
        in_quotes = False
        while i < n and (in_quotes or cmdline[i] not in " \t"):
            if cmdline[i] == "\\":
                j = i
                while j < n and cmdline[j] == "\\":
                    j += 1
                num = j - i
                if j < n and cmdline[j] == '"':
                    cur.append("\\" * (num // 2))
                    if num % 2 == 1:
                        cur.append('"')
                        i = j + 1
                    else:
                        in_quotes = not in_quotes
                        i = j + 1
                else:
                    cur.append("\\" * num)
                    i = j
            elif cmdline[i] == '"':
                in_quotes = not in_quotes
                i += 1
            else:
                cur.append(cmdline[i])
                i += 1
        args.append("".join(cur))
        while i < n and cmdline[i] in " \t":
            i += 1
    return args


def test_the_reference_argv_parser_matches_microsofts_own_worked_examples():
    """Sanity check on the checker, not the product: this parser is only
    trustworthy for the round-trip test below if it agrees with Microsoft's
    own four worked examples first."""
    cases = [
        ('"abc" d e', ["abc", "d", "e"]),
        ('a\\\\b d"e f"g h', ["a\\\\b", "de fg", "h"]),
        ('a\\\\\\"b c d', ['a\\"b', "c", "d"]),
        ('a\\\\\\\\"b c" d e', ["a\\\\b c", "d", "e"]),
    ]
    for cmdline, expected in cases:
        assert _win_argv_split(cmdline) == expected, cmdline


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
@pytest.mark.parametrize("value", [
    "plain",
    "/clear",
    "C:/Users/a b/repo",                 # a -Root with a space (the reported bug)
    "C:/Repos/a project/child",
    "has \"a quote\" inside",
    "trailing\\backslash\\",
    "trailing\\\\before quote\\",
    "",
    "-NoProfile",                          # a flag-shaped value, must still round-trip
], ids=["plain", "slash-command", "root-with-space", "nested-space",
        "embedded-quote", "trailing-backslash", "backslash-before-space",
        "empty", "flag-shaped"])
def test_convert_to_crew_win32_arg_round_trips_through_the_real_argv_algorithm(value):
    """`ConvertTo-CrewWin32Arg`'s whole job is: whatever pwsh feeds it,
    `Start-Process`'s single joined command line, once split back apart by
    the CHILD process's own argv parser, must reproduce EXACTLY the
    original string as one argument -- this is what stops a `-Root` (or
    `-Text`) value with a space in it silently becoming two argv entries."""
    with open(_PS1, encoding="utf-8") as handle:
        source = handle.read()
    func = _extract_ps1_function(source, "ConvertTo-CrewWin32Arg")
    script = func + "\nWrite-Output (ConvertTo-CrewWin32Arg $env:CREW_TEST_ARG)"
    result = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-Command", script],
        env=dict(os.environ, CREW_TEST_ARG=value),
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    quoted = result.stdout.rstrip("\r\n")
    parsed = _win_argv_split(quoted)
    assert parsed == [value], (
        f"quoted form {quoted!r} parsed back to {parsed!r}, not [{value!r}]")


# ============================================================================
# FIX 3 -- context-watch.sh must not swallow the notify JSON when mktemp
# is unavailable
# ============================================================================


def _watch_repo(tmp_path, session):
    cfg = {"context": {"warnAt": 0.8, "handoffPath": ".work/HANDOFF.md"}}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    (crew / "config.json").write_text(json.dumps({"context": {"autoClear": {
        "enabled": True}}}), encoding="utf-8")
    (root / ".crew" / (".handoff-requested-" + session)).write_text(json.dumps({
        "session_id": session, "requested_at": time.time() - 30,
        "trusted": True, "why": "measured"}), encoding="utf-8")
    handoff = root / ".work" / "HANDOFF.md"
    handoff.write_text(
        "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
        "## Done\n- a thing\n\n## Next action\nDo the next thing.\n", encoding="utf-8")
    os.utime(handoff, (time.time() + 5, time.time() + 5))
    return root


def _no_mktemp_path(tmp_path):
    """A directory prepended to PATH holding a `mktemp` that always fails,
    the same shape a genuinely absent/broken `mktemp` produces (no stdout,
    non-zero exit) -- without needing to reconstruct an entire minimal
    PATH just to remove one binary from it."""
    bindir = tmp_path / "no-mktemp-bin"
    crew_fixtures.write_shim(str(bindir), "mktemp", "#!/bin/sh\nexit 1\n")
    return str(bindir)


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_context_watch_forwards_the_notify_json_even_when_mktemp_fails(tmp_path):
    """End to end through context-watch.sh (not auto-clear.sh directly):
    a `stop_hook_active` continuation with this session's wrap-up marker
    already present hands straight to `cw_run_auto_clear`, which shells out
    to auto-clear.sh. With no TMUX/DISPLAY and OS=Windows_NT, `auto`
    resolves to `notify`, whose systemMessage is the ONE real path that
    writes to auto-clear.sh's stdout -- and `mktemp` is shadowed here to
    always fail, reproducing the exact condition the swallow bug needed."""
    session = "sess-fix3"
    root = _watch_repo(tmp_path, session)
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               TMUX="", DISPLAY="", TMUX_PANE="",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    env["PATH"] = _no_mktemp_path(tmp_path) + os.pathsep + env["PATH"]
    payload = json.dumps({"session_id": session, "cwd": str(root),
                          "hook_event_name": "Stop", "stop_hook_active": True})

    result = subprocess.run([_BASH, _WATCH_SH], cwd=str(root), env=env,
                            input=payload, capture_output=True, text=True,
                            check=False, timeout=60)

    assert result.returncode == 0
    assert result.stdout.strip(), (
        "the notify systemMessage never reached this hook's own stdout "
        "with mktemp shadowed to fail" + repr(result))
    out = json.loads(result.stdout.strip())
    assert "safe to run" in out["systemMessage"], result.stdout
    log_path = root / ".crew" / ".autoclear.log"
    assert log_path.exists()
    assert "sent - method notify" in log_path.read_text(encoding="utf-8")


# ============================================================================
# ITEM 2 -- sendkeys must confirm the Windows Terminal tab it would type into
# is the active or only one, not decline blanket-fashion for every WT window.
#
# The decision is split in two: Get-CrewSendKeysTabDecision is a PURE
# function of (uiaAvailable, tabCount, selectedMatches) and is fully
# unit-tested here, on Linux. Get-CrewWindowsTerminalTabState -- the real UI
# Automation probe that feeds it -- is NOT: there is no live Windows Terminal
# window and no UIAutomationClient assembly on this platform, and nothing in
# this suite can create either. That probe's own fail-closed behaviour (any
# exception -> UiaAvailable=$false) is exercised indirectly by
# test_auto_cycle.py's WindowsTerminal-owner case, which runs on real pwsh
# and observes UIA genuinely being unavailable there.
# ============================================================================


def _extract_ps1_function(source, name):
    """Same brace-balance extraction test_convert_to_crew_win32_arg_... above
    uses, duplicated locally so this section has no ordering dependency on
    the rest of the file."""
    marker = f"function {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    i = brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces extracting {name}")


def _ps1_source():
    with open(_PS1, encoding="utf-8") as handle:
        return handle.read()


def _run_tab_decision(uia_available, tab_count, selected_matches):
    func = _extract_ps1_function(_ps1_source(), "Get-CrewSendKeysTabDecision")
    tab_count_expr = "$null" if tab_count is None else str(tab_count)
    script = (
        func + "\n"
        f"$r = Get-CrewSendKeysTabDecision -UiaAvailable ${str(bool(uia_available)).lower()} "
        f"-TabCount {tab_count_expr} -SelectedMatches ${str(bool(selected_matches)).lower()}\n"
        "Write-Output ($r | ConvertTo-Json -Compress)")
    result = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
@pytest.mark.parametrize("uia_available,tab_count,selected_matches,expect_send", [
    # UIA unavailable declines regardless of what tabCount/selectedMatches
    # would otherwise say -- "could not tell" is never folded into "safe".
    (False, 1, True, False),
    (False, None, False, False),
    (False, 5, True, False),
    # UIA available, but no tab elements found at all -- also unknown.
    (True, 0, False, False),
    (True, None, False, False),
    # Exactly one tab: always safe, whatever selectedMatches says.
    (True, 1, False, True),
    (True, 1, True, True),
    # Several tabs: only a PROVEN selection sends; otherwise decline.
    (True, 2, False, False),
    (True, 2, True, True),
    (True, 7, False, False),
], ids=[
    "uia-unavailable-one-tab", "uia-unavailable-unknown-count", "uia-unavailable-many-tabs",
    "zero-tabs-found", "zero-tabs-null-count",
    "one-tab-unmatched", "one-tab-matched",
    "many-tabs-unmatched", "many-tabs-matched", "many-tabs-unmatched-7",
])
def test_get_crew_send_keys_tab_decision_covers_every_branch(
        uia_available, tab_count, selected_matches, expect_send):
    decision = _run_tab_decision(uia_available, tab_count, selected_matches)
    if expect_send:
        assert decision["Decision"] == "send", decision
    else:
        assert decision["Decision"] == "decline", decision
        assert "cannot verify the active tab" in decision["Reason"], decision


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_get_crew_send_keys_tab_decision_never_sends_when_uia_is_unavailable(tmp_path):
    """Isolates the ONE property item 2's brief calls out by name: an unknown
    tab state must never resolve to "send", however tabCount/selectedMatches
    happen to be set. Sabotage flips exactly this branch's Decision literal
    from "decline" to "send" and must turn this test red."""
    for tab_count, selected in [(1, True), (1, False), (5, True), (None, False)]:
        decision = _run_tab_decision(False, tab_count, selected)
        assert decision["Decision"] == "decline", (
            f"tabCount={tab_count} selectedMatches={selected}: {decision}")


# ============================================================================
# ITEM 1 (part 2) -- the DELAY value handed to the detached sendkeys child,
# asserted as the literal argv entry Get-CrewSendKeysChildArgs builds -- not
# by measuring how long anything takes. A hard-coded `-Delay 3` finishes in
# well under a second regardless of what is configured; only reading the
# argument itself tells the two apart.
# ============================================================================


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
@pytest.mark.parametrize("delay", [1, 4, 6, 9])
def test_get_crew_send_keys_child_args_carries_the_configured_delay(delay):
    source = _ps1_source()
    func = (_extract_ps1_function(source, "ConvertTo-CrewWin32Arg") + "\n" +
            _extract_ps1_function(source, "Get-CrewSendKeysChildArgs"))
    script = (
        func + "\n"
        f"$a = Get-CrewSendKeysChildArgs -ChildPath 'C:/tmp/child.ps1' -Hwnd 42 "
        f"-Command '/clear' -Delay {delay} -Root 'C:/repo'\n"
        "Write-Output ($a | ConvertTo-Json -Compress)")
    result = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout.strip())
    assert "-Delay" in args, args
    # None of the parametrized values is 3 (the schema default): a
    # hard-coded "-Delay 3" would fail every case here, not merely the ones
    # that happen to differ from the default.
    assert args[args.index("-Delay") + 1] == str(delay), args
