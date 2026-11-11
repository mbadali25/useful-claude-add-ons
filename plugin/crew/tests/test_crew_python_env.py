"""CREW_PYTHON is honoured by the shell guards, and a missing guard script fails closed.

Two things, both found on Windows hosts (L-0868 follow-up):

1. `crew-hook.sh` / `crew-hook.ps1` resolve and run an interpreter, then export it
   as CREW_PYTHON for the guards the dispatcher starts. The guards used to walk
   PATH and probe every candidate again, which on Windows costs a process tree per
   candidate and, under load, is what timed them out. `crew_py`, `crew_py_strict`
   and role-write-guard.sh's `_resolve_role_write_python` now take a VALIDATED
   CREW_PYTHON first: an absolute path (Windows `C:\\..` or POSIX), a regular
   executable file, named like an interpreter. Anything else is ignored and the
   old walk runs, so a bad value can never select a program.
2. `"$PY" "$(crew_native_path "$DIR/x.py")"` handed python an EMPTY operand when
   the substitution produced nothing, and python then ran the current directory
   (`can't find '__main__' module in '<repo>'`). `crew_py_script` refuses an
   empty or missing script, and every guard names the failure and fails CLOSED.

Every case is a must-block / must-allow pair, and the byte-identical resolver
copies are pinned to each other.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from _train_base import TRAIN_BASE, seed_train_base
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = pathlib.Path(_ROOT) / "hooks" / "scripts"
_COMMON = _SCRIPTS / "_common.sh"
_RWG = _SCRIPTS / "role-write-guard.sh"

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

_FUNCS = [
    (_COMMON, "crew_py() {", "crew_py"),
    (_COMMON, "crew_py_strict() {", "crew_py_strict"),
    (_RWG, "_resolve_role_write_python() {", "_resolve_role_write_python"),
]
_IDS = [f[2] for f in _FUNCS]


def _raw_function(path, header):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, header + " is gone from " + str(path)
    end = src.find("\n}\n", start)
    assert end != -1
    return src[start:end + 3]


def _block(path, header):
    body = _raw_function(path, header)
    match = re.search(r"# BEGIN CREW_PYTHON.*?# END CREW_PYTHON", body, re.S)
    assert match, header + " lost its CREW_PYTHON block"
    return [ln.strip() for ln in match.group(0).splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _python_free(tmp_path, keep=()):
    tools = tmp_path / "bin-no-python"
    tools.mkdir()
    crew_fixtures.link_path_dirs(
        tools, skip=lambda n: n.startswith(("python", "py", "cygpath")) and n not in keep)
    return str(tools)


def _stub(directory, name="python3"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    # Never run by these tests when CREW_PYTHON is honoured: that is the point.
    path.write_text("#!/bin/sh\nexit 97\n", encoding="ascii", newline="\n")
    os.chmod(path, 0o755)
    return path


def _posix(path):
    text = str(path)
    if not (len(text) > 1 and text[1] == ":"):
        return text
    out = subprocess.run([_BASH, "-c", 'cygpath -u "$1"', "_", text],
                         capture_output=True, text=True, check=False).stdout.strip()
    return out or crew_fixtures.windows_to_posix(text)


def _call(tmp_path, func, creg, path_dirs, extra_env=None, prelude=""):
    """Run `func` (raw source from the shipped file) with CREW_PYTHON=creg."""
    path, header, name = func
    script = tmp_path / "call.sh"
    script.write_text(prelude + _raw_function(path, header) + "\n" + name + "\n",
                      encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env.pop("CREW_PYTHON", None)
    env["PATH"] = os.pathsep.join(path_dirs)
    if creg is not None:
        env["CREW_PYTHON"] = creg
    env.update(extra_env or {})
    proc = subprocess.run([_BASH, _posix(script)], capture_output=True, text=True,
                          env=env, check=False, timeout=120)
    return proc.returncode, proc.stdout.strip().replace("\r", ""), proc.stderr


# --- the three resolver copies cannot drift ---------------------------------------


def test_the_three_crew_python_blocks_are_identical():
    blocks = [_block(p, h) for p, h, _ in _FUNCS]
    assert blocks[0] == blocks[1] == blocks[2], blocks


# --- MUST ALLOW: a valid CREW_PYTHON is returned without any probe ---------------


@needs_bash
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_must_allow_a_posix_crew_python_without_a_probe(tmp_path, func):
    stub = _stub(tmp_path / "elsewhere")
    code, out, err = _call(tmp_path, func, _posix(stub), [_python_free(tmp_path)])
    assert (code, out) == (0, _posix(stub)), err


@needs_bash
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_must_allow_a_crlf_terminated_value(tmp_path, func):
    stub = _stub(tmp_path / "elsewhere")
    code, out, err = _call(tmp_path, func, _posix(stub) + "\r", [_python_free(tmp_path)])
    assert (code, out) == (0, _posix(stub)), err


@needs_bash
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_must_allow_a_windows_path_converted_with_cygpath(tmp_path, func):
    """crew-hook.ps1 exports `C:\\...`. A fake cygpath proves the conversion is
    asked for with -u and its answer, not the raw string, is what is checked."""
    stub = _stub(tmp_path / "elsewhere", "python.exe")
    # A shell function, found by `command -v cygpath` ahead of any binary.
    prelude = f"cygpath() {{ [ \"$1\" = -u ] || return 3; printf '%s' '{_posix(stub)}'; }}\n"
    code, out, err = _call(tmp_path, func, "C:\\fake\\Scripts\\python.exe",
                           [_python_free(tmp_path)], prelude=prelude,
                           extra_env=
                           # MSYS rewrites a Windows-looking env value on its way
                           # into bash; keep it as crew-hook.ps1 writes it so the
                           # block's own conversion is what is exercised.
                           {"MSYS2_ENV_CONV_EXCL": "CREW_PYTHON"})
    assert (code, out) == (0, _posix(stub)), err


@needs_bash
@pytest.mark.skipif(os.name != "nt", reason="needs a real Windows path to convert")
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_must_allow_a_windows_path_converted_by_hand_without_cygpath(tmp_path, func):
    """crew 1.2.115: the drive path is converted without a fork, `C:\\x` ->
    `/c/x`, and cygpath is asked only when that names no executable file. A
    cygpath that fails loudly proves it is never asked here."""
    stub = _stub(tmp_path / "elsewhere", "python.exe")
    prelude = "cygpath() { echo CYGPATH-ASKED >&2; return 3; }\n"
    code, out, err = _call(tmp_path, func, str(stub), [_python_free(tmp_path)], prelude=prelude,
                           extra_env={"MSYS2_ENV_CONV_EXCL": "CREW_PYTHON"})
    # Not _posix(): cygpath -u answers /tmp/.. for the temp dir, a mount of the
    # same folder; the hand conversion names it by its drive.
    text = str(stub)
    want = "/" + text[0].lower() + text[2:].replace("\\", "/")
    assert (code, out.lower()) == (0, want.lower()), err
    assert "CYGPATH-ASKED" not in err, err


# --- MUST BLOCK (ignored, fall back to the walk, which finds nothing) -----------


def _bad_values(tmp_path):
    good = _stub(tmp_path / "ok")
    not_exec = tmp_path / "noexec" / "python3"
    not_exec.parent.mkdir()
    not_exec.write_text("#!/bin/sh\n", encoding="ascii", newline="\n")
    os.chmod(not_exec, 0o644)
    directory = tmp_path / "dir" / "python3"
    directory.mkdir(parents=True)
    wrong_name = _stub(tmp_path / "wrong", "bash-not-python")
    cases = {
        "missing-file": _posix(tmp_path / "nope" / "python3"),
        "a-directory": _posix(directory),
        "wrong-name": _posix(wrong_name),
        "relative": "python3",
        "relative-dotted": "./ok/python3",
        "empty": "",
        "windows-no-cygpath-nonexistent": "C:\\nowhere\\python.exe",
    }
    if crew_fixtures_noexec_supported(not_exec):
        cases["not-executable"] = _posix(not_exec)
    return good, cases


def crew_fixtures_noexec_supported(path):
    proc = subprocess.run([_BASH, "-c", '[ -x "$1" ]', "_", _posix(path)],
                          capture_output=True, check=False)
    return proc.returncode != 0


@needs_bash
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_must_block_an_invalid_crew_python_is_never_returned(tmp_path, func):
    pyfree = _python_free(tmp_path)
    _, cases = _bad_values(tmp_path)
    for label, value in cases.items():
        code, out, _ = _call(tmp_path, func, value, [pyfree])
        assert code != 0 and out == "", (label, code, out)


@needs_bash
@pytest.mark.parametrize("func", _FUNCS, ids=_IDS)
def test_an_invalid_crew_python_falls_back_to_the_walk(tmp_path, func):
    real = shutil.which("python3") or shutil.which("python")
    assert real
    code, out, err = _call(tmp_path, func, _posix(tmp_path / "nope" / "python3"),
                           [_posix(os.path.dirname(real)), _python_free(tmp_path)])
    assert code == 0 and out and "nope" not in out, (code, out, err)


# --- the suite clears an ambient CREW_PYTHON, and that does not hide the feature ---
#
# conftest.py removes CREW_PYTHON for every test: crew-hook.ps1 / .sh export it
# into the dispatcher, so a suite run from a crew-hooked session inherited it and
# every PATH-stubbed python fixture (test_native_script_path.py,
# test_python_probe_signals.py) was silently bypassed. The cases below pin that
# isolation, then prove through the SHIPPED `_common.sh` (sourced whole, not one
# function cut out) that an explicitly set value is still honoured.


def test_the_suite_clears_an_ambient_crew_python():
    assert "CREW_PYTHON" not in os.environ


def _logging_python_stub(directory, log):
    """A `python3` on PATH that records each run and then behaves like python,
    so the PATH walk accepts it and the log alone says whether it was used."""
    directory.mkdir(parents=True, exist_ok=True)
    real = _posix(os.path.realpath(shutil.which("python3") or shutil.which("python")))
    path = directory / "python3"
    path.write_text(f"#!/bin/sh\necho ran >>'{_posix(log)}'\nexec '{real}' \"$@\"\n",
                    encoding="ascii", newline="\n")
    os.chmod(path, 0o755)
    return path


def _sourced(tmp_path, func, creg):
    log = tmp_path / "stub.log"
    stub_dir = tmp_path / "stub-bin"
    _logging_python_stub(stub_dir, log)
    script = tmp_path / "sourced.sh"
    script.write_text(f'. "{_posix(_COMMON)}"\n{func}\n', encoding="utf-8", newline="\n")
    env = dict(os.environ, PATH=os.pathsep.join([_posix(stub_dir), _python_free(tmp_path)]))
    if creg is not None:
        env["CREW_PYTHON"] = creg
    proc = subprocess.run([_BASH, _posix(script)], capture_output=True, text=True,
                          env=env, check=False, timeout=120)
    return proc.returncode, proc.stdout.strip().replace("\r", ""), log.exists(), proc.stderr


@needs_bash
@pytest.mark.parametrize("func", ["crew_py", "crew_py_strict"])
def test_must_allow_an_explicit_crew_python_skips_the_path_stub(tmp_path, func):
    real = _posix(os.path.realpath(shutil.which("python3") or shutil.which("python")))
    code, out, stub_ran, err = _sourced(tmp_path, func, real)
    assert (code, out, stub_ran) == (0, real, False), err


@needs_bash
@pytest.mark.parametrize("func", ["crew_py", "crew_py_strict"])
@pytest.mark.parametrize("creg", [None, "/nowhere/python3", "relative/python3"],
                         ids=["unset", "missing", "relative"])
def test_must_block_without_a_valid_crew_python_the_path_stub_is_used(tmp_path, func, creg):
    code, out, stub_ran, err = _sourced(tmp_path, func, creg)
    assert code == 0 and stub_ran, (code, out, err)
    assert "nowhere" not in out and out != "relative/python3", out


# --- crew_py_script ---------------------------------------------------------------


def _script_call(tmp_path, arg):
    script = tmp_path / "s.sh"
    script.write_text(
        f'. "{_posix(_COMMON)}"\ncrew_py_script "$1"\n',
        encoding="utf-8", newline="\n")
    proc = subprocess.run([_BASH, _posix(script), arg], capture_output=True,
                          text=True, check=False, timeout=60)
    return proc.returncode, proc.stdout.replace("\r", "")


@needs_bash
def test_crew_py_script_must_allow_an_existing_file(tmp_path):
    target = tmp_path / "x.py"
    target.write_text("pass\n", encoding="utf-8")
    code, out = _script_call(tmp_path, _posix(target))
    assert code == 0 and out.endswith("x.py"), (code, out)


@needs_bash
@pytest.mark.parametrize("arg", ["", "does-not-exist.py"], ids=["empty", "missing"])
def test_crew_py_script_must_block_empty_or_missing(tmp_path, arg):
    code, out = _script_call(tmp_path, arg if not arg else _posix(tmp_path / arg))
    assert code == 1 and out == "", (code, out)


# --- the guards fail CLOSED, naming the missing script ----------------------------


@pytest.fixture(scope="module")
def scripts_copy(tmp_path_factory):
    """The plugin's hooks/scripts and skills/crew-graph/scripts as plain files
    (crew_config imports crew_upgrade from the second), so one helper can be
    removed per case without touching the shipped tree."""
    dest = tmp_path_factory.mktemp("plugin")
    for rel in (("hooks", "scripts"), ("skills", "crew-graph", "scripts")):
        src = pathlib.Path(_ROOT).joinpath(*rel)
        (dest.joinpath(*rel)).mkdir(parents=True)
        for entry in src.iterdir():
            if entry.is_file():
                shutil.copy2(entry, dest.joinpath(*rel) / entry.name)
    return dest


def _repo(tmp_path, cfg):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return root


def _run_guard(scripts, name, tmp_path, payload, root, drop=None):
    plugin = tmp_path / "plugin"
    shutil.copytree(scripts, plugin)
    work = plugin / "hooks" / "scripts"
    if drop:
        (work / drop).unlink()
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               CLAUDE_PROJECT_DIR=str(root))
    env.pop("CREW_PYTHON", None)
    proc = subprocess.run([_BASH, _posix(work / name)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(root),
                          check=False, timeout=170)
    return proc.returncode, proc.stdout + proc.stderr


_BASH_PAYLOAD = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}


@needs_bash
@pytest.mark.parametrize("name,helper,cfg", [
    ("cloud-guard.sh", "cloud_guard.py", {"guards": {"cloudGuard": "block"}}),
    ("env-guard.sh", "env_guard.py", {"guards": {"envGuard": "block"}}),
], ids=["cloud-guard", "env-guard"])
def test_an_armed_guard_with_its_script_missing_fails_closed(
        scripts_copy, tmp_path, name, helper, cfg):
    root = _repo(tmp_path, cfg)
    code, out = _run_guard(scripts_copy, name, tmp_path, dict(_BASH_PAYLOAD, cwd=str(root)),
                           root, drop=helper)
    assert code == 2, out
    assert f"{helper} is missing" in out, out
    assert "__main__" not in out, out


@needs_bash
@pytest.mark.parametrize("name,cfg", [
    ("cloud-guard.sh", {"guards": {"cloudGuard": "block"}}),
    ("env-guard.sh", {"guards": {"envGuard": "block"}}),
], ids=["cloud-guard", "env-guard"])
def test_an_armed_guard_with_its_script_present_runs(scripts_copy, tmp_path, name, cfg):
    """The control: the same call with the script present judges and allows."""
    root = _repo(tmp_path, cfg)
    code, out = _run_guard(scripts_copy, name, tmp_path, dict(_BASH_PAYLOAD, cwd=str(root)), root)
    assert code == 0, out
    assert "is missing" not in out, out


@needs_bash
def test_role_write_guard_with_its_script_missing_fails_closed(scripts_copy, tmp_path):
    root = _repo(tmp_path, {"guards": {"roleWrites": "block"}})
    payload = {"tool_name": "Write", "agent_type": "reviewer",
               "tool_input": {"file_path": str(root / "x.txt"), "content": "x"},
               "cwd": str(root)}
    code, out = _run_guard(scripts_copy, "role-write-guard.sh", tmp_path, payload, root,
                           drop="role_write_guard.py")
    assert "role_write_guard.py is missing" in out, (code, out)
    assert code == 2 or '"deny"' in out, (code, out)


@needs_bash
def test_promote_gate_with_a_helper_missing_blocks_and_names_it(scripts_copy, tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "runbook.md").write_text("# Rollback\nlast verified: 2026-11-01\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({"environments": {
        "prod": {"deploy": "deploy-prod", "rollback": "runbook.md",
                 "requireReview": False, "reviewReason": "fixture",
                 "reviewWaiverSha": TRAIN_BASE}}}), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=False, capture_output=True)
    seed_train_base(root)
    for args in (["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "T"], ["add", "-A", "-f"],
                 ["commit", "-q", "-m", "fixture"]):
        subprocess.run(["git"] + args, cwd=root, check=False, capture_output=True)
    payload = {"tool_input": {"command": "deploy-prod"}, "cwd": str(root)}
    code, out = _run_guard(scripts_copy, "promote-gate.sh", tmp_path, payload, root,
                           drop="_promote_dispatch.py")
    assert code == 2, out
    assert "_promote_dispatch.py is missing" in out, out
