"""Tests for the context-watch Stop hook: threshold detection, the
autoWrapUp instruction branch, and the three loop-safety layers.

context-watch has no Python module -- it is a Stop hook shipped as a matched
pair of scripts (bash + native PowerShell) invoked as a subprocess by Claude
Code. These tests run both flavours the same way Claude Code does: JSON on
stdin, exit code and stderr as the contract.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
# Forward slashes only: MSYS bash.exe re-parses its own argv and eats bare
# backslashes in a native Windows path passed straight through subprocess.
_SH = (_ROOT + "/hooks/scripts/context-watch.sh").replace("\\", "/")
_PS1 = _ROOT + "/hooks/scripts/context-watch.ps1"


def _resolve_bash():
    """Find a bash that works when spawned directly by python's subprocess.

    Git for Windows ships bash.exe in two places. usr/bin/bash.exe is the
    raw MSYS binary: launched from a non-MSYS parent (python.exe here,
    rather than another MSYS shell) it fails to resolve its own mount
    table and cannot open ANY path, including its own script argument --
    confirmed by running a trivial one-line script and getting "No such
    file or directory" back for a file that demonstrably exists. bin/
    bash.exe is a launcher shim that bootstraps the MSYS environment
    correctly first. Prefer the shim when this looks like a Git for
    Windows install and it is present.
    """
    found = shutil.which("bash")
    if not found:
        return None
    parts = pathlib.Path(found).parts
    lower = [p.lower() for p in parts]
    if "usr" in lower and "bin" in lower:
        root = pathlib.Path(*parts[:lower.index("usr")])
        shim = root / "bin" / "bash.exe"
        if shim.exists():
            return str(shim)
    return found


_BASH = _resolve_bash()
_HAS_BASH = _BASH is not None
_HAS_PWSH = shutil.which("pwsh") is not None

FLAVORS = [f for f, have in (("sh", _HAS_BASH), ("ps1", _HAS_PWSH)) if have]

by_flavor = pytest.mark.parametrize("flavor", FLAVORS)

# budgetTokens=100, warnAt=0.8 -> the threshold sits at 80 estimated tokens.
# EST = bytes/4*0.75, so EST=80 needs bytes ~= 427. 500 bytes clears it
# (EST=93.75, pct=0.9375); 100 bytes stays well under it (EST=18.75, pct=0.1875).
_OVER_BYTES = 500
_UNDER_BYTES = 100


def _run(flavor, root, transcript_path, stop_hook_active=False):
    payload = json.dumps({
        "transcript_path": str(transcript_path),
        "cwd": str(root),
        "stop_hook_active": stop_hook_active,
    })
    if flavor == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", _PS1]
    return subprocess.run(
        cmd, input=payload, cwd=str(root),
        capture_output=True, text=True, check=False,
    )


def _transcript(root, num_bytes):
    path = root / "transcript.jsonl"
    path.write_bytes(b"x" * num_bytes)
    return path


def _config(auto_wrap_up=None):
    cfg = {"warnAt": 0.8, "budgetTokens": 100, "handoffPath": ".work/HANDOFF.md"}
    if auto_wrap_up is not None:
        cfg["autoWrapUp"] = auto_wrap_up
    return {"context": cfg}


def test_flavors_are_discoverable():
    # If neither interpreter is on PATH, the parametrized tests below
    # silently collect zero cases and the suite still reports green.
    assert FLAVORS, "neither bash nor pwsh is on PATH; cannot test context-watch"


@by_flavor
def test_below_threshold_emits_nothing(flavor, tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _UNDER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_above_threshold_auto_wrap_up_false_emits_existing_warning_only(
        flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=False), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "write the handoff note to" in result.stderr
    assert "Reach a stopping point" not in result.stderr
    assert (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_above_threshold_default_config_behaves_like_auto_wrap_up_false(
        flavor, tmp_path):
    # autoWrapUp is absent from the fixture's config entirely -- default false.
    root = crew_fixtures.make_repo(tmp_path, config=_config(), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "write the handoff note to" in result.stderr
    assert "Reach a stopping point" not in result.stderr


@by_flavor
def test_above_threshold_auto_wrap_up_true_emits_wrap_up_instruction(
        flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript)
    assert result.returncode == 2, result.stderr
    assert "Reach a stopping point" in result.stderr
    assert "finish or safely abandon the change in flight" in result.stderr
    assert ".work/HANDOFF.md" in result.stderr
    assert "update the ticket" in result.stderr
    assert "ready to clear" in result.stderr
    assert "Do not start new work" in result.stderr
    assert (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_stop_hook_active_emits_nothing_even_above_threshold(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    result = _run(flavor, root, transcript, stop_hook_active=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".handoff-requested").exists()


@by_flavor
def test_once_per_session_marker_still_gates_repeats(flavor, tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config=_config(auto_wrap_up=True), git=False)
    transcript = _transcript(root, _OVER_BYTES)
    first = _run(flavor, root, transcript)
    assert first.returncode == 2, first.stderr
    second = _run(flavor, root, transcript)
    assert second.returncode == 0, second.stderr
    assert second.stderr.strip() == "", second.stderr
