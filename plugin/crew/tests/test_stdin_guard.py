"""The suite survives a pytest run whose stdin is not a console (Windows).

`--capture=fd` closes the Win32 stdin handle, so any test child started without
`stdin=` died with `[WinError 6] The handle is invalid` (the Stop hook's verify
gate; `pytest ... <NUL`). `conftest.py` calls `_stdin_guard.install()` to stop
that. These tests pin the guard and the wiring.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

HERE = pathlib.Path(__file__).resolve().parent

PROBE = textwrap.dedent('''
    import subprocess, sys

    # stdin=None on purpose, at collection time as well as in the test: this is
    # the call that raised WinError 6 (test_context_watch_python_resolver.py).
    COLLECTED = subprocess.run([sys.executable, "-c", "pass"], capture_output=True,
                               text=True, check=False)

    def test_child_without_stdin_starts():
        assert COLLECTED.returncode == 0
        done = subprocess.run([sys.executable, "-c", "pass"], capture_output=True,
                              text=True, check=False)
        assert done.returncode == 0
''')

PROBE_CONFTEST = "import _stdin_guard\n_stdin_guard.install()\n"


def _launcher():
    # Measured on a machine whose `python` is the Python install manager shim
    # (...\Python\bin\python.exe): the bug shows through the shim and not
    # through the real interpreter sys.executable names. The Stop hook starts
    # `python3` from PATH, so the probe does too.
    return shutil.which("python3") or shutil.which("python") or sys.executable


def _run_probe(tmp_path, with_guard):
    (tmp_path / "test_probe.py").write_text(PROBE, encoding="utf-8", newline="\n")
    (tmp_path / "conftest.py").write_text(PROBE_CONFTEST if with_guard else "",
                                          encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_VERSION", "PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS")}
    env["PYTHONPATH"] = str(HERE)
    # `cmd /c ... <NUL` hands the child a NUL stdin the way a hook shell does.
    # shell=True runs `cmd.exe /c "<command>"` (Python adds the outer quotes).
    command = (f'"{_launcher()}" -m pytest "{tmp_path / "test_probe.py"}" -q '
               f'-p no:cacheprovider --rootdir "{tmp_path}" <NUL')
    return subprocess.run(command, shell=True, cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, check=False)

@pytest.mark.skipif(sys.platform != "win32", reason="Win32 handle semantics")
def test_child_without_stdin_starts_under_default_capture_with_guard(tmp_path):
    done = _run_probe(tmp_path, with_guard=True)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 handle semantics")
def test_probe_fails_without_guard_so_the_test_above_proves_something(tmp_path):
    done = _run_probe(tmp_path, with_guard=False)
    if done.returncode == 0:
        pytest.skip("this python launcher does not show the bug, so there is nothing to guard")
    assert "WinError 6" in done.stdout + done.stderr


def test_install_is_idempotent_and_never_raises():
    import _stdin_guard  # pylint: disable=import-outside-toplevel
    _stdin_guard.install()
    _stdin_guard.install()


def test_crew_conftest_installs_the_guard():
    source = (HERE / "conftest.py").read_text(encoding="utf-8")
    assert "import _stdin_guard" in source and "_stdin_guard.install()" in source


def test_pytest_rule_children_get_a_closed_stdin():
    source = (HERE / "pytest_rule.py").read_text(encoding="utf-8")
    assert "stdin=subprocess.DEVNULL" in source
