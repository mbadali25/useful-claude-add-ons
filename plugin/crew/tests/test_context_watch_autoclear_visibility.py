"""Regression test: context-watch must not swallow a misbehaving auto-clear.

context-watch hands off to auto-clear on a session's forced continuation
(`stop_hook_active`) and on a repeated crossing, and used to discard
everything the child did: its exit code, its stderr, and any exception
thrown invoking it --

  .ps1: `try { & "$PSScriptRoot/auto-clear.ps1" ... 2>$null | Out-Null }
         catch { }`
  .sh:  `bash ".../auto-clear.sh" ... 2>/dev/null`

auto-clear already logs its OWN refusals/sends to .crew/.autoclear.log (see
its own `note()` / Write-CrewAutoClearNote) -- but only on paths that reach
that logger. A crash before that point left NOTHING anywhere recording the
attempt: `.crew/.autoclear.log` was reported to exist nowhere on the affected
Windows host, which is what that total silence looks like. Both callers were
also invoked with no session id in the payload that triggered the report.

This runs the REAL context-watch.sh / context-watch.ps1 -- copied byte for
byte from this repo at test time, so a future revert of the fix in either
file is caught here automatically -- from a scripts/ directory holding a
STUB auto-clear in place of the real one. The stub is what crashes; what is
under test is only what CONTEXT-WATCH does with a child that crashes, not
whatever auto-clear itself does or does not fix (that is tracked separately;
see CLAUDE.md's note on the Windows burn-in).
"""
import json
import os
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")

_BASH = crew_fixtures.resolve_bash()
_HAS_BASH = _BASH is not None
_PWSH = crew_fixtures.resolve_pwsh()
_HAS_PWSH = _PWSH is not None

FLAVORS = [f for f, have in (("sh", _HAS_BASH), ("ps1", _HAS_PWSH)) if have]
by_flavor = pytest.mark.parametrize("flavor", FLAVORS)

# Crashes on purpose: exits non-zero AND writes to stderr, deliberately
# BEFORE anything resembling auto-clear's own logger could run. `param()`
# blocks accept the same flags the real script does (-Session/-Root,
# --session/--root) so the crash under test is this file's own `exit 3`,
# never a parameter-binding failure standing in for it.
_CRASH_SH = "#!/usr/bin/env bash\necho 'stub auto-clear: boom, crashed before logging' >&2\nexit 3\n"
_CRASH_PS1 = (
    "param([string]$Session = \"\", [string]$Root = \"\", [switch]$DryRun, [switch]$Force)\n"
    "[Console]::Error.WriteLine('stub auto-clear: boom, crashed before logging')\n"
    "exit 3\n"
)
# A well-behaved child: exits 0, says nothing. Must not itself manufacture a
# log line -- the capture is about a MISBEHAVING child, not every child.
_QUIET_SH = "#!/usr/bin/env bash\nexit 0\n"
_QUIET_PS1 = "param([string]$Session = \"\", [string]$Root = \"\", [switch]$DryRun, [switch]$Force)\nexit 0\n"


def _fixture_scripts(tmp_path, flavor, auto_clear_body):
    """A copy of the real context-watch.{sh,ps1} (plus .sh's _common.sh
    dependency) next to a stub auto-clear with the given body."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    if flavor == "sh":
        shutil.copy2(os.path.join(_SCRIPTS, "context-watch.sh"), scripts / "context-watch.sh")
        shutil.copy2(os.path.join(_SCRIPTS, "_common.sh"), scripts / "_common.sh")
        stub = scripts / "auto-clear.sh"
        stub.write_text(auto_clear_body, encoding="utf-8", newline="\n")
        os.chmod(stub, 0o755)
        os.chmod(scripts / "context-watch.sh", 0o755)
        return scripts / "context-watch.sh"
    shutil.copy2(os.path.join(_SCRIPTS, "context-watch.ps1"), scripts / "context-watch.ps1")
    (scripts / "auto-clear.ps1").write_text(auto_clear_body, encoding="utf-8", newline="\n")
    return scripts / "context-watch.ps1"


def _payload(root):
    # No session_id at all -- both flavours fall back to "", the no-session
    # call the report names, and the marker key falls back to "nosession"
    # (session_markers() / the same rule in the .ps1 twin).
    return json.dumps({"cwd": str(root), "stop_hook_active": True})


def _marker(root):
    path = root / ".crew" / ".handoff-requested-nosession"
    path.write_text(json.dumps({"session_id": "", "trusted": True, "why": "measured"}),
                    encoding="utf-8")
    return path


def _log_lines(root):
    path = root / ".crew" / ".autoclear.log"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(flavor, script, root):
    env = dict(os.environ, HOME=str(root), USERPROFILE=str(root))
    if flavor == "sh":
        cmd = [_BASH, str(script).replace("\\", "/")]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)]
        env["OS"] = "Windows_NT"
    return subprocess.run(cmd, input=_payload(root), cwd=str(root), env=env,
                          capture_output=True, text=True, check=False)


def test_flavors_are_discoverable():
    assert FLAVORS, "neither bash nor pwsh is on PATH; cannot test context-watch"


@by_flavor
def test_a_crashing_auto_clear_is_logged_not_swallowed(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"context": {"warnAt": 0.8}}, git=False)
    _marker(root)
    body = _CRASH_SH if flavor == "sh" else _CRASH_PS1
    script = _fixture_scripts(tmp_path, flavor, body)

    result = _run(flavor, script, root)

    # The Stop hook's own contract is unchanged: stop_hook_active always
    # exits 0 here, and nothing the crashing child wrote reaches THIS hook's
    # own stdout, which Claude Code would read as this hook's protocol.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    lines = _log_lines(root)
    assert lines, "auto-clear crashed and left no trace in .crew/.autoclear.log"
    assert any("exited 3" in line and "boom" in line for line in lines), lines


@by_flavor
def test_a_quiet_auto_clear_writes_no_log_line(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"context": {"warnAt": 0.8}}, git=False)
    _marker(root)
    body = _QUIET_SH if flavor == "sh" else _QUIET_PS1
    script = _fixture_scripts(tmp_path, flavor, body)

    result = _run(flavor, script, root)

    assert result.returncode == 0, result.stderr
    assert not _log_lines(root), _log_lines(root)
