"""The `slow` marker: the full per-shell hook matrix is out of the default run
and still reachable, and the parity-sample helpers mark what they say.

conftest.py deselects `slow` unless `--run-slow` is given or a `-m` names it.
These run pytest itself, collect-only, against one decision table whose
sample is known: test_cloud_guard.py's `_B_SHELL` keeps `tf-apply` and marks
`tf-destroy` slow. Collection never spawns a shell, so this holds on a host
with no bash too.
"""
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_CREW = context._ROOT  # pylint: disable=protected-access
_TARGET = "tests/test_cloud_guard.py::test_must_block_bash"
_SAMPLE = "test_must_block_bash[tf-apply]"
_MATRIX = "test_must_block_bash[tf-destroy]"


def _collected(*args):
    done = subprocess.run(
        [sys.executable, "-m", "pytest", _TARGET, "--collect-only", "-q",
         "-p", "no:cacheprovider", *args],
        cwd=_CREW, capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert done.returncode == 0, done.stdout + done.stderr
    return {line.split("::")[-1] for line in done.stdout.splitlines() if "::" in line}


@pytest.mark.parametrize("args,sample,matrix", [
    pytest.param((), True, False, id="default"),
    pytest.param(("-m", "slow"), False, True, id="m-slow"),
    pytest.param(("--run-slow",), True, True, id="run-slow"),
])
def test_collection_selects_by_the_slow_marker(args, sample, matrix):
    collected = _collected(*args)

    assert (_SAMPLE in collected, _MATRIX in collected) == (sample, matrix)


def test_parity_sample_marks_every_case_but_the_kept_ones_slow():
    params = crew_fixtures.parity_sample(["a", "b"], ["keep", "drop"], {"keep"})

    assert [[m.name for m in p.marks] for p in params] == [[], ["slow"]]


def test_parity_sample_refuses_an_id_the_table_does_not_have():
    with pytest.raises(AssertionError, match="unknown case"):
        crew_fixtures.parity_sample(["a"], ["only"], {"renamed"})


def test_sample_params_keeps_existing_marks_and_adds_slow():
    skip = pytest.mark.skipif(False, reason="x")
    params = crew_fixtures.sample_params(
        [pytest.param(1, id="keep", marks=skip), pytest.param(2, id="drop", marks=skip)],
        {"keep"})

    assert [[m.name for m in p.marks] for p in params] == [["skipif"], ["skipif", "slow"]]
