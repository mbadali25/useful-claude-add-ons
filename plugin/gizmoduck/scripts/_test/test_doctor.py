"""Tests for gizmoduck.py's `doctor` command, specifically the NVD_API_KEY
report added for the THDDEV multi-scanner bootstrap work (2026-09-10 plan
Task 20).

dependency-check's first run downloads the entire NVD CVE corpus; without an
API key NIST rate-limits that sync to ~5 requests/30s, which is what one
operator ran into on a fresh machine - a first run stuck at ~50 minutes with
no visible progress, indistinguishable from a hang. `doctor` now reports
whether NVD_API_KEY is set so this reads as a documented, optional tradeoff
instead. Three things must hold no matter what: it is a gap, never a failure
(nuclei and its templates are the only things allowed to fail this check);
presence/absence must never change doctor's exit code; and the key's value
must never appear in doctor's output, not even partially.

Runs `gizmoduck.py` as a real subprocess, matching test_tickets_gate.py's
approach for this same script: gizmoduck.py is invoked by name, never
imported as a module by a caller, so the CLI surface (stdout, exit code) is
the contract worth pinning down, not cmd_doctor's internals.
"""
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "gizmoduck.py"

# Distinctive enough that an accidental substring match (e.g. against the
# literal env var name) can't produce a false pass.
_SECRET = "totally-fake-nvd-key-do-not-leak-9f3c1a"


def _run(*, with_key):
    env = os.environ.copy()
    if with_key:
        env["NVD_API_KEY"] = _SECRET
    else:
        env.pop("NVD_API_KEY", None)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "doctor"],
        capture_output=True, text=True, check=False, env=env,
    )


def test_reports_not_set_with_a_hint_when_the_env_var_is_absent():
    result = _run(with_key=False)
    assert "NVD_API_KEY: not set" in result.stdout
    assert "nvd.nist.gov/developers/request-an-api-key" in result.stdout


def test_reports_set_with_no_value_when_the_env_var_is_present():
    result = _run(with_key=True)
    assert "NVD_API_KEY: set" in result.stdout
    # The "set" line must not carry the unset-hint URL - a real branch, not
    # both messages printed regardless of state.
    assert "not set" not in result.stdout


def test_key_absence_or_presence_never_changes_the_exit_code():
    """The requirement that actually matters: dependency-check is optional
    tooling and NVD_API_KEY doubly so. doctor's pass/fail must be decided by
    nuclei and its templates alone, per the existing convention - whatever
    this machine's real toolchain state happens to be, both runs below must
    agree with each other.
    """
    without = _run(with_key=False)
    with_key = _run(with_key=True)
    assert without.returncode == with_key.returncode


def test_key_value_never_appears_in_doctor_output_at_all():
    result = _run(with_key=True)
    assert _SECRET not in result.stdout
    assert _SECRET not in result.stderr
