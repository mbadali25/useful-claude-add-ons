"""The conftest trust-seam venv is the interpreter the gate's resolver returns.

A seam venv that `crew_py_strict` walks past makes every gate test fail with
"UNTRUSTED" and nothing naming the venv, so the resolution is pinned here, and
the `.pth` chain is held to the isolation the gate relies on (`python -E -s`).
"""
import os
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_COMMON = os.path.join(_ROOT, "hooks", "scripts", "_common.sh")
_BASH = crew_fixtures.resolve_bash()


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_the_resolver_returns_the_seam_interpreter(_trust_seam_python):
    probe = ('. "$1"; p=$(crew_py_strict) || exit 3; '
             '"$p" -c "import sys; print(sys.prefix)"')
    done = crew_fixtures.run_gate([_BASH, "-c", probe, "_", _COMMON], capture_output=True,
                                  text=True, check=False, stdin=subprocess.DEVNULL,
                                  env=dict(os.environ))
    assert done.returncode == 0, f"crew_py_strict found no interpreter: {done.stderr}"
    prefix = done.stdout.strip().splitlines()[-1]
    assert os.path.normcase(os.path.realpath(prefix)) == os.path.normcase(
        os.path.realpath(_trust_seam_python.parent)), (
        f"the gate's resolver chose {prefix}, not the seam venv {_trust_seam_python.parent}")


def test_the_seam_venv_does_not_re_add_the_user_site(_trust_seam_python):
    exe = _trust_seam_python / ("python.exe" if os.name == "nt" else "python")
    done = subprocess.run([str(exe), "-E", "-s", "-c",
                           "import site, sys; u = site.getusersitepackages();"
                           "print(any(p == u for p in sys.path))"],
                          capture_output=True, text=True, check=False, timeout=60,
                          stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False", "the seam venv's .pth put the user site back on sys.path"
