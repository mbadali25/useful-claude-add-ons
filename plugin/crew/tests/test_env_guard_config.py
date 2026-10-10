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
