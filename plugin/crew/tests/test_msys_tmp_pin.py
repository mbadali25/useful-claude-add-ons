"""T-0110: a test that hands an MSYS child TMP/TEMP pointing at a FILE must
not turn `/tmp` into that file for every other Git-Bash process on the host.

Git for Windows mounts `/tmp` as `usertemp` (its etc/fstab), resolved from
the TMP/TEMP of whichever process CREATES the MSYS runtime's per-user,
per-installation shared mount table; every MSYS process started while that
region lives shares the answer. Under pytest-xdist on an otherwise idle
runner, `test_34d_ps1_a_temp_dir_failure_falls_back_to_crew_not_a_pipe`
(test_verify_gate_stop_gate_record.py) could be that creator, and other
workers' `sh`-flavour gates then failed with `bash.exe: warning: /tmp must
be a valid directory name` / `VERIFY GATE: cannot create temp file` - CI
jobs 109709668000 and 109307433677, each within ~2 s of that test passing
on another worker.

`crew_fixtures.msys_tmp_pinned` is the guard. Two checks here:

- behavioural, on a PRIVATE copy of Git's MSYS runtime (its own install
  path, so its own shared region, with no other process in it - on a dev
  box the real install always has long-lived bash processes holding the
  region, so the race cannot be staged against it): the hazard is live
  without the pin and gone with it;
- structural: every crew test that puts TMP/TEMP into a child environment
  does so inside `msys_tmp_pinned`.
"""
import ast
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

_TESTS = pathlib.Path(__file__).resolve().parent
_BASH = crew_fixtures.resolve_bash()
_PROBE = "if [ -d /tmp ]; then echo tmp-is-dir; else echo tmp-not-dir; fi"


def _private_msys(tmp_path):
    """A copy of the MSYS runtime `_BASH` belongs to, at a new path: bash,
    its DLLs and etc/fstab (which holds the `/tmp usertemp` line). Returns
    the copy's raw bash.exe."""
    git_root = pathlib.Path(_BASH).resolve().parents[1]
    src_bin = git_root / "usr" / "bin"
    fstab = git_root / "etc" / "fstab"
    if not (src_bin / "msys-2.0.dll").is_file() or not fstab.is_file():
        pytest.skip(f"{_BASH} is not a Git-for-Windows MSYS layout this test can copy")
    dst_bin = tmp_path / "msys" / "usr" / "bin"
    dst_bin.mkdir(parents=True)
    for entry in src_bin.iterdir():
        if entry.suffix.lower() == ".dll" or entry.name.lower() == "bash.exe":
            shutil.copy2(entry, dst_bin / entry.name)
    (tmp_path / "msys" / "etc").mkdir()
    shutil.copy2(fstab, tmp_path / "msys" / "etc" / "fstab")
    return str(dst_bin / "bash.exe")


def _poisoned_env(tmp_path):
    bogus = tmp_path / "not-a-directory"
    bogus.write_text("blocking TMP/TEMP", encoding="utf-8")
    return dict(os.environ, TMP=str(bogus), TEMP=str(bogus))


def _hold(bash, env):
    """Start an MSYS process under `env` and return once its runtime is up
    (so it has created or joined the shared region). Exits on stdin EOF."""
    # Outlives this function by design; `_release` closes and reaps it.
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [bash, "-c", "echo up; read -r _"], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True)
    assert proc.stdout.readline().strip() == "up", f"holder {bash} did not start"
    return proc


def _release(proc):
    proc.stdin.close()
    proc.wait(timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _probe(bash, env=None):
    done = subprocess.run([bash, "-c", _PROBE], env=env or dict(os.environ),
                          capture_output=True, text=True, check=False,
                          timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    return done.stdout.strip(), done.stderr.strip()


_WINDOWS_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("win") or _BASH is None,
    reason="`/tmp usertemp` and the shared MSYS mount table are Git for "
           "Windows behaviour; elsewhere /tmp is a real directory")


@_WINDOWS_ONLY
def test_unpinned_a_bogus_tmp_child_poisons_tmp_for_its_neighbours(tmp_path):
    """The premise the pin exists for. If this ever stops reproducing, the
    pinned test below passes vacuously - so this fails rather than skips."""
    bash = _private_msys(tmp_path)
    assert _probe(bash)[0] == "tmp-is-dir", "the private copy must start sane"

    poisoner = _hold(bash, _poisoned_env(tmp_path))
    try:
        out, err = _probe(bash)
    finally:
        _release(poisoner)

    assert out == "tmp-not-dir", (
        "a neighbour started while the bogus-TMP process held the region no "
        f"longer sees /tmp as a file (out={out!r} err={err!r}); re-check "
        "whether msys_tmp_pinned is still needed before trusting its test")
    assert "/tmp must be a valid directory name" in err
    assert _probe(bash)[0] == "tmp-is-dir", "the poison must end with its region"


@_WINDOWS_ONLY
def test_pinned_a_bogus_tmp_child_leaves_tmp_alone(tmp_path):
    bash = _private_msys(tmp_path)
    poisoned = _poisoned_env(tmp_path)

    with crew_fixtures.msys_tmp_pinned(bash, poisoned):
        poisoner = _hold(bash, poisoned)
        try:
            neighbour = _probe(bash)
            itself = _probe(bash, poisoned)
        finally:
            _release(poisoner)

    assert neighbour == ("tmp-is-dir", ""), neighbour
    assert itself == ("tmp-is-dir", ""), itself


# --- structural: every TMP/TEMP override runs inside the pin -----------------

_OVERRIDDEN = {"TMP", "TEMP"}


def _unpinned_overrides(source):
    """Names of functions in `source` that put TMP or TEMP into an
    environment - `dict(..., TMP=...)` or a `{"TMP": ...}` literal - without
    a `with ...msys_tmp_pinned(...)` block in the same function."""
    offenders = []
    for func in ast.walk(ast.parse(source)):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        overrides = pinned = False
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and any(
                    kw.arg in _OVERRIDDEN for kw in node.keywords):
                overrides = True
            elif isinstance(node, ast.Dict) and any(
                    isinstance(key, ast.Constant) and key.value in _OVERRIDDEN
                    for key in node.keys):
                overrides = True
            elif isinstance(node, ast.With):
                for item in node.items:
                    call = item.context_expr
                    target = getattr(call, "func", None)
                    name = getattr(target, "attr", None) or getattr(target, "id", None)
                    pinned = pinned or name == "msys_tmp_pinned"
        if overrides and not pinned:
            offenders.append(func.name)
    return offenders


def test_the_override_detector_sees_both_spellings_and_the_pin():
    unpinned = (
        "def a(p):\n    env = dict(os.environ, TMP=p)\n    run(env)\n"
        "def b(p):\n    run({'TEMP': p})\n"
        "def c(p):\n    run(dict(os.environ, PATH=p))\n"
    )
    pinned = (
        "def d(p):\n    env = dict(os.environ, TMP=p, TEMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env):\n        run(env)\n"
    )
    assert _unpinned_overrides(unpinned) == ["a", "b"]
    assert _unpinned_overrides(pinned) == []


# Exempt by exact name, with the reason: this module's own helper poisons
# only the PRIVATE MSYS copy above, whose shared region no other process on
# the host can join.
_EXEMPT = {"test_msys_tmp_pin.py::_poisoned_env"}


def test_every_crew_test_that_overrides_tmp_does_it_inside_the_pin():
    found = [
        f"{path.name}::{name}"
        for path in sorted(_TESTS.glob("*.py"))
        for name in _unpinned_overrides(path.read_text(encoding="utf-8"))
    ]
    assert _EXEMPT <= set(found), "stale exemption: " + repr(_EXEMPT - set(found))
    offenders = [name for name in found if name not in _EXEMPT]
    assert offenders == [], (
        "these tests hand a child TMP/TEMP; on Windows that child can decide "
        "/tmp for every Git-Bash process on the host (see this module's "
        "docstring). Run the child inside crew_fixtures.msys_tmp_pinned: "
        + ", ".join(offenders))
