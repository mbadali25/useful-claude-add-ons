"""The record sync's payload never rides on argv, and a dead producer is a failure (L-0905).

`verify-gate.sh` used to hand the matched-rule JSON to `python -c` as one argv
element. A large map overflows that: a single argument is capped at 128 KiB on
Linux and the whole command line at 32,767 characters on Windows. The exec
failed, the sync stage read an empty stdin and exited 0, and the verified marker
advanced on a record that was never written.
"""
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
from test_verify_gate_stop_budget import _FLAVOURS, _repo, _run

_ROOT = context._ROOT  # pylint: disable=protected-access
_RECORD_PY = os.path.join(_ROOT, "hooks", "scripts", "verify_record.py")

_RULES = 400
_PAD = 600


def _big_map():
    rules = []
    for index in range(_RULES):
        command = f"echo rule-{index} # {'x' * _PAD}"
        rules.append({"paths": ["a.py"], "seconds": 90, "run": [command],
                      "why": "chronic: persisted by name, never run, so the suite is fast"})
    return {"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_payload_over_the_argv_limit_reaches_the_record(flavour, tmp_path):
    """The matched-rule JSON here is about 250 KB, over a 128 KiB argument and
    over a 32 KiB Windows command line; every rule must still be recorded."""
    root = _repo(tmp_path, _big_map())

    result = _run(flavour, root)

    assert "Argument list too long" not in result.stderr, result.stderr[-2000:]
    record = json.loads((root / ".crew" / ".verify-gate.record.json")
                        .read_text(encoding="utf-8"))
    assert len(record["rules"]) == _RULES, (len(record["rules"]), result.stderr[-2000:])


def _shim_python(directory):
    """A `python3` first on PATH that delegates to the real interpreter for
    every call except the sync's stage-1 producer. The producer is told apart
    by the last statement of its script. The real interpreter runs as a CHILD
    and prints the full valid payload, then the shim exits 126 itself: exec
    would return the real status (0) and the test would pass on unfixed code.
    The gate's interpreter probe prints `sys.executable`, which would resolve
    past the shim to the real path, so the shim answers that probe with its own
    path and the gate then runs every `$PY` call through it."""
    real = shutil.which("python3") or sys.executable
    shim = directory / "python3"
    shim.write_text(
        "#!/bin/bash\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in\n"
        "    *sys.executable*) printf '%s\\n' \"$0\"; exit 0 ;;\n"
        "    *'\"cmd_log\": cmd_log}))'*)\n"
        "      out=$('" + real + "' \"$@\")\n"
        "      printf '%s\\n' \"$out\"\n"
        "      exit 126 ;;\n"
        "  esac\n"
        "done\n"
        "exec '" + real + "' \"$@\"\n", encoding="utf-8", newline="\n")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


@pytest.mark.skipif(
    os.name == "nt",
    reason="bin/bash.exe prepends /mingw64/bin:/usr/bin ahead of the PATH it is handed, so a shim dir placed "
           "first is never reached, and os.chmod cannot mark the shim executable there (see "
           "crew_fixtures.resolve_bash_no_prepend). Not attempted on Windows.")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_failed_sync_producer_does_not_advance_the_marker(flavour, tmp_path):
    """MUST-BLOCK. The producer prints a valid payload and then exits 126, as
    an exec that died would: the stage after it still reads input and exits 0,
    so only a check of every pipeline stage keeps the marker where it was."""
    verify_map = {"version": 1, "rules": [
        {"paths": ["a.py"], "seconds": 1, "run": ["echo RAN-ok"], "why": "passes"}],
        "default": [], "unmapped": "ignore"}
    root = _repo(tmp_path, verify_map)
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    _shim_python(shim_dir)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               PATH=str(shim_dir) + os.pathsep + os.environ["PATH"])

    result = crew_fixtures.run_gate(
        [crew_fixtures.resolve_bash(), os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")],
        input="{}", cwd=str(root), env=env, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    assert "RAN-ok" in result.stderr, result.stderr
    assert not (root / ".crew" / ".verify-verified-at").exists(), (
        "the marker advanced after the sync producer died. " + result.stderr)
    assert "NOT advancing the marker" in result.stderr, result.stderr


def test_an_empty_sync_payload_is_refused(tmp_path):
    """verify_record.py sync on an empty stdin exits nonzero and says why."""
    result = subprocess.run([sys.executable, _RECORD_PY, "sync"], input="", cwd=str(tmp_path),
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    assert result.returncode != 0
    assert "refused an empty payload" in result.stderr, result.stderr


_GATE_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")


def test_the_rule_child_redirects_stdin_from_devnull_in_the_run_line():
    """MUST-ALLOW guard. The run line that starts a rule keeps `</dev/null`."""
    with open(_GATE_SH, encoding="utf-8") as handle:
        text = handle.read()

    run_lines = [ln for ln in text.splitlines()
                 if 'eval "$c"' in ln and "RULE_DONE_FILE" in ln]

    assert run_lines, "the rule run line was not found"
    assert all("</dev/null" in ln for ln in run_lines), run_lines


@pytest.mark.skipif(os.name == "nt", reason="fd 0 is the null device on POSIX only")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_rule_child_redirects_stdin_from_devnull(flavour, tmp_path):
    """On POSIX, fd 0 of a rule child is the null device."""
    probe = "import os,sys;sys.exit(0 if os.path.samestat(os.fstat(0), os.stat('/dev/null')) else 1)"
    verify_map = {"version": 1, "rules": [
        {"paths": ["a.py"], "seconds": 1,
         "run": [f'python3 -c "{probe}" || python -c "{probe}"'],
         "why": "stdin is /dev/null"}],
        "default": [], "unmapped": "ignore"}
    root = _repo(tmp_path, verify_map)

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
