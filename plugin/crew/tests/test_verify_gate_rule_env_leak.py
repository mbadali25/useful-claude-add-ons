"""verify-gate.ps1 hands each rule's command text to bash through an env
var, `CREW_VERIFY_RULE_CMD` (and the output-capture path through
`CREW_VERIFY_RULE_OUT`) -- deliberately, per the comment above the wrapper
script in verify-gate.ps1: `eval` inherits positional parameters, so those
cannot carry the value, and interpolating an arbitrary rule command
directly into a script string is exactly the injection shape everywhere
else in this file avoids. An env var is the remaining option.

But an env var bash sets for ITS OWN wrapper is still an env var the RULE's
own `eval`'d command inherits, for the whole time it runs -- a rule that
does `env | grep CREW_VERIFY`, or a script it shells out to that dumps its
own environment for diagnostics, would see its own source text and output
path as if they were legitimate input. `verify-gate.sh` never had this
leak: its equivalent (`RULE_OUT_FILE`, `c`) are plain, un-exported shell
variables the eval'd rule never inherits at all -- that is the parity bar
this file pins BOTH flavours to.

Fixed in verify-gate.ps1's wrapper script: the two values are copied into
local (non-exported) shell variables first, then the two env vars are
`unset` from bash's own environment, before `eval` runs.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_PY = "'" + sys.executable.replace("\\", "/").replace("'", "'\\''") + "'"

# Exits 0 only if NEITHER carrier var is visible inside the rule's own
# process. Checked by name, not merely "empty": an unset var and an env var
# set to "" both read as falsy in a shell `[ -n ... ]` test but are NOT the
# same thing to `os.environ` -- `in` is the one check that cannot be
# satisfied by an empty-but-present leak.
_ENV_LEAK_CHECK = (
    f'{_PY} -c "import os, sys; '
    "leaked = [v for v in ('CREW_VERIFY_RULE_CMD', 'CREW_VERIFY_RULE_OUT') "
    "if v in os.environ]; "
    "sys.exit(0 if not leaked else 7)\""
)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, run_entry):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "changed.py").write_text("x = 1\n", encoding="utf-8")
    verify = {"version": 1, "rules": [
        {"paths": ["changed.py"], "reach": "local", "run": [run_entry]}
    ], "always": [], "default": [], "unmapped": "warn"}
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    return root


def _run(cmd, root):
    return crew_fixtures.run_gate(
        cmd, input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )


@pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gate is the native-Windows flavour; needs Windows + pwsh",
)
def test_ps1_rule_never_sees_its_own_command_carrier_env_vars(tmp_path):
    """Sabotage: reverting the wrapper script to a bare
    `eval "$CREW_VERIFY_RULE_CMD" > "$CREW_VERIFY_RULE_OUT" 2>&1 </dev/null`
    (no unset) makes this rule see both vars in its own environment and
    exit 7 -- RED via the gate's own VERIFY FAILED reporting, not a silent
    pass."""
    root = _repo(tmp_path, _ENV_LEAK_CHECK)

    result = _run([_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1], root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED" not in result.stderr, result.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_sh_rule_never_sees_a_command_carrier_env_var_either(tmp_path):
    """The parity half: verify-gate.sh never had this leak (RULE_OUT_FILE
    and `c` are plain shell variables, never exported), so this passes
    without needing any change there -- pinned here so a future refactor of
    the .sh side that starts exporting its own equivalent gets caught by
    the same check."""
    root = _repo(tmp_path, _ENV_LEAK_CHECK)

    result = _run([_BASH, _VERIFY_SH], root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED" not in result.stderr, result.stderr
