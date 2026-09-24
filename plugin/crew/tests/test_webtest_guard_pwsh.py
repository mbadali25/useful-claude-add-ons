"""Runs `_test/webtest-guard.ps1`, the PowerShell driver for `webtest_guard.py`.

Not Windows-only, unlike `test_gates_powershell.py`: the driver calls the
Python guard, which is the same on every platform, so any host with pwsh can
run it. Skipped when no pwsh resolves. pwsh is looked up by absolute path as
well as on PATH, because it is not on Git Bash's PATH (CLAUDE.md landmine).
"""
import os
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_DRIVER = os.path.join(context._ROOT, "hooks", "scripts", "_test",  # pylint: disable=protected-access
                       "webtest-guard.ps1")
_CANDIDATES = ("C:/Program Files/PowerShell/7/pwsh.exe", "/snap/bin/pwsh", "/usr/bin/pwsh",
               "/usr/local/bin/pwsh", "/opt/microsoft/powershell/7/pwsh")


def _pwsh():
    found = shutil.which("pwsh")
    return found or next((p for p in _CANDIDATES if os.path.isfile(p)), None)


@pytest.mark.skipif(_pwsh() is None, reason="no pwsh on this host")
def test_powershell_driver_passes_every_must_block_and_must_allow_case():
    done = subprocess.run([_pwsh(), "-NoProfile", "-NonInteractive", "-File", _DRIVER],
                          capture_output=True, text=True, check=False, timeout=300,
                          stdin=subprocess.DEVNULL)

    assert (done.returncode, "RESULT: 9 passed, 0 failed" in done.stdout) == (0, True), (
        done.stdout + done.stderr)
