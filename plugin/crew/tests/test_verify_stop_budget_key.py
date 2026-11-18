"""`verify.stopBudgetSeconds` is a settable, documented, bounded config key (thd-jobs 5a).

Before crew 1.3.157 the verify gate READ the key (`verify-gate.sh`, default 60) but the key was in
no template, so `crew_config` refused every write of it as "not a settable leaf of
.crew/config.json" and the budget could only be tuned by hand-editing the file. These cases hold:

* the key is a repo leaf with a KEY_META row, and its default is the 60 the gate already used;
* a whole number inside the bounds is ACCEPTED and written;
* anything else (zero, negative, over the Stop hook's timeout less the gate's margin, a float, a string, a boolean, a
  list, an object) is REFUSED with the value and the range named, and the file is left untouched,
  rather than stored for the reader to turn into its default without a word;
* it is repo only (the machine layer refuses it by name).

`test_verify_stop_budget_key_sabotage` reintroduces each bug in a copy of the code and proves the
suite goes red for the stated reason.
"""
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_hook
import crew_keys
import crew_state

KEY = "verify.stopBudgetSeconds"


def _repo(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    text = json.dumps(crew_config.default_config(), indent=2) + "\n"
    (root / ".crew" / "config.json").write_bytes(text.encode("utf-8"))
    return root


def _bytes(root):
    return (root / ".crew" / "config.json").read_bytes()


def test_key_is_a_repo_leaf_with_the_gates_own_default():
    assert KEY in crew_config.leaf_paths(crew_config.default_config())
    assert crew_config.default_config()["verify"] == {"stopBudgetSeconds": 60}
    assert crew_config.is_repo_path(KEY) is True
    # The gate's own fallback is the same 60, so declaring the key moved nothing.
    with open(os.path.join(context._ROOT, "hooks", "scripts", "verify-gate.sh"),  # pylint: disable=protected-access
              encoding="utf-8") as handle:
        assert "budget = 60\n" in handle.read()


def test_key_is_repo_only():
    assert crew_config.is_global_path(KEY) is False
    assert KEY not in crew_config.leaf_paths(crew_config.default_global_config())
    reason = crew_config.value_allowed(KEY, "machine", 30)
    assert reason is not None and "repo-only" in reason


def _gate_deadline_margin():
    with open(os.path.join(context._ROOT, "hooks", "scripts", "verify-gate.sh"),  # pylint: disable=protected-access
              encoding="utf-8") as handle:
        found = re.search(r"^DEADLINE_MARGIN=(\d+)$", handle.read(), re.MULTILINE)
    assert found, "verify-gate.sh no longer declares DEADLINE_MARGIN= on its own line"
    return int(found.group(1))


def test_key_has_a_documented_row_and_the_upper_bound_leaves_the_gates_margin():
    row = crew_keys.KEY_META[KEY]
    assert row["since"] == "1.3.157" and row["kind"] == "type"
    stop = [r for r in crew_hook.TABLE if r.script == "verify-gate.sh"]
    assert [r.event for r in stop] == ["Stop"]
    # A budget AT the hook timeout could be spent to the last second, leaving no time to defer the
    # rest and write the markers before the hook is killed: the bound reserves the gate's margin.
    assert crew_state.STOP_BUDGET_BOUNDS == (1, stop[0].timeout - _gate_deadline_margin())
    assert crew_state.STOP_BUDGET_BOUNDS[1] < stop[0].timeout


@pytest.mark.parametrize("value", [1, 30, 60, 300, 540])
def test_repo_writer_accepts_a_whole_number_in_bounds(tmp_path, value):
    root = _repo(tmp_path)
    assert crew_config.value_allowed(KEY, "repo", value) is None
    crew_config.write_repo_config(str(root), {KEY: value}, str(tmp_path / "g.json"))
    assert json.loads(_bytes(root))["verify"]["stopBudgetSeconds"] == value


def test_null_is_accepted_and_means_unset():
    assert crew_config.value_allowed(KEY, "repo", None) is None


def test_writing_null_clears_the_value_so_the_gate_uses_its_default(tmp_path):
    root = _repo(tmp_path)
    crew_config.write_repo_config(str(root), {KEY: 120}, str(tmp_path / "g.json"))
    assert json.loads(_bytes(root))["verify"]["stopBudgetSeconds"] == 120
    crew_config.write_repo_config(str(root), {KEY: None}, str(tmp_path / "g.json"))
    # The repo layer's convention: null is stored and means "unset" (the gate reads null as 60).
    assert json.loads(_bytes(root))["verify"]["stopBudgetSeconds"] is None


@pytest.mark.parametrize("value", [
    0, -1, 541, 600, 601, 10 ** 9,  # outside 1..540 (600 is the hook's own timeout)
    60.0, 59.5, float("nan"),  # not a whole number (60.0 == 60 in Python)
    "60", "", "unlimited",     # a string
    True, False,               # True == 1 in Python
    [60], {"a": 1}, {},        # a container
])
def test_repo_writer_refuses_everything_else_and_names_the_range(tmp_path, value):
    root = _repo(tmp_path)
    before = _bytes(root)
    reason = crew_config.value_allowed(KEY, "repo", value)
    assert reason is not None and KEY in reason
    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.write_repo_config(str(root), {KEY: value}, str(tmp_path / "g.json"))
    assert KEY in str(caught.value)
    assert _bytes(root) == before
    if not isinstance(value, dict):
        assert "1 to 540" in reason


def test_an_unknown_sibling_is_still_refused(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(crew_config.RepoWriteRefused):
        crew_config.write_repo_config(str(root), {"verify.stopBudgetSecond": 30},
                                      str(tmp_path / "g.json"))
    with pytest.raises(crew_config.RepoWriteRefused):
        crew_config.write_repo_config(str(root), {"verify": {}}, str(tmp_path / "g.json"))


def test_verify_stop_budget_key_sabotage(monkeypatch):
    """Reintroduce each bug and watch the cases above fail for their reason."""
    # Bug 1: the bound check is gone, so a typo is stored and the gate quietly runs its 60.
    monkeypatch.setattr(crew_config, "bounds_problem", lambda dotted, value: None)
    assert crew_config.value_allowed(KEY, "repo", -5) is None  # what the suite must catch
    for bad in (0, 541, 600, 60.0, True, "60"):  # the must-reject cases above would all go red
        assert crew_config.value_allowed(KEY, "repo", bad) is None, bad
    monkeypatch.undo()
    assert crew_config.value_allowed(KEY, "repo", -5) is not None
    # Bug 2: the key is not declared, so it is "not a settable leaf" (the original defect).
    template = crew_config.default_config()
    del template["verify"]
    monkeypatch.setattr(crew_config, "_default_template", lambda: template)
    reason = crew_config.value_allowed(KEY, "repo", 30)
    assert reason is not None and "not a settable leaf" in reason
