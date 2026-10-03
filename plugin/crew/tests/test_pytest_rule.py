"""pytest_rule.py: the parallel-then-wallclock split .crew/verify.json's crew
rules run through. The exit code is the whole contract the gate reads."""
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
                                  ["a.py", "--numprocesses=4"], ["a.py", "-m=slow"], []])
def test_a_marker_or_worker_count_of_its_own_is_refused(monkeypatch, argv):
    calls = _with(monkeypatch, [0, 0])

    assert pytest_rule.main(argv) == 2
    assert calls == []
