"""`guards.enabled`, the master switch's key (crew 1.3.90): declared, validated and shown.

The dispatcher half (crew 1.3.87, `crew_hook.guards_switched_off`) is held by `test_guards_master.py`. This
file holds what declaring the key added: both default layers carry it, the machine writer takes only the
JSON booleans, the repo writer refuses the key (only the machine layer counts, owner decision 2026-11-13),
and `/crew:status` says the guards are off, or that a repo `false` is not in effect.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_keys
import crew_status


def _repo(tmp_path, cfg):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(root)


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_the_key_is_declared_true_in_both_default_layers():
    assert crew_config.default_config()["guards"]["enabled"] is True
    assert crew_config.default_global_config()["guards"]["enabled"] is True
    assert crew_config.is_global_path("guards.enabled")
    assert crew_keys.KEY_META["guards.enabled"]["values"] == (True, False)


def test_the_machine_writer_takes_only_a_json_boolean():
    for good in (True, False):
        assert crew_config.value_allowed("guards.enabled", "machine", good) is None
    for bad in ("false", "off", 0, 1, [], {}):
        assert crew_config.value_allowed("guards.enabled", "machine", bad) is not None, bad


@pytest.mark.parametrize("value", [True, False, None, "false"])
def test_the_repo_writer_refuses_the_key(value):
    """Owner decision 2026-11-13: only the machine layer counts, so a repo file may not hold the key."""
    reason = crew_config.value_allowed("guards.enabled", "repo", value)
    assert reason is not None and "machine" in reason, value


def test_the_key_is_machine_only_in_the_key_table():
    assert crew_keys.layer_of("guards.enabled") == "machine-only"


def test_status_says_the_guards_are_disabled_only_for_the_machine_layer(tmp_path, home):
    root = _repo(tmp_path, {})
    (home / ".claude" / "crew" / "config.json").write_text('{"guards": {"enabled": false}}', encoding="utf-8")
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert line.startswith("guards   DISABLED - guards.enabled is false in the machine layer")


def test_status_says_a_repo_false_is_not_in_effect(tmp_path, home):
    assert os.path.isdir(str(home))
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "DISABLED" not in line
    assert "only the machine layer counts" in line and "every guard still runs" in line


def test_status_says_nothing_extra_while_the_guards_are_on(tmp_path, home):
    assert os.path.isdir(str(home))
    root = _repo(tmp_path, {"guards": {"enabled": True}})
    assert "DISABLED" not in (crew_status._guards_line(root) or "")  # pylint: disable=protected-access
    assert crew_status._guards_line(_repo(tmp_path / "bare", {})) is None  # pylint: disable=protected-access


def test_a_repo_value_is_reported_as_ignored_not_as_in_effect(tmp_path, home):
    assert os.path.isdir(str(home))
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    entries = crew_config.inert_settings(root)
    entry = next(e for e in entries if e["key"] == "guards.enabled")
    assert entry["kind"] == "repo-ignored" and "no guard down" in entry["effect"]
    rows = {row["path"]: row for row in crew_config.explain_config(root, all_keys=True)}
    assert rows["guards.enabled"]["repoIgnored"] is False


def test_the_default_true_in_a_repo_file_is_quiet(tmp_path, home):
    assert os.path.isdir(str(home))
    root = _repo(tmp_path, {"guards": {"enabled": True}})
    assert not [e for e in crew_config.inert_settings(root) if e["key"] == "guards.enabled"]
