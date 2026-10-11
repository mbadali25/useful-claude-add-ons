"""`guards.envGuard`, the environment-dump guard's switch (L-0772).

Off by default, `block` as the floor for a malformed value, ratcheted across
the two layers with the narrower one winning, and listed by /crew:config with
a widening note for every tier.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_keys
import crew_state


def test_default_is_off_in_both_layers():
    assert crew_config.default_config()["guards"]["envGuard"] == "off"
    assert crew_config.default_global_config()["guards"]["envGuard"] == "off"
    assert crew_state.GUARD_DEFAULTS["envGuard"] == "off"


def test_it_is_a_guard_with_the_role_writes_vocabulary():
    assert "envGuard" in crew_state.ENV_GUARD_NAMES
    assert "envGuard" in crew_state.ALL_GUARD_NAMES
    tiers, normalise, _ = crew_state.guard_tiers("envGuard")
    assert tiers == crew_state.ROLE_WRITE_POLICIES == ("block", "report", "off")
    assert normalise(None) == "off"


@pytest.mark.parametrize("value", ["blok", "BLOCK ", 1, True, [], {}])
def test_malformed_value_is_block(value):
    _, normalise, _ = crew_state.guard_tiers("envGuard")
    assert normalise(value) == "block"


@pytest.mark.parametrize("repo,glob,want", [
    ("off", "block", "block"), ("block", "off", "block"),
    ("report", "off", "report"), ("off", "report", "report"),
    ("report", "block", "block"), ("off", "off", "off"), (None, None, "off")])
def test_ratchet_narrower_layer_wins(repo, glob, want):
    assert crew_state.effective_ratcheted("guards.envGuard", repo, glob) == want


def test_widening_notes_are_total_and_name_the_key():
    for tier in crew_state.ROLE_WRITE_POLICIES:
        note = crew_config.widening_note("guards.envGuard", tier)
        assert note, tier
    assert "guards.envGuard" in crew_config.widening_note("guards.envGuard", "off")
    assert "guard.log" in crew_config.widening_note("guards.envGuard", "report")


def test_config_key_table_declares_it():
    assert "guards.envGuard" in crew_keys.KEY_META


# Review round 1 (FIX): only an ABSENT key is off. An explicit `null` in either
# layer is malformed, the floor -- `normalise_role_writes(None)` alone cannot
# tell the two apart, so `resolve_ratcheted` does. `roleWrites` and
# `cloudGuard` keep reading `null` as absent.
def _layers(tmp_path, repo_guards, global_guards):
    import json  # pylint: disable=import-outside-toplevel
    import subprocess  # pylint: disable=import-outside-toplevel
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=60)
    glob = tmp_path / "global.json"
    for path, guards in ((repo / ".crew" / "config.json", repo_guards),
                         (glob, global_guards)):
        if guards is not None:
            path.write_text(json.dumps({"guards": guards}), encoding="utf-8")
    return str(repo), str(glob)


@pytest.mark.parametrize("repo_guards,global_guards,want", [
    ({"envGuard": None}, None, "block"),
    (None, {"envGuard": None}, "block"),
    ({"envGuard": None}, {"envGuard": "off"}, "block"),
    ({}, None, "off"),
    (None, None, "off"),
    ({"envGuard": "off"}, {"envGuard": "off"}, "off"),
], ids=["repo-null", "global-null", "repo-null-over-global-off", "repo-absent",
        "no-files", "both-off"])
def test_explicit_null_is_block_and_absent_is_off(tmp_path, monkeypatch,
                                                  repo_guards, global_guards,
                                                  want):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root, glob = _layers(tmp_path, repo_guards, global_guards)
    assert crew_config.resolve_guard(root, "envGuard", glob)["effective"] == want


@pytest.mark.parametrize("name", ["roleWrites", "cloudGuard"])
def test_other_switches_still_read_null_as_absent(tmp_path, monkeypatch, name):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root, glob = _layers(tmp_path, {name: None}, None)
    assert crew_config.resolve_guard(root, name, glob)["effective"] == "off"
