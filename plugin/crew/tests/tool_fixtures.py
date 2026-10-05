"""L-1508: a tool that only `shutil.which` can reach.

A guard that runs a bare `"git"` judges whatever CreateProcess finds (on
Windows only `git.exe`), while bash, pwsh and `shutil.which` honour PATHEXT
and find a `git.cmd` first. These helpers make that split testable on every
OS: the failing tool is written OUTSIDE PATH and handed out only through
`shutil.which`, so a bare name still runs the real, healthy tool and the guard
passes for the wrong reason -- red until the site runs the resolved path.
Modelled on #356's `test_check_runs_the_git_which_resolves`.

`shutil.which` is patched on the `shutil` module itself, so every crew module
(and `crew_common.resolve_tool`) sees the same answer.
"""
import os
import shutil

import crew_fixtures

FAIL_SH = "#!/bin/sh\necho 'fatal: broken' >&2\nexit 128\n"
FAIL_CMD = "@echo off\r\necho fatal: broken 1>&2\r\nexit /b 128\r\n"


def _patch_which(monkeypatch, name, answer):
    real = shutil.which

    def which(cmd, *args, **kwargs):
        return answer if cmd == name else real(cmd, *args, **kwargs)
    monkeypatch.setattr(shutil, "which", which)


def which_only(monkeypatch, directory, name="git", sh_body=FAIL_SH, cmd_body=FAIL_CMD):
    """Write a failing `name` in `directory` (never on PATH) and make it the
    one `shutil.which(name)` answers; returns that path (the `.cmd` on
    Windows, the form a native `which` finds)."""
    shim = crew_fixtures.write_shim(directory, name, sh_body, cmd_body)
    resolved = shim + ".cmd" if os.name == "nt" else shim
    _patch_which(monkeypatch, name, resolved)
    return resolved


def which_none(monkeypatch, name="git"):
    """`shutil.which(name)` answers None: the tool does not resolve."""
    _patch_which(monkeypatch, name, None)


def failing_subcommand(sub, real=None):
    """(sh body, cmd body) for a git that fails `sub` and hands every other
    subcommand to the `real` git (default: the one on PATH now), so only the
    one probe under test breaks."""
    real = real or shutil.which("git")
    sh = (f"#!/bin/sh\nif [ \"$1\" = {sub} ]; then echo 'fatal: broken' >&2; exit 128; fi\n"
          f"exec '{real}' \"$@\"\n")
    cmd = (f"@echo off\r\nif \"%~1\"==\"{sub}\" (\r\n  echo fatal: broken 1>&2\r\n  exit /b 128\r\n)\r\n"
           f"\"{real}\" %*\r\nexit /b %ERRORLEVEL%\r\n")
    return sh, cmd
