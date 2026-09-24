"""verify-gate.ps1 runs every rule in ONE PowerShell process, and that leaked.

Measured 2026-09-13 on aws-managed-services (T-0019 there): the gate failed
at every Stop with `bash -n scripts/ci_changed.sh`, pytest "no tests ran" and
ruff `E902 cannot find the path` for files that exist. Rule 11 of that run's
ordered list was `cd drata-insights/frontend && npm test`. `Invoke-Expression`
runs in the gate's own scope, so `cd` moved the gate's working directory and
rules 12-27 ran from the wrong place. Three more things fell out of the same
loop, each confirmed with a two-line pwsh experiment:

- `$ok = $?` after Invoke-Expression is Invoke-Expression's OWN status. A
  failed `cd` and a command that does not exist both came back ok=True with
  LASTEXITCODE=0, so six rules of that run silently passed.
- `FDM_MODULE=x bash case.sh` is bash syntax the sh twin evals natively; in
  PowerShell it is a command named `FDM_MODULE=x`, which does not exist, and
  by the point above that read as a pass.
- The lock's `PowerShell.Exiting` handler compared a RELATIVE token path, so
  once the cwd had moved it found no token, kept the lock, and the next Stop
  within the 700 s TTL was silently ungated after a failing one.

verify-gate.sh has none of these: it evals each rule inside `$(...)`, which
is a subshell, so a `cd` cannot leak and the exit status is the rule's own.
This file pins the .ps1 flavour to the same contract.

Windows + pwsh only, as test_gates_powershell.py: this is the native-Windows
half of the pair and there is nothing to compare on a POSIX runner.
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
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PWSH = shutil.which("pwsh")
# The interpreter running this suite, quoted for a BASH command line.
#
# It used to be quoted for PowerShell (`& 'C:\...\python.exe'`), because the
# gate evaluated each rule with Invoke-Expression. It no longer does: rules are
# handed to bash, which is the only way the .ps1 can honour the same contract
# as verify-gate.sh, whose rules have always been bash. A rule written in
# PowerShell syntax could never have run on the sh side, so these fixtures were
# testing a rule shape that only half the matched pair could execute.
# Backslashes are turned into forward slashes because Git Bash execs that form
# and treats a backslash inside single quotes as a literal character.
_PY = "'" + sys.executable.replace("\\", "/").replace("'", "'\\''") + "'"

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gate is the native-Windows flavour; needs Windows + pwsh",
)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _py_exit_unless(condition, code):
    """A rule that exits `code` unless the Python expression is true."""
    return f'{_PY} -c "import os, sys; sys.exit(0 if ({condition}) else {code})"'


def _repo(tmp_path, rules):
    """A committed repo with one untracked file per rule, named so that
    `Sort-Object -Unique` on the changed set orders the rules as given:
    rule N fires on `rN.py`. The rules are the whole test."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "sub").mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text(".crew/\n", encoding="utf-8")
    (root / "sub" / "marker.txt").write_text("in sub\n", encoding="utf-8")
    (root / "top.txt").write_text("at root\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    verify = {"version": 1, "rules": [], "always": [], "default": [], "unmapped": "warn"}
    for n, run in enumerate(rules, 1):
        (root / f"r{n}.py").write_text("x = 1\n", encoding="utf-8")
        # reach: local - this whole file tests `cd`/cwd mechanics, which the
        # Stop gate's reach scanner (Codex round 4) now defers unconditionally
        # on its own terms (a `cd` anywhere in the command). These fixtures
        # are exercising a real, supported rule shape deliberately, not an
        # undeclared reach - declaring it here is the same thing a real
        # verify.json author would do for a genuine cd-prefixed rule.
        verify["rules"].append({"paths": [f"r{n}.py"], "reach": "local", "run": [run]})
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    return root


def _run_verify(root):
    return crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
        input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )


def _lock(root):
    return root / ".crew" / ".verify-gate.lock"


def test_a_cd_rule_does_not_move_the_rules_after_it(tmp_path):
    """The aws-managed-services failure in miniature: a `cd sub && ...` rule
    followed by a rule that only works from the repo root."""
    root = _repo(tmp_path, [
        "cd sub && " + _py_exit_unless("os.path.exists('marker.txt')", 5),
        _py_exit_unless("os.path.exists('top.txt')", 6),
    ])

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED" not in result.stderr


def test_an_at_prefixed_argument_is_not_a_powershell_splat(tmp_path):
    """`--grep @flow` is an ordinary argument to every tool that takes it, and
    it is NOT valid PowerShell: `@flow` is a splat of the variable `$flow`.

    Measured on TheSelectSource (PR #151): under Invoke-Expression this rule
    failed with "The variable '$flow' cannot be retrieved because it has not
    been set" - the rule never ran at all, and the gate reported a failure
    whose cause was PowerShell's parser rather than anything in the repo.

    This is the half of the fold that #153's own cases do not cover: the cwd
    and status findings are reproducible under either design, but this one is
    only fixed by handing the rule to bash. If someone reverts to
    Invoke-Expression, this is the test that says so.
    """
    root = _repo(tmp_path, [
        # python -c "..." --grep @flow  ->  argv is ['-c', '--grep', '@flow']
        _py_exit_unless("sys.argv[2] == '@flow'", 7) + " --grep @flow",
    ])

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "cannot be retrieved" not in result.stderr
    assert "VERIFY FAILED" not in result.stderr


def test_a_failed_cd_is_a_failed_rule(tmp_path):
    """`cd nowhere && anything` never runs `anything`; the sh twin reports
    that as the rule failing. So must this flavour, instead of reading
    Invoke-Expression's own success as the rule's."""
    root = _repo(tmp_path, ["cd does-not-exist && " + _py_exit_unless("True", 0)])

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED: cd does-not-exist" in result.stderr


def test_a_command_that_does_not_exist_is_a_failed_rule(tmp_path):
    root = _repo(tmp_path, ["crew-no-such-command-9f3a --flag"])

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED: crew-no-such-command-9f3a" in result.stderr


def test_an_env_prefix_rule_sets_the_variable_for_that_rule_only(tmp_path):
    """`VAR=value command` is how verify.json rules are written for the sh
    twin (`FDM_MODULE=drata-insights bash _verify/cases/...`). The variable
    must reach the command, and must be gone again for the next rule."""
    root = _repo(tmp_path, [
        "CREW_RULE_T=drata CREW_RULE_U='two words' "
        + _py_exit_unless("os.environ.get('CREW_RULE_T') == 'drata' and "
                          "os.environ.get('CREW_RULE_U') == 'two words'", 7),
        _py_exit_unless("'CREW_RULE_T' not in os.environ and 'CREW_RULE_U' not in os.environ", 8),
    ])

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"


def test_an_env_prefix_does_not_hide_a_failing_command(tmp_path):
    root = _repo(tmp_path, ["CREW_RULE_T=1 " + _py_exit_unless("False", 9)])

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED: CREW_RULE_T=1" in result.stderr


def test_an_env_prefix_still_resolves_a_leading_bash(tmp_path):
    """The bash resolver keys on a LEADING `bash`; the prefix must be peeled
    off before that test or `FDM_MODULE=x bash case.sh` goes to PATH lookup,
    which on this machine is the WSL launcher (test_verify_gate_bash_resolver)."""
    root = _repo(tmp_path, ["CREW_RULE_T=1 bash -c 'test \"$CREW_RULE_T\" = 1'"])

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"


def test_a_failing_rules_stderr_reaches_the_report(tmp_path):
    """The gate's report is the last 25 lines a failing rule wrote. A case
    script writes its FAIL lines to stderr; a `2>&1` placed on
    Invoke-Expression itself dropped them (measured 2026-09-13: `VERIFY
    FAILED: ... frontend-dist-matches.sh` followed by nothing), which is a
    verdict with no evidence. The redirect has to sit on the rule's block."""
    root = _repo(tmp_path, [
        f'{_PY} -c "import sys; sys.stderr.write(\'CREW-STDERR-EVIDENCE\\n\'); sys.exit(11)"',
    ])

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "VERIFY FAILED" in result.stderr
    assert "CREW-STDERR-EVIDENCE" in result.stderr


def test_the_lock_is_released_after_a_cd_rule_and_a_failure(tmp_path):
    """test_verify_gate_lock.py proves cleanup on a plain exit 2. This is the
    measured leak: cwd moved by a rule, then a failing rule, then a lock left
    behind that made the next Stop exit 0 silently for up to 700 s."""
    root = _repo(tmp_path, [
        "cd sub && " + _py_exit_unless("True", 0),
        _py_exit_unless("False", 10),
    ])

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert not _lock(root).exists(), "the holder leaked its lock after the cwd moved"


def test_the_verified_marker_lands_in_the_repo_after_a_cd_rule(tmp_path):
    """Write-CrewVerified writes `.crew/.verify-verified-at` by a relative
    path. With the cwd moved it would land in the subdirectory (or nowhere),
    and the next turn would re-verify everything since the merge-base."""
    root = _repo(tmp_path, ["cd sub && " + _py_exit_unless("True", 0)])

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert (root / ".crew" / ".verify-verified-at").exists()
    assert not (root / "sub" / ".crew").exists()
