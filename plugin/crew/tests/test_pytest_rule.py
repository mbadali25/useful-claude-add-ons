"""pytest_rule.py: the parallel-then-wallclock split .crew/verify.json's crew
rules run through. The exit code is the whole contract the gate reads."""
import os
import subprocess
import sys

import pytest

import pytest_rule


def _with(monkeypatch, codes, xdist=True):
    calls = []

    def fake(args):
        calls.append(args)
        return codes[len(calls) - 1]
    monkeypatch.setattr(pytest_rule, "_pytest", fake)
    monkeypatch.setattr(pytest_rule, "_has_xdist", lambda: xdist)
    return calls


@pytest.mark.parametrize("parallel, serial, want", [
    (0, 0, 0),
    (0, 5, 0),      # no wallclock test in these files: the usual case
    (5, 0, 0),      # every test is wallclock
    (5, 5, 5),      # the rule selected nothing at all
    (1, 0, 1),
    (0, 1, 1),
    (2, 1, 2),      # the first real failure, not the larger code
    (-9, 0, 1),     # a half killed by a signal is a failure, never max()'s 0
    (0, -15, 1),
])
def test_the_exit_code_is_the_first_real_failure(monkeypatch, parallel, serial, want):
    calls = _with(monkeypatch, [parallel, serial])

    assert pytest_rule.main(["a.py", "-q"]) == want
    assert calls == [["a.py", "-q", "-n", "auto", "-m", "not wallclock"],
                     ["a.py", "-q", "-m", "wallclock"]]


def test_without_xdist_it_is_the_one_serial_run_the_rule_had(monkeypatch):
    calls = _with(monkeypatch, [3], xdist=False)

    assert pytest_rule.main(["a.py", "-q"]) == 3
    assert calls == [["a.py", "-q"]]


@pytest.mark.parametrize("argv", [["a.py", "-m", "slow"], ["a.py", "-n", "4"],
                                  ["a.py", "--numprocesses=4"], ["a.py", "-m=slow"],
                                  ["a.py", "-n4"], ["a.py", "-nauto"], ["a.py", "-mslow"], []])
def test_a_marker_or_worker_count_of_its_own_is_refused(monkeypatch, argv):
    calls = _with(monkeypatch, [0, 0])

    assert pytest_rule.main(argv) == 2
    assert calls == []


@pytest.mark.parametrize("body, want", [("assert True", 0), ("assert False", 1)])
def test_the_real_subprocess_path_end_to_end(tmp_path, body, want):
    """Nothing mocked: the script runs pytest as `sys.executable -m pytest`
    on a throwaway file, with or without xdist, and its exit code is the one
    the gate reads -- 0 for a pass (the wallclock half's exit 5 forgiven), 1
    for a failure."""
    (tmp_path / "test_one.py").write_text(f"def test_one():\n    {body}\n", encoding="utf-8")
    script = os.path.join(os.path.dirname(os.path.abspath(pytest_rule.__file__)), "pytest_rule.py")
    done = subprocess.run([sys.executable, script, str(tmp_path / "test_one.py"), "-q",
                           "-p", "no:cacheprovider"],
                          cwd=str(tmp_path), capture_output=True, text=True, check=False,
                          timeout=120, stdin=subprocess.DEVNULL)
    assert done.returncode == want, done.stdout + done.stderr
