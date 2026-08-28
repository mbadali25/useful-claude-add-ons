"""Tests for crew_config: the single source of truth for a fresh config.

Three things must never disagree: `default_config()`, the committed template
`templates/config.template.json` (what `/crew:init` writes), and the `pm` /
`graph` blocks owned by `crew_state` and `crew_upgrade` respectively. The
template-drift test is the one that actually protects that -- everything
else here is ordinary unit coverage.
"""
import copy
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import crew_upgrade

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "templates", "config.template.json",
)


def test_default_config_matches_the_committed_template():
    """Drift between this module and the file /crew:init copies must fail CI.

    A byte-for-byte comparison, not just a dict equality, so a formatting
    change (key order, indent width) that would still round-trip equal is
    also caught -- the template is meant to be exactly what a fresh
    `json.dumps(default_config(), indent=2) + "\\n"` produces.
    """
    expected = json.dumps(crew_config.default_config(), indent=2) + "\n"
    with open(_TEMPLATE_PATH, encoding="utf-8") as handle:
        actual = handle.read()
    assert actual == expected


def test_default_config_pm_block_matches_crew_state():
    assert crew_config.default_config()["pm"] == crew_state.PM_DEFAULTS


def test_default_config_graph_block_matches_crew_upgrade():
    assert crew_config.default_config()["graph"] == crew_upgrade.GRAPH_BLOCK


def test_default_config_schema_matches_crew_state():
    assert crew_config.default_config()["schema"] == crew_state.SCHEMA_CURRENT


def test_default_config_is_a_dict():
    assert isinstance(crew_config.default_config(), dict)


def test_default_config_platform_block_is_all_null():
    # platform-sync fills this in; a hand-written value here is only ever
    # overwritten on the next session start.
    platform_block = crew_config.default_config()["platform"]
    assert all(value is None for value in platform_block.values())


def test_default_config_returns_a_fresh_object_each_call():
    """Mutating one call's result must not affect the next call's."""
    first = crew_config.default_config()
    first["pm"]["authority"] = "act"
    first["graph"]["obsidian"]["confirmed"] = True
    second = crew_config.default_config()
    assert second["pm"]["authority"] == "report-only"
    assert second["graph"]["obsidian"]["confirmed"] is False


def test_default_config_json_round_trips():
    text = json.dumps(crew_config.default_config())
    assert json.loads(text) == crew_config.default_config()


def test_mutating_pm_defaults_copy_does_not_leak_into_a_new_call():
    """copy.deepcopy, not a shared reference -- crew_upgrade.GRAPH_BLOCK's own
    docstring warns about exactly this failure one level down (obsidian)."""
    borrowed = copy.deepcopy(crew_state.PM_DEFAULTS)
    borrowed["maxDispatches"] = 999
    assert crew_config.default_config()["pm"]["maxDispatches"] == 3
