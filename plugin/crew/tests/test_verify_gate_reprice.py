"""A cached measurement re-prices a rule in both directions (L-0905).

The Stop gate used to take min(declared, cached), so a rule that really costs
more than it declares kept its stale cheap price forever: it spent budget it
did not have and never deferred its neighbour. The latest valid measurement on
this machine now wins. A rule re-priced over the budget alone is chronic, so it
is deferred (counted NOT VERIFIED) and runs only under `--all`, which also
re-measures it.
"""
import json
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from test_verify_gate_stop_budget import (  # pylint: disable=wrong-import-order
    _BIG_ALONE, _CHEAP_ALONE, _FLAVOURS, _ran, _repo, _run, _seed_timing)

_TIMINGS = ".verify-gate.timings.json"


def _deferred(result):
    """The deferred count the budget line states, 0 when it prints none."""
    found = re.search(r"stop budget \d+s; ran \d+s of stated cost, deferred (\d+)", result.stderr)
    return int(found.group(1)) if found else 0


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_dearer_measurement_defers_a_declared_rule(flavour, tmp_path):
    """MUST-BLOCK. Declared 5s, a cache that measured 190s: the rule is now
    over the 60s budget alone, so it is deferred, not run."""
    root = _repo(tmp_path, _CHEAP_ALONE)
    _seed_timing(root, _CHEAP_ALONE, 190)

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    assert "echo RAN-cheap-5" not in _ran(result), (
        "a rule measured at 190s still ran on its declared 5s. " + result.stderr)
    assert _deferred(result) == 1, result.stderr
    assert "NOT VERIFIED ON THIS TREE - rules[0]: echo RAN-cheap-5" in result.stderr, result.stderr
    assert "priced at 190s, measured on this machine, above its declared 5s" in result.stderr, (
        result.stderr)
    assert "/crew:verify --all" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_cheaper_measurement_runs_a_rule_its_declared_price_defers(flavour, tmp_path):
    """MUST-ALLOW. The other direction still holds: declared 90s, measured 3s."""
    root = _repo(tmp_path, _BIG_ALONE)
    _seed_timing(root, _BIG_ALONE, 3)

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    assert "echo RAN-big-90" in _ran(result), result.stderr
    assert _deferred(result) == 0, result.stderr
    assert "NOT VERIFIED" not in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_slow_rule_measured_over_two_runs_defers_its_neighbour(flavour, tmp_path):
    """Run 1 times a rule declared 1s at about 3s. The neighbour's cache entry
    is then set to its declared 58s, as a measurement of a rule that really
    costs that would be (an `echo` cannot cost it). Run 2 prices the slow rule
    at what it cost, so 3 + 58 no longer fits the 60s budget and the
    neighbour defers; at the declared 1s it would have fitted."""
    verify_map = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 1,
             "run": ["sleep 3"],
             "why": "declared 1s, really 3s"},
            {"paths": ["a.py"], "seconds": 58, "run": ["echo RAN-neighbour-58"],
             "why": "fits beside a 1s rule, not beside a 3s one"},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, verify_map)

    first = _run(flavour, root)
    timings_path = root / ".crew" / _TIMINGS
    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    import verify_record  # pylint: disable=import-outside-toplevel
    neighbour = verify_record.rule_key(verify_map["rules"][1])
    timings["rules"][neighbour] = 58
    timings_path.write_text(json.dumps(timings), encoding="utf-8")
    (root / "a.py").write_text("x = 2", encoding="utf-8")
    second = _run(flavour, root)

    assert first.returncode == 0, first.stderr
    assert "echo RAN-neighbour-58" in _ran(first), first.stderr
    assert second.returncode == 0, second.stderr
    assert "echo RAN-neighbour-58" not in _ran(second), (
        "the 3s measurement did not re-price the slow rule. " + second.stderr)
    assert _deferred(second) == 1, second.stderr
    assert "deferred to /crew:verify: echo RAN-neighbour-58 (58s)" in second.stderr, second.stderr
    assert "the verified baseline was NOT advanced" in second.stderr, second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_chronic_by_measurement_rule_runs_under_all_and_is_remeasured(flavour, tmp_path):
    """MUST-ALLOW. `--all` removes the budget, runs the rule, and the cache
    entry takes the new figure."""
    root = _repo(tmp_path, _CHEAP_ALONE)
    key = _seed_timing(root, _CHEAP_ALONE, 190)

    result = _run(flavour, root, "--all")

    assert result.returncode == 0, result.stderr
    assert "echo RAN-cheap-5" in _ran(result), result.stderr
    timings = json.loads((root / ".crew" / _TIMINGS).read_text(encoding="utf-8"))
    assert 1 <= timings["rules"][key] < 190, timings


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("value", [True, 2.5, "3", 0, -1, None])
def test_an_unusable_measurement_does_not_price_a_rule_with_no_declared_seconds(flavour, value, tmp_path):
    """MUST-BLOCK. With no declared `seconds` only a positive integer is a
    price; a JSON true is an int in python and must not read as 1s."""
    rule = {"paths": ["a.py"], "run": ["echo RAN-undeclared"], "why": "no seconds on purpose"}
    verify_map = {"version": 1, "rules": [rule], "default": [], "unmapped": "ignore"}
    root = _repo(tmp_path, verify_map)
    _seed_timing(root, verify_map, value)

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    assert "echo RAN-undeclared" in _ran(result), result.stderr
    assert "priced from a cached measurement" not in result.stderr, (
        "a cached " + repr(value) + " priced a rule with no declared seconds. " + result.stderr)
