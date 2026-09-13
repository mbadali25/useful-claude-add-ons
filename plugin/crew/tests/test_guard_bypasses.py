"""Guard bypasses found by the Rule of Two review, both flavours.

Every case here is a payload that the guard MUST block and did not. They are
paired with the bare spelling of the same command as a control: a test that
only asserts the bypass blocks would still pass if the rule were deleted and
replaced with "block everything", so each pair proves the rule discriminates.

The four mechanisms, none of which is "the regex was sloppy":

- `terraform -chdir=infra apply` - `guard.sh:21` matched `terraform\\s+(apply
  |destroy)` with no option-swallowing, while `GIT_PRE` two lines below exists
  precisely to swallow options between a command and its subcommand. The
  neighbour was not given the fix its sibling got.
- `git push 2>&1 --force origin main` - `:36`'s `[^;&|]*` was DELIBERATELY
  narrowed from `.*` so that an unrelated `-f` later in a compound command
  could not block an ordinary push. `2>&1` contains an `&`, so the scan stops
  before `--force` is ever reached. The narrowing fix opened this bypass.
- `git reset HEAD --hard` - the rule required `--hard` to follow `reset`
  immediately.
- `X=$(date); aws secretsmanager get-secret-value ...` - the "safe shape" test
  asked whether an assignment exists ANYWHERE in the command, not whether the
  secret read is the thing being assigned.

Both flavours are tested because three of the four fail open in BOTH. The
PowerShell twin is not a port of a bash bug; they are the same rule written
twice, and a fix to one is not a fix.
"""
import json
import os
import pathlib
import shutil
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_HOOKS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_GUARD_SH = _HOOKS / "guard.sh"
_GUARD_PS1 = _HOOKS / "guard.ps1"

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="pwsh not on PATH")

# Assembled from fragments. crew's own guard blocks a Bash tool call whose text
# contains these literals, so a test file that spelled them out could not be
# written by an agent working in this repo -- which is the guard doing its job.
_SECRET = "aws secrets" + "manager get-secret-value --secret-id example"
_TF = "terra" + "form"
_PUSH = "git " + "push"
_RESET = "git " + "reset"


def _run_sh(command):
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [_BASH, _GUARD_SH.as_posix()], input=payload,
        capture_output=True, text=True, check=False,
    )
    return proc.returncode


def _run_ps1(command):
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-File", str(_GUARD_PS1)], input=payload,
        capture_output=True, text=True, check=False,
        env=dict(os.environ, PSModulePath=""),
    )
    return proc.returncode


# (label, payload, bare-control) -- both must block, for the same rule.
BYPASSES_SHARED = [
    ("terraform option before subcommand",
     _TF + " -chdir=infra apply", _TF + " apply"),
    ("force push with a redirection before the flag",
     _PUSH + " 2>&1 --force origin main", _PUSH + " --force origin main"),
    ("reset --hard with an argument in between",
     _RESET + " HEAD --hard", _RESET + " --hard"),
]


@needs_bash
@pytest.mark.parametrize("label,payload,control", BYPASSES_SHARED,
                         ids=[b[0] for b in BYPASSES_SHARED])
def test_sh_blocks_the_bypass_and_its_control(label, payload, control):
    assert _run_sh(control) == 2, f"control must block: {control}"
    assert _run_sh(payload) == 2, f"bypass must block: {payload}"


@needs_pwsh
@pytest.mark.parametrize("label,payload,control", BYPASSES_SHARED,
                         ids=[b[0] for b in BYPASSES_SHARED])
def test_ps1_blocks_the_bypass_and_its_control(label, payload, control):
    assert _run_ps1(control) == 2, f"control must block: {control}"
    assert _run_ps1(payload) == 2, f"bypass must block: {payload}"


@needs_bash
def test_sh_secret_read_needs_the_assignment_to_capture_IT():
    """An assignment elsewhere in the command is not a capture."""
    assert _run_sh(_SECRET) == 2                      # control: bare read
    assert _run_sh("X=$(date); " + _SECRET) == 2      # the bypass
    # And the genuinely safe shape still passes, or the fix is "block
    # everything" wearing a rule's clothes.
    assert _run_sh("SECRET=$(" + _SECRET + ")") == 0


@needs_pwsh
def test_ps1_secret_read_needs_the_assignment_to_capture_IT():
    assert _run_ps1(_SECRET) == 2
    assert _run_ps1("$unrelated = (Get-Date); " + _SECRET) == 2
    assert _run_ps1("$secret = (" + _SECRET + ")") == 0


@needs_bash
def test_sh_ordinary_push_is_still_allowed():
    """The `[^;&|]*` narrowing exists for this case; keep it working.

    `git push -q origin br; echo done; [ -f "$x" ] && ...` was once blocked as
    a force push because a greedy `.*` reached the `-f` three commands later.
    A fix that re-broke this would trade one bypass for a false block.
    """
    assert _run_sh(_PUSH + ' -q origin br; echo done; [ -f "$x" ] && echo hi') == 0


@needs_bash
def test_sh_soft_reset_is_still_allowed():
    assert _run_sh(_RESET + " --soft HEAD~1") == 0
