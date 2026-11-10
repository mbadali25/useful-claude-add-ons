"""The verify gate names a missing scope_report.py instead of a python error.

HISTORY, and why the file is still called this. It used to hold six cases:
five drove `verify-gate.ps1 -PrintPython`, pinning that file's own python
resolver against two live vectors - a `function python { ... }` in a user
profile winning `Get-Command` with an empty `.Source`, and the WindowsApps
App Execution Alias resolving as a real Application and opening the Microsoft
Store instead of running the script. Both were instances of this repository's
recurring defect: an unknown collapsing into a safe-looking value ("no python;
scope not checked") on a machine that had python installed.

L-0869 deleted verify-gate.ps1, so those five went with it. The resolver
itself did not disappear - it lives on as `Resolve-CrewPython` in
crew-hook.ps1:48, where the dispatcher uses it, and its coverage is
test_ps1_python_probe.py, test_python_probe_signals.py,
test_context_watch_python_resolver.py and test_map_audit_python_family.py.
All four assert the WindowsApps-stub hazard, so no vector lost its test.

What remains is the sixth case, which was always the bash half and always ran
on POSIX: the scope script's own precondition. verify-gate.sh tests
`-n "$SCOPE_PY"` AND `-f "$SCOPE_DIR/scope_report.py"`. Both flavours once
answered "(no python; scope not checked)" for a missing scope_report.py - a
different cause wearing the other one's sentence. Its own docstring records
that it was found by sabotage, and why that matters: collapsing the two
branches in verify-gate.sh left every `.ps1` case in this file green, because
none of them executed the bash flavour at all. That is now the only flavour
there is, which makes this case the whole file rather than its safety net.
"""
import os
import shutil
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

_BASH = crew_fixtures.resolve_bash()

_NEEDS_BASH = pytest.mark.skipif(_BASH is None, reason="needs bash")


def _fixture_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=repo, check=True,
                       capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=repo, check=True,
                   capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=repo,
                   check=True, capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "unverified.py").write_text("x = 1", encoding="utf-8")
    return repo


def _scripts_without_scope_report(tmp_path):
    """A copy of the whole hooks/scripts directory with scope_report.py
    removed.

    Copying the gate ALONE is not enough and the difference is not cosmetic:
    verify-gate.sh dot-sources _common.sh from its own directory, so a lone
    copy dies with "crew_incident_active: command not found" and never
    reaches the scope block at all -- while still printing a plausible
    "(no python; scope not checked)" line, because crew_py went missing with
    the rest. That would have been a test passing for entirely the wrong
    reason on a gate that never ran.
    """
    dst = tmp_path / "scripts"
    shutil.copytree(os.path.join(_ROOT, "hooks", "scripts"), dst)
    (dst / "scope_report.py").unlink()
    return dst


@_NEEDS_BASH
def test_the_bash_flavour_also_names_a_missing_scope_report(tmp_path):
    """Both flavours used to answer "(no python; scope not checked)" for a
    missing scope_report.py -- a different cause with a different fix, wearing
    the other one's sentence. Found by sabotage: collapsing the two branches in
    verify-gate.sh again left every .ps1 case in this file green, because none
    of them executed the bash flavour at all.
    """
    lonely = _scripts_without_scope_report(tmp_path)
    copied = lonely / "verify-gate.sh"

    repo = _fixture_repo(tmp_path)
    result = crew_fixtures.run_gate(
        [_BASH, str(copied)], input="{}", cwd=str(repo),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(repo)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert "scope_report.py not found" in result.stderr, (
        "verify-gate.sh must name the missing scope script rather than "
        "reporting it as an absent interpreter. stderr: " + result.stderr
    )
