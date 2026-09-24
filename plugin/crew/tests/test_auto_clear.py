"""Tests for the EXPERIMENTAL auto-clear pair.

This is the only crew script that reaches outside the session to press a key on
the user's behalf, so the properties worth pinning are all refusals:

  - opted out (the default) does nothing at all, not even a log file
  - a stub handoff does not trigger a clear
  - a method that cannot verify what it types into refuses
  - a refusal does NOT burn the one-per-session attempt, or fixing the config
    mid-session would appear to change nothing
  - a dry run does not burn it either

Every case runs with `--dry-run` or against a fake `tmux`/`xdotool` on PATH, so
no test can send a keystroke to the machine running it.

Both flavours are exercised where both interpreters exist; the PowerShell one is
skipped elsewhere. That asymmetry is the bug this plugin keeps having - a `.ps1`
that drifted from its `.sh` twin for a whole release - and it is worse here than
usual, because the failure mode is a keystroke going somewhere unintended.
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

_ROOT = context._ROOT  # pylint: disable=protected-access
# Forward slashes: MSYS bash re-parses its own argv and eats bare backslashes.
_SH = (_ROOT + "/hooks/scripts/auto-clear.sh").replace("\\", "/")
_PS1 = _ROOT + "/hooks/scripts/auto-clear.ps1"

# Not shutil.which("bash"): under PowerShell that resolves WSL's bash, which
# cannot open a Windows path and exits 127 for every script handed to it.
# resolve_bash() proves a candidate by running one, and returns None when there
# is none - so the `sh` flavour is skipped rather than parametrized in to fail.
_BASH = crew_fixtures.resolve_bash()
# The .ps1 flavour is native Windows ONLY: its send path is
# System.Windows.Forms.SendKeys against a Win32 foreground window, so on a Linux
# runner with pwsh installed (the CI job has one) the script now stands down
# immediately - and a test that expected it to refuse for some *other* reason
# would pass for the wrong reason, while one expecting it to send would fail.
# Both happened on the first CI run: it claimed the one-per-session attempt and
# reported "sent" on a platform where it cannot type anything.
_PWSH = shutil.which("pwsh") if sys.platform.startswith("win") else None
FLAVORS = [f for f, have in (("sh", _BASH), ("ps1", _PWSH)) if have]

by_flavor = pytest.mark.parametrize("flavor", FLAVORS)

HANDOFF = (
    "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
    "## Done\n- a thing\n\n## Next action\nDo the next thing.\n"
)


def _stub(directory, name, body="#!/bin/sh\nexit 0\n", cmd_body="@echo off\r\nexit /b 0\r\n"):
    """A fake executable on PATH, so a resolved method never really types.

    `crew_fixtures.write_shim` writes the extensionless file bash runs and,
    on Windows, the `.cmd` twin -- the only form the native python behind
    `crew_autocycle.py` can find with `shutil.which`."""
    return crew_fixtures.write_shim(directory, name, body, cmd_body)


def _crlf_python_env(tmp_path):
    """A `PYTHONPATH` entry carrying a `sitecustomize.py` that reconfigures
    EVERY python process that inherits it to write CRLF, rather than the
    real `crew_py_strict`-resolved interpreter's own untouched choice.

    The naive way to model "python on Windows writes \\r\\n" -- a wrapper
    script pretending to be `python3` on PATH ahead of the real one -- does
    not work here: `crew_py_strict`'s probe proves a candidate by running
    `sys.executable` and then uses THAT resolved path for every later call
    (exactly the alias-forwarding behaviour
    `test_context_watch_python_resolver.py`'s Store-alias case exists to
    prove), so a wrapper is bypassed the moment it hands back a real
    interpreter's own path -- confirmed by hand before trusting this
    fixture. A real native Windows python.exe does not need a wrapper to
    write CRLF; it is `sys.stdout`'s own default text-mode newline
    translation on that platform (`io.TextIOWrapper(..., newline=None)`
    translates every `\\n` a `print()` writes to `os.linesep`, and
    `os.linesep` is `\\r\\n` there). `sitecustomize.py` reproduces that SAME
    effect on whichever real interpreter this host resolves, instead of
    substituting a fake one, so it survives the resolver's own
    sys.executable indirection intact.

    Sabotage-checked by hand: with `auto-clear.sh`'s own `tr -d '\\r'` on the
    plan capture removed, a run using this env refuses (empty stdout,
    "refusing" on stderr) instead of reporting `method: tmux`. Without this
    fixture the same sabotage left the pre-existing test passing unchanged,
    because a real Linux python3 never emits the CR this guards against."""
    sitedir = tmp_path / "crlf-sitecustomize"
    sitedir.mkdir(exist_ok=True)
    (sitedir / "sitecustomize.py").write_text(
        "import sys, io\n"
        "sys.stdout = io.TextIOWrapper(\n"
        "    sys.stdout.buffer, encoding=sys.stdout.encoding,\n"
        "    newline='\\r\\n', line_buffering=True)\n",
        encoding="utf-8")
    return {"PYTHONPATH": str(sitedir)}


SESSION = "sess-1"
SENT = ".autoclear-sent-" + SESSION
REQUESTED = ".handoff-requested-" + SESSION


def _write_machine(root, enabled):
    """`enabled` is a MACHINE opt-in: it is read from the global file under
    HOME, which `_run` points at `<tmp>/home`, never the real one."""
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    cfg = {} if enabled is _ABSENT else {"context": {"autoClear": {"enabled": enabled}}}
    (crew / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


_ABSENT = object()


def _repo(tmp_path, auto_clear=None, handoff=HANDOFF, requested=True):
    cfg = {"context": {"warnAt": 0.8, "handoffPath": ".work/HANDOFF.md"}}
    auto = dict(auto_clear or {})
    enabled = auto.pop("enabled", _ABSENT)
    if auto_clear is not None:
        cfg["context"]["autoClear"] = auto
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    _write_machine(root, enabled)
    if requested:
        # A trusted wrap-up request for THIS session, as context-watch writes
        # it. test_auto_cycle.py owns the untrusted and foreign-session cases.
        (root / ".crew" / REQUESTED).write_text(json.dumps({
            "session_id": SESSION, "requested_at": time.time() - 30,
            "trusted": True, "why": "measured"}), encoding="utf-8")
    if handoff is not None:
        # mtime must be strictly newer than the request: "the handoff was
        # written AFTER we asked for it" is one of the conditions.
        path = root / ".work" / "HANDOFF.md"
        path.write_text(handoff, encoding="utf-8")
        stamp = time.time() + 5
        os.utime(path, (stamp, stamp))
    return root


def _run(flavor, root, *args, env_extra=None, session=SESSION):
    # Never let the suite reach the real send path. Set here rather than
    # per-test so a case added later cannot forget it; the cases that DO
    # exercise sending pass --dry-run, which prints the decision without the
    # keystroke. See CREW_AUTOCLEAR_INHIBIT in auto-clear.{sh,ps1}.
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    if env_extra:
        env.update(env_extra)
    if session is not None:
        args = ("--session", session) + args
    if flavor == "sh":
        cmd = [_BASH, _SH, *args]
    else:
        ps_args = ["-DryRun" if a == "--dry-run" else
                   "-Force" if a == "--force" else
                   "-Session" if a == "--session" else a for a in args]
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, *ps_args]
    return subprocess.run(cmd, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, check=False)


def _window_stub(tmp_path, windows):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(windows), encoding="utf-8")
    return {"CREW_AUTOCLEAR_WINDOW_STUB": str(path)}


def _sendable(flavor, tmp_path):
    """Config and env for a method each flavour will actually agree to use.

    tmux must now prove the pane is this session's: the stub reports this
    test process's pid as the pane pid, and this process IS an ancestor of
    the script. The Windows flavour gets one stubbed window whose title is
    the only match -- the title fallback, since no ancestor owns it."""
    if flavor == "sh":
        bindir = str(tmp_path / "fakebin")
        _stub(bindir, "tmux", f"#!/bin/sh\necho {os.getpid()}\n",
              f"@echo off\r\necho {os.getpid()}\r\n")
        return ({"enabled": True, "method": "tmux"},
                {"PATH": crew_fixtures.shell_path("sh", [bindir]),
                 "TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%9"})
    return ({"enabled": True, "windowTitle": "NoSuchWindowForTests"},
            _window_stub(tmp_path, [{"id": 4242, "pid": 999999,
                                     "title": "NoSuchWindowForTests"}]))


def test_flavors_are_discoverable():
    assert FLAVORS, "neither bash nor pwsh is on PATH; cannot test auto-clear"


# --- The Windows burn-in's real cause: home-dir resolution bypassed the test
#     isolation entirely ---------------------------------------------------
#
# `[Environment]::GetFolderPath('UserProfile')` resolves the profile path via
# the Shell API from the current user's token/registry on native Windows,
# and ignores an overridden $env:USERPROFILE there -- unlike its Linux/.NET
# Core implementation, which reads $env:HOME and so happily obeys every
# fixture in this suite that redirects HOME/USERPROFILE at a tmp directory.
# That made the divergence invisible on a Linux-pwsh run (this container
# included) and live on the one platform the script actually runs on: a
# burn-in there read the REAL machine ~/.claude/crew/config.json instead of
# the isolated fixture one, arming on whatever autoClear state that real
# machine happened to be carrying. No env-var trick can prove the ORIGINAL
# bug here -- the asymmetry is in the .NET runtime's own per-OS
# implementation of GetFolderPath, not in anything a Linux pwsh process can
# be made to disagree with itself about -- so this is a static tripwire
# instead, the same shape as
# `test_context_watch_does_not_call_the_unhardened_resolver`.
def test_auto_clear_ps1_resolves_home_from_the_env_not_the_shell_api():
    # Comment lines excluded: this test's own docstring/header quotes the old
    # call form by name, and a bare substring check over the whole file would
    # match its own explanation rather than the code.
    code_lines = [line for line in pathlib.Path(_PS1).read_text(encoding="utf-8").splitlines()
                  if not line.strip().startswith("#")]
    source = "\n".join(code_lines)
    assert "GetFolderPath" not in source, (
        "auto-clear.ps1 is back on [Environment]::GetFolderPath('UserProfile'), "
        "which ignores $env:USERPROFILE on native Windows and so cannot be "
        "redirected to an isolated fixture home -- every other case in this "
        "suite depends on that redirection actually working. Read $env:"
        "USERPROFILE (falling back to $env:HOME) instead, matching "
        "cloud-guard.ps1's Test-CloudGuardArmed.")


# --- Opted out ------------------------------------------------------------


@by_flavor
def test_absent_block_does_nothing_and_writes_no_log(flavor, tmp_path):
    # The default. A repo that never asked for this must not even discover the
    # feature exists by finding a log file in .crew/.
    root = _repo(tmp_path)
    result = _run(flavor, root, "--dry-run")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


@by_flavor
def test_enabled_false_does_nothing(flavor, tmp_path):
    root = _repo(tmp_path, auto_clear={"enabled": False, "method": "tmux"})
    result = _run(flavor, root, "--dry-run")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


@by_flavor
def test_enabled_as_a_string_is_not_enabled(flavor, tmp_path):
    # Config is hand-edited. "true" means someone was confused, not yes -- and
    # the permissive reading of that sends a keystroke nobody asked for.
    root = _repo(tmp_path, auto_clear={"enabled": "true", "method": "tmux"})
    result = _run(flavor, root, "--dry-run")
    assert result.stdout.strip() == ""


# --- The handoff conditions ----------------------------------------------


@by_flavor
def test_no_handoff_request_means_nothing_to_clear_after(flavor, tmp_path):
    cfg, env = _sendable(flavor, tmp_path)
    root = _repo(tmp_path, auto_clear=cfg, requested=False)
    result = _run(flavor, root, env_extra=env)
    assert result.returncode == 0
    assert not (root / ".crew" / SENT).exists()


@by_flavor
def test_a_stub_handoff_refuses(flavor, tmp_path):
    # Clearing on the strength of a two-line placeholder loses the session's
    # work and leaves a note that says "continue the work".
    cfg, env = _sendable(flavor, tmp_path)
    root = _repo(tmp_path, auto_clear=cfg, handoff="# Handoff\nTODO\n")
    result = _run(flavor, root, env_extra=env)
    assert result.returncode == 0
    assert "minHandoffLines" in result.stderr
    assert not (root / ".crew" / SENT).exists()


@by_flavor
def test_a_handoff_older_than_the_request_refuses(flavor, tmp_path):
    # A leftover HANDOFF.md from a previous session is not this session's note.
    cfg, env = _sendable(flavor, tmp_path)
    root = _repo(tmp_path, auto_clear=cfg)
    path = root / ".work" / "HANDOFF.md"
    stale = os.path.getmtime(root / ".crew" / REQUESTED) - 60
    os.utime(path, (stale, stale))
    result = _run(flavor, root, env_extra=env)
    assert result.returncode == 0
    assert not (root / ".crew" / SENT).exists()


@by_flavor
def test_min_handoff_lines_is_configurable(flavor, tmp_path):
    cfg, env = _sendable(flavor, tmp_path)
    cfg = dict(cfg, minHandoffLines=99)
    root = _repo(tmp_path, auto_clear=cfg)
    result = _run(flavor, root, env_extra=env)
    assert "minHandoffLines is 99" in result.stderr


# --- Refusing to type into something it cannot identify ------------------


@by_flavor
def test_a_method_that_cannot_verify_its_target_refuses_without_a_title(
        flavor, tmp_path):
    """CHANGED in 0.19.57, and only for the PowerShell flavour.

    `xdotool` activates a window BY NAME, so it still cannot prove it is
    talking to Claude Code and an explicit title is still the user accepting
    that -- the sh case is unchanged.

    The Windows flavour no longer needs one. It walks its own ancestors to the
    first process that OWNS A WINDOW and compares the foreground window's
    owning process id to it, which is exact where a title was a guess: the
    detector read three different titles for the same window in one session.
    So `windowTitle` unset is no longer a refusal there, and asserting one
    would be asserting the old defect.
    """
    if flavor == "sh":
        bindir = str(tmp_path / "fakebin")
        _stub(bindir, "xdotool")
        cfg = {"enabled": True, "method": "xdotool"}
        env = {"PATH": crew_fixtures.shell_path("sh", [bindir]), "DISPLAY": ":0"}
        root = _repo(tmp_path, auto_clear=cfg)
        result = _run(flavor, root, env_extra=env)
        assert result.returncode == 0
        assert "windowTitle" in result.stderr
        return

    # ps1: must not demand a title merely because one is unset. It either
    # resolves the owning terminal and proceeds, or says it could NOT resolve
    # one -- and which of those happens depends on the ancestry of whatever
    # launched the tests. Measured: it resolves from a plain shell and does
    # not from under pytest, so asserting either outcome would be asserting a
    # property of the test runner.
    #
    # What IS invariant is that the OLD unconditional refusal is gone, so that
    # exact sentence is what this checks.
    root = _repo(tmp_path, auto_clear={"enabled": True})
    result = _run(flavor, root, "--dry-run")
    assert result.returncode == 0
    assert "windowTitle is required" not in result.stderr, result.stderr


@by_flavor
def test_an_unknown_method_refuses_by_name(flavor, tmp_path):
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "telepathy",
                                       "windowTitle": "x"})
    result = _run(flavor, root)
    assert result.returncode == 0
    assert "telepathy" in result.stderr


@pytest.mark.skipif("sh" not in FLAVORS, reason="needs bash")
def test_wtype_needs_explicit_consent_because_it_cannot_check_focus(tmp_path):
    bindir = str(tmp_path / "fakebin")
    _stub(bindir, "wtype")
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "wtype",
                                       "windowTitle": "Claude"})
    result = _run("sh", root, env_extra={
        "PATH": crew_fixtures.shell_path("sh", [bindir]),
        "WAYLAND_DISPLAY": "wayland-0"})
    assert "unsafeFocus" in result.stderr
    assert not (root / ".crew" / SENT).exists()


# --- The one-per-session claim -------------------------------------------


@by_flavor
def test_a_dry_run_does_not_burn_the_one_attempt(flavor, tmp_path):
    cfg, env = _sendable(flavor, tmp_path)
    root = _repo(tmp_path, auto_clear=cfg)
    result = _run(flavor, root, "--dry-run", env_extra=env)
    assert "would send" in result.stdout
    assert not (root / ".crew" / SENT).exists()


@by_flavor
def test_a_refusal_does_not_burn_the_one_attempt(flavor, tmp_path):
    """The claim is taken immediately before the send, not with the conditions.

    Taken earlier, a misconfiguration burns the session's only attempt: the user
    fixes windowTitle, nothing happens, and there is no way to tell that from
    the feature being broken.
    """
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "telepathy"})
    _run(flavor, root)
    assert not (root / ".crew" / SENT).exists()

    # Now fix it in the same session and confirm it really does retry.
    cfg, env = _sendable(flavor, tmp_path)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"context": {"handoffPath": ".work/HANDOFF.md",
                                "autoClear": cfg}}), encoding="utf-8")
    result = _run(flavor, root, env_extra=env)
    assert "sent" in result.stderr
    assert (root / ".crew" / SENT).exists()


@by_flavor
def test_the_second_attempt_in_one_session_is_silent(flavor, tmp_path):
    # Two /clear keystrokes means the second one lands in the FRESH session,
    # where it wipes context nobody asked to lose.
    cfg, env = _sendable(flavor, tmp_path)
    root = _repo(tmp_path, auto_clear=cfg)
    first = _run(flavor, root, env_extra=env)
    assert "sent" in first.stderr
    second = _run(flavor, root, env_extra=env)
    assert second.returncode == 0
    assert second.stderr.strip() == ""


# --- The plan, and what reaches it ---------------------------------------


@by_flavor
def test_the_dry_run_plan_reports_the_configured_command_and_delay(
        flavor, tmp_path):
    # Whatever method `_sendable` actually resolves to on this host decides
    # what "the delay" means: sendkeys/tmux wait the configured seconds out,
    # notify has none to wait (its own exact wording is asserted below). Read
    # `method:` back out of the emitted plan rather than assuming which one
    # was reached -- forcing a method here is what made the old version of
    # this test vacuous: under the window-stub pid (999999) the .ps1 flavour
    # declines sendkeys and prints a decline notice with no `method:` line at
    # all, so a hard-coded "sendkeys" expectation never got asserted against.
    cfg, env = _sendable(flavor, tmp_path)
    cfg = dict(cfg, command="/compact", delaySeconds=9)
    root = _repo(tmp_path, auto_clear=cfg)
    result = _run(flavor, root, "--dry-run", env_extra=env)
    out = result.stdout
    method_lines = [line.split(":", 1)[1].strip()
                    for line in out.splitlines()
                    if line.strip().startswith("method:")]
    assert method_lines, (
        f"no dry-run plan was emitted at all (stdout={out!r} "
        f"stderr={result.stderr!r})")
    resolved = method_lines[0]
    assert "command: /compact" in out, out
    if resolved in ("sendkeys", "tmux"):
        assert "delay: 9s" in out, out
    elif resolved == "notify":
        assert "delay: n/a (notify sends no keystroke)" in out, out
    else:
        pytest.fail(f"unexpected resolved method {resolved!r} in plan: {out!r}")


@by_flavor
def test_the_notify_plan_says_the_delay_is_not_applicable(flavor, tmp_path):
    """notify types nothing, so it has no delay to wait out and no window to
    target. The plan used to print `delay: 0s` (.ps1) or the configured number
    (.sh), and an empty `target:` line (.sh). Each reads as a real setting;
    none is one."""
    root = _repo(tmp_path, auto_clear={
        "enabled": True, "method": "notify",
        "command": "/compact", "delaySeconds": 9})
    out = _run(flavor, root, "--dry-run").stdout
    assert "method: notify" in out, out
    assert "command: /compact" in out, out
    # Exact wording, not a substring: "delay: n/a" alone is also a substring
    # of the old bare text, so a loose check here stays green even if the
    # " (notify sends no keystroke)" suffix regresses.
    assert "delay: n/a (notify sends no keystroke)" in out, out
    assert "9s" not in out, out
    assert "target:" not in out, out


@pytest.mark.skipif("sh" not in FLAVORS, reason="needs bash")
def test_a_window_title_containing_spaces_survives_config_parsing(tmp_path):
    """Regression: the config was read as tab-separated fields with
    `IFS=$'\\t' read`. Tab is IFS *whitespace*, so bash collapsed consecutive
    tabs and an empty windowTitle - the default - shifted every later field left
    by one. The script then exited silently having done nothing.

    The window layer is stubbed with exactly one window of that title, so the
    title fallback resolves it uniquely; test_auto_cycle.py owns the zero and
    many cases.
    """
    bindir = str(tmp_path / "fakebin")
    _stub(bindir, "xdotool")
    root = _repo(tmp_path, auto_clear={
        "enabled": True, "method": "xdotool",
        "windowTitle": "Claude Code - my repo"})
    env = {"PATH": crew_fixtures.shell_path("sh", [bindir]), "DISPLAY": ":0"}
    env.update(_window_stub(tmp_path, [
        {"id": 77, "pid": 999999, "title": "Claude Code - my repo"}]))
    out = _run("sh", root, "--dry-run", env_extra=env).stdout
    assert "target: Claude Code - my repo" in out


@pytest.mark.skipif("sh" not in FLAVORS, reason="needs bash")
def test_config_values_survive_a_crlf_writing_python(tmp_path):
    """Regression: python on Windows writes \\r\\n, so every value arrived with
    a trailing CR. `enabled` read as "true\\r", the equality test failed, and the
    script exited 0 having done nothing and said nothing - the hardest possible
    failure to diagnose from a Stop hook.

    Runs `crew_autocycle.py` itself through a CRLF-emitting python
    (`_crlf_python_env`) so this actually exercises `auto-clear.sh:106`'s
    `tr -d '\\r'` on the plan capture -- the real python3 this test ran
    against before never wrote a CR at all, so the assertions below passed
    whether or not that stripping was there to catch. See
    `_crlf_python_env`'s docstring for the sabotage check that proved it.
    """
    bindir = str(tmp_path / "fakebin")
    _stub(bindir, "tmux", f"#!/bin/sh\necho {os.getpid()}\n",
              f"@echo off\r\necho {os.getpid()}\r\n")
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "tmux"})
    env = {"PATH": crew_fixtures.shell_path("sh", [bindir]),
           "TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%9"}
    env.update(_crlf_python_env(tmp_path))
    out = _run("sh", root, "--dry-run", env_extra=env).stdout
    assert "method: tmux" in out, "a CR in the config values would break this"
    assert "target: %9" in out


@pytest.mark.skipif("sh" not in FLAVORS, reason="needs bash")
def test_tmux_method_refuses_outside_tmux(tmp_path):
    bindir = str(tmp_path / "fakebin")
    _stub(bindir, "tmux")
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "tmux"})
    env = {"PATH": crew_fixtures.shell_path("sh", [bindir])}
    env["TMUX"] = ""
    result = _run("sh", root, env_extra=env)
    assert "not in a tmux pane" in result.stderr or "TMUX" in result.stderr
    assert not (root / ".crew" / SENT).exists()


@pytest.mark.skipif("ps1" not in FLAVORS, reason="needs pwsh")
def test_the_windows_flavour_points_tmux_users_at_the_bash_one(tmp_path):
    root = _repo(tmp_path, auto_clear={"enabled": True, "method": "tmux",
                                       "windowTitle": "x"})
    result = _run("ps1", root)
    assert "auto-clear.sh" in result.stderr


_PWSH_ANY = shutil.which("pwsh")


@pytest.mark.skipif(_PWSH_ANY is None or sys.platform.startswith("win"),
                    reason="the point of this case is a NON-Windows pwsh")
def test_the_windows_flavour_stands_down_entirely_off_windows(tmp_path):
    """On Linux/macOS pwsh, auto-clear.ps1 must do nothing at all.

    Its send path is SendKeys against a Win32 foreground window. Without the
    $IsWindows guard it ran every condition, claimed the one-per-session
    attempt, and reported "sent" while delivering no keystroke - which is worse
    than failing, because the log then says it worked. auto-clear.sh is the
    flavour for those platforms and is registered alongside it.
    """
    root = _repo(tmp_path, auto_clear={"enabled": True, "windowTitle": "x"})
    result = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-File", _PS1],
        cwd=str(root), env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / SENT).exists()
    assert not (root / ".crew" / ".autoclear.log").exists()


# --- The `.crew/` gate --------------------------------------------------------
#
# OWNER DECISION (crew 1.0 F4, reversing the file-based gate this section used
# to describe): `context.autoClear` is a MACHINE-global switch
# (`crew_config.py`), so it must work in any crew repo without a per-repo
# config of its own -- "crew repo" is read as `.crew/` the DIRECTORY existing,
# not `.crew/config.json`. See CONFIG.md sec 14 for the full account,
# including the file-gate period this reverses. The six states below are the
# ones that decide silence vs. arming:
#
#   (1) NO `.crew/` at all, machine enabled -- SILENT. Exit 0, nothing on
#       stdout or stderr, and `.crew/` must NEVER spring into existence as a
#       side effect of a hook that only ever reads -- crew never creates
#       `.crew/` from a read.
#   (2) `.crew/` present, NO config.json, machine enabled -- ARMED. Reaches
#       the session check (the no-session refusal is logged), because
#       `.crew/`'s mere existence is now the whole "is this a crew repo"
#       question, and a repo that never got as far as writing a config.json
#       must not stop the machine's global enabled:true from reaching it.
#   (3) `.crew/` present, NO config.json, machine DISABLED -- SILENT, no log
#       file. Same repo shape as (2); the machine simply never opted in.
#   (4) `.crew/` + config.json present (even with no `autoClear` block at
#       all), machine enabled -- ARMED, for the same reason as (2): a
#       present-but-empty repo config is the same input to
#       Read-CrewJsonFile/crew_autocycle._load as an absent `autoClear`
#       block, and 1.0 already merges: machine opts in, repo may only opt
#       out. Repo silence is not an opt-out.
#   (5) `.crew/` + config.json present, repo `autoClear.enabled: false`,
#       machine enabled -- SILENT (a repo may only narrow the machine's
#       opt-in, never widen it).
#   (6) `.crew/` present, machine enabled but `onlyRepos` excludes this repo
#       -- SILENT, no log line either (a narrowing that does not match this
#       repo is the same as never having opted in).


def _repo_with_empty_config(tmp_path, machine_enabled=True):
    """`.crew/config.json` present but empty -- no `autoClear` block at
    all -- matching a repo that ran `/crew:init` for something else and
    never touched this feature. The MACHINE is opted in regardless --
    `test_only_the_machine_can_opt_in_and_a_repo_can_only_opt_out` already
    proves a repo need not enable anything for the machine's global config
    to arm it."""
    root = crew_fixtures.make_repo(tmp_path, config={}, git=False)
    _write_machine(root, machine_enabled)
    return root


def _repo_with_no_config(tmp_path, machine_enabled=True):
    """A repo directory that HAS `.crew/` (so it has been through
    `/crew:init` or equivalent, or is a worktree that copied the directory)
    but no `.crew/config.json` -- matching a fresh checkout: the file is
    git-ignored in this very repo (`.gitignore:292`), so every clone or
    worktree starts this way until something writes one. Proves the gate is
    on the DIRECTORY, not the file: states (2) and (3) below."""
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    _write_machine(root, machine_enabled)
    return root


def _repo_with_no_crew_dir(tmp_path, machine_enabled=True):
    """A repo directory with NO `.crew/` at all -- never initialised, and
    never touched by anything crew has run before. `make_repo` always
    creates `.crew/` (every other fixture in this file needs it to exist),
    so this one is built by hand instead."""
    root = tmp_path / "repo"
    (root / ".work").mkdir(parents=True)
    _write_machine(root, machine_enabled)
    return root


def _write_machine_autoclear(root, auto_clear):
    """Like `_write_machine`, but writes the whole `context.autoClear` block
    instead of just `enabled` -- for onlyRepos/onlySessions narrowing."""
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    cfg = {"context": {"autoClear": auto_clear}}
    (crew / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _run_ps1_forced_windows(root, *extra_args):
    """The `.ps1` twin, run the way hooks.json's registered scripts are
    invoked (`pwsh -NoProfile ... -File script.ps1 <args>`), with
    `OS=Windows_NT` forced -- the same test seam `scope_fixtures.py`/
    `test_context_watch.py` use to drive this flavour on a non-Windows host.
    Nothing in these cases reaches the send path, so it is safe off real
    Windows too.
    """
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    return subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-File", _PS1,
         "-Root", str(root), *extra_args],
        cwd=str(root), env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False)


# (4) `.crew/` + config.json present, machine on -- armed, reaches the
#     session check.


def test_a_present_but_empty_repo_config_is_armed_sh(tmp_path):
    """State (4): an initialised repo with a present-but-empty config.json
    is armed by the machine's global enabled:true, same as state (2)'s
    missing config.json -- a repo config file's mere presence changes
    nothing about the merge."""
    root = _repo_with_empty_config(tmp_path)
    assert (root / ".crew" / "config.json").exists()
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert "no session id" in result.stderr, result.stderr
    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "no session id" in log


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_a_present_but_empty_repo_config_is_armed_ps1(tmp_path):
    """The `.ps1` twin of the case above."""
    root = _repo_with_empty_config(tmp_path)
    assert (root / ".crew" / "config.json").exists()
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert "no session id" in result.stderr, result.stderr
    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "no session id" in log


# (2) `.crew/` present, NO config.json, machine enabled -- ARMED, reaches the
#     session check. This is the state the F4 gate reversal exists for: a
#     `.crew/` directory with no config.json used to stand this down
#     entirely (the file-based gate F3 shipped); it now behaves exactly like
#     state (4) above, because the directory's mere existence is the whole
#     "is this a crew repo" question.


def test_a_crew_directory_with_no_config_json_arms_and_reaches_the_session_check_sh(tmp_path):
    root = _repo_with_no_config(tmp_path, machine_enabled=True)
    assert (root / ".crew").is_dir()
    assert not (root / ".crew" / "config.json").exists()
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert "no session id" in result.stderr, result.stderr
    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "no session id" in log


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_a_crew_directory_with_no_config_json_arms_and_reaches_the_session_check_ps1(tmp_path):
    root = _repo_with_no_config(tmp_path, machine_enabled=True)
    assert (root / ".crew").is_dir()
    assert not (root / ".crew" / "config.json").exists()
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert "no session id" in result.stderr, result.stderr
    log = (root / ".crew" / ".autoclear.log").read_text(encoding="utf-8")
    assert "no session id" in log


# (3) `.crew/` present, NO config.json, machine DISABLED -- silent, no log
#     file. Same repo shape as (2); only the machine's opt-in differs.


def test_a_crew_directory_with_no_config_json_and_machine_disabled_stays_silent_sh(tmp_path):
    root = _repo_with_no_config(tmp_path, machine_enabled=False)
    assert (root / ".crew").is_dir()
    assert not (root / ".crew" / "config.json").exists()
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_a_crew_directory_with_no_config_json_and_machine_disabled_stays_silent_ps1(tmp_path):
    root = _repo_with_no_config(tmp_path, machine_enabled=False)
    assert (root / ".crew").is_dir()
    assert not (root / ".crew" / "config.json").exists()
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


# (1) NO `.crew/` at all, machine enabled -- silent, and nothing may be
#     created as a side effect.


def test_no_crew_directory_at_all_stays_silent_and_creates_nothing_sh(tmp_path):
    root = _repo_with_no_crew_dir(tmp_path)
    assert not (root / ".crew").exists()
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (root / ".crew").exists()


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_no_crew_directory_at_all_stays_silent_and_creates_nothing_ps1(tmp_path):
    root = _repo_with_no_crew_dir(tmp_path)
    assert not (root / ".crew").exists()
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""
    assert not (root / ".crew").exists()


# (6) `.crew/` present, machine on but `onlyRepos` excludes this repo --
#     silent, no log line either.


def test_only_repos_excluding_this_repo_stays_silent_sh(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={}, git=False)
    _write_machine_autoclear(root, {"enabled": True,
                                     "onlyRepos": [str(tmp_path / "elsewhere")]})
    assert (root / ".crew" / "config.json").exists()
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_only_repos_excluding_this_repo_stays_silent_ps1(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={}, git=False)
    _write_machine_autoclear(root, {"enabled": True,
                                     "onlyRepos": [str(tmp_path / "elsewhere")]})
    assert (root / ".crew" / "config.json").exists()
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


# (5) repo-local `enabled: false` while the machine is on -- silent (a repo
#     may only narrow the opt-in, never widen it). This fixture already
#     writes a real config.json, so the gate change does not touch it.


def _repo_opted_out(tmp_path):
    cfg = {"context": {"warnAt": 0.8, "handoffPath": ".work/HANDOFF.md",
                        "autoClear": {"enabled": False}}}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    _write_machine(root, True)
    return root


def test_repo_local_opt_out_stays_silent_with_global_on_sh(tmp_path):
    root = _repo_opted_out(tmp_path)
    result = _run("sh", root, session=None)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_repo_local_opt_out_stays_silent_with_global_on_ps1(tmp_path):
    root = _repo_opted_out(tmp_path)
    result = _run_ps1_forced_windows(root)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not (root / ".crew" / ".autoclear.log").exists()
