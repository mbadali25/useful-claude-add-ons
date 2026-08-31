r"""guard.ps1's command rules, which nothing covered until now.

hooks/scripts/_test/run-tests.sh exercises guard.sh and cannot run the .ps1
flavour, so every rule in guard.ps1 shipped on the strength of someone reading
it. That is the same asymmetry test_gates_powershell.py exists for, and it bit
in the same place: the git rules in both flavours required the subcommand to
sit immediately after `git`, so `git -C <path> push --force` was never blocked
on either. The bash bypass had a suite to catch it once the cases were written;
the PowerShell one had nothing.

Windows + pwsh only - this is the native-Windows half of the pair and there is
nothing to compare on a POSIX runner.

SABOTAGE-TEST THIS FILE before trusting it: restore the old adjacent-only
`\bgit\s+push\b` pattern in guard.ps1, run this, and confirm the bypass cases
go red.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_GUARD_PS1 = os.path.join(_ROOT, "hooks", "scripts", "guard.ps1")
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="guard.ps1 is the native-Windows flavour; needs Windows + pwsh",
)

# Every rule below is a general git/infra rule, not one tied to any repo. The
# paths are placeholders: what is under test is the command shape.
_MUST_BLOCK = [
    # force push, in the spellings a worktree-per-agent setup actually types
    "git push --force origin main",
    "git push -f origin main",
    "git push --force-with-lease origin main",
    "git -C /work/app push --force",
    "git -C /work/app push -f origin main",
    "git -c user.name=agent push --force",
    "git --git-dir=/work/app/.git --work-tree=/work/app push --force",
    # a force push carrying no --force token at all
    "git push origin +main",
    "git push origin +refs/heads/main:refs/heads/main",
    # history and worktree destruction, same option forms
    "git reset --hard HEAD~3",
    "git -C /work/app reset --hard origin/main",
    "git clean -fd",
    "git -C /work/app clean -fdx",
    # the non-git rules, so a regression in one does not hide behind the others
    "terraform apply -auto-approve",
    "terraform destroy",
    "DROP TABLE users",
    "TRUNCATE TABLE audit_log",
]

_MUST_ALLOW = [
    "git push origin feature/x",
    "git status",
    # --follow-tags contains a literal "-f" and is not a force push
    "git push --follow-tags origin main",
    "git -C /work/app push origin feature/x",
    "git -C /work/app status",
    'git commit -m "do not force push to main, use -f nowhere"',
    "git push origin refs/heads/main:refs/heads/main",
    "git clean -n",
    "git stash push -m wip",
    "terraform plan",
    "npm test",
]


def _guard(command):
    payload = {"tool_name": "PowerShell", "tool_input": {"command": command}}
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GUARD_PS1],
        input=json.dumps(payload), capture_output=True, text=True, check=False,
    )


@pytest.mark.parametrize("command", _MUST_BLOCK)
def test_guard_ps1_blocks(command):
    result = _guard(command)
    assert result.returncode == 2, (
        f"guard.ps1 let this through: {command!r} "
        f"(rc={result.returncode}, stderr={result.stderr!r})"
    )
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize("command", _MUST_ALLOW)
def test_guard_ps1_allows(command):
    result = _guard(command)
    assert result.returncode == 0, (
        f"guard.ps1 blocked ordinary work: {command!r} "
        f"(rc={result.returncode}, stderr={result.stderr!r})"
    )
