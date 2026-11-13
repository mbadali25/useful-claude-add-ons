"""`guards.enabled`, the master switch's key (crew 1.3.88): declared, validated and shown.

The dispatcher half (crew 1.3.87, `crew_hook.guards_switched_off`) is held by `test_guards_master.py`. This
file holds what declaring the key added: both default layers carry it, both config writers take only the
JSON booleans, `/crew:config` warns when a repo writes `false`, and `/crew:status` says the guards are off.
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


@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_both_writers_take_only_a_json_boolean(layer):
    for good in (True, False):
        assert crew_config.value_allowed("guards.enabled", layer, good) is None
    for bad in ("false", "off", 0, 1, [], {}):
        assert crew_config.value_allowed("guards.enabled", layer, bad) is not None, bad


def test_status_says_the_guards_are_disabled_and_by_which_layer(tmp_path, home):
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert line.startswith("guards   DISABLED - guards.enabled is false in the repo layer")

    root = _repo(tmp_path / "other", {})
    (home / ".claude" / "crew" / "config.json").write_text('{"guards": {"enabled": false}}', encoding="utf-8")
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "in the machine layer" in line


def test_status_says_nothing_extra_while_the_guards_are_on(tmp_path, home):
    assert os.path.isdir(str(home))
    root = _repo(tmp_path, {"guards": {"enabled": True}})
    assert crew_status._guards_line(root) is None  # pylint: disable=protected-access


def test_a_repo_false_is_a_widening_that_config_warns_about():
    notes = crew_config._REPO_WIDENING  # pylint: disable=protected-access
    assert ("guards.enabled", False) in notes
    assert "stands down" in notes[("guards.enabled", False)]
