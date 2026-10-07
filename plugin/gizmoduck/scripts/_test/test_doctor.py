"""Tests for gizmoduck.py's `doctor` command, specifically the NVD_API_KEY
report added for the ACME multi-scanner bootstrap work (2026-09-10 plan
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

import pytest

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


def _run_home(home):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run([sys.executable, str(_SCRIPT), "doctor"],
                          capture_output=True, text=True, check=False, env=env)


def test_an_empty_templates_directory_is_not_ok(tmp_path):
    # C-0008: `nuclei -update-templates` can exit 0 leaving only an empty
    # ~/nuclei-templates; doctor must not call that OK.
    (tmp_path / "nuclei-templates").mkdir()
    result = _run_home(tmp_path)
    assert "!! templates:" in result.stdout
    assert "holds no templates" in result.stdout
    assert result.returncode != 0


def test_a_templates_directory_with_a_template_is_ok(tmp_path):
    (tmp_path / "nuclei-templates" / "http").mkdir(parents=True)
    (tmp_path / "nuclei-templates" / "http" / "x.yaml").write_text("id: x\n")
    result = _run_home(tmp_path)
    assert "OK templates:" in result.stdout


# ---- tool lookup (L-0684) ---------------------------------------------------

def _doctor(env_updates):
    env = os.environ.copy()
    env.update(env_updates)
    return subprocess.run([sys.executable, str(_SCRIPT), "doctor"],
                          capture_output=True, text=True, check=False, env=env)


def test_doctor_reports_tool_home(tmp_path):
    home = tmp_path / "toolhome"
    missing = _doctor({"GIZMODUCK_HOME": str(home)})
    assert f"tool home: {home} (does not exist yet)" in missing.stdout
    home.mkdir()
    present = _doctor({"GIZMODUCK_HOME": str(home)})
    assert f"tool home: {home} (exists)" in present.stdout


def test_doctor_names_a_broken_override_without_changing_exit_status(tmp_path):
    good_pl = tmp_path / "nikto.pl"
    good_pl.write_text("# stand-in")
    gone = tmp_path / "no-such-zap"
    clean = _doctor({})
    result = _doctor({"GIZMODUCK_ZAP_HOME": str(gone), "GIZMODUCK_NIKTO_PL": str(good_pl)})
    assert f"!! GIZMODUCK_ZAP_HOME={gone} does not resolve - zap is disabled" in result.stdout
    assert f"OK GIZMODUCK_NIKTO_PL: {good_pl}" in result.stdout
    assert "GIZMODUCK_TESTSSL_SH" not in result.stdout  # unset variables are not listed
    assert result.returncode == clean.returncode


# --- C-0015.4: testssl needs hexdump, and `testssl --version` passes without it

def _run_path(tmp_path, tools):
    """doctor with PATH = one stub dir holding only `tools` (each a no-op)."""
    stub = tmp_path / "stubbin"
    stub.mkdir()
    for tool in tools:
        p = stub / tool
        p.write_text("#!/bin/sh\nexit 0\n", newline="\n")
        p.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(stub)
    env["HOME"] = str(tmp_path)
    for var in ("GIZMODUCK_MSYS2_BIN", "GIZMODUCK_TESTSSL_SH", "LOCALAPPDATA"):
        env.pop(var, None)
    return subprocess.run([sys.executable, str(_SCRIPT), "doctor"],
                          capture_output=True, text=True, check=False, env=env)


_posix = pytest.mark.skipif(os.name == "nt", reason="shell stubs on PATH")


@_posix
def test_testssl_without_hexdump_is_reported_missing(tmp_path):
    # Must-block: testssl.sh on PATH but no hexdump anywhere.
    result = _run_path(tmp_path, ["testssl.sh"])
    lines = [ln for ln in result.stdout.splitlines() if "testssl" in ln and "[" in ln]
    assert lines and lines[0].startswith("!! testssl"), result.stdout
    assert "hexdump" in lines[0], result.stdout
    assert "OK testssl" not in result.stdout
    assert "unavailable:" in result.stdout and "testssl" in result.stdout.split("unavailable:")[1]


@_posix
def test_testssl_with_hexdump_is_ok(tmp_path):
    # Must-allow: the same, with hexdump resolvable.
    result = _run_path(tmp_path, ["testssl.sh", "hexdump"])
    assert "OK testssl" in result.stdout, result.stdout
    assert "hexdump" not in result.stdout


@_posix
def test_missing_testssl_says_not_installed_not_hexdump(tmp_path):
    result = _run_path(tmp_path, [])
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("!! testssl"))
    assert "not installed" in line and "hexdump" not in line, line
