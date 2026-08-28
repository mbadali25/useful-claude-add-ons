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
import crew_fixtures
import crew_platform
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


# --- Global + repo layering (resolve_config) -------------------------------


def _global(tmp_path, monkeypatch, contents=None):
    """Point GLOBAL_CONFIG_PATH at a scratch file for this test only."""
    path = tmp_path / "global-config.json"
    if contents is not None:
        path.write_text(json.dumps(contents), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    return path


def test_resolve_config_with_neither_layer_is_just_defaults(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)  # no global file at all
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert crew_config.resolve_config(str(root)) == crew_config.default_config()


def test_resolve_config_global_only(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "tracker": "jira", "pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["tracker"] == "jira"
    assert resolved["pm"]["maxDispatches"] == 9
    # Everything else in pm still comes from the built-in default.
    assert resolved["pm"]["quietLines"] == crew_state.PM_DEFAULTS["quietLines"]


def test_resolve_config_repo_only(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(
        tmp_path, config={"tracker": "obsidian"}, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["tracker"] == "obsidian"
    assert resolved["pm"] == crew_state.PM_DEFAULTS


def test_resolve_config_repo_overrides_global(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "tracker": "jira", "pm": {"maxDispatches": 9, "quietLines": 2}})
    root = crew_fixtures.make_repo(tmp_path, config={
        "tracker": "files", "pm": {"quietLines": 20}}, git=False)

    resolved = crew_config.resolve_config(str(root))

    # Repo wins where both set it.
    assert resolved["tracker"] == "files"
    assert resolved["pm"]["quietLines"] == 20
    # Global still wins over the built-in default where repo said nothing.
    assert resolved["pm"]["maxDispatches"] == 9


def test_resolve_config_malformed_global_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "global-config.json"
    path.write_text("{ not json, half-edited", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(
        tmp_path, config={"tracker": "sdp"}, git=False)

    # Must not raise, and must resolve exactly as if the global file were
    # absent -- crew_upgrade._read_config_strict's reasoning applied to the
    # global layer instead of the repo one.
    resolved = crew_config.resolve_config(str(root))
    assert resolved["tracker"] == "sdp"
    assert resolved["pm"] == crew_state.PM_DEFAULTS
    # The broken file itself is left alone -- nothing in this module writes
    # the global layer, ever.
    assert path.read_text(encoding="utf-8") == "{ not json, half-edited"


def test_resolve_config_global_that_is_a_json_array_is_ignored(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents=None)
    path = tmp_path / "global-config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    assert crew_config.resolve_config(str(root)) == crew_config.default_config()


def test_heal_writes_the_repo_file_not_the_global_one(tmp_path, monkeypatch):
    """heal_config recreates .crew/config.json only -- the global layer is
    never read for the decision and never written, regardless of whether it
    exists, is missing, or is broken."""
    global_path = _global(tmp_path, monkeypatch,
                          contents={"tracker": "jira"})
    before = global_path.read_bytes()
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    cfg, message = crew_platform.heal_config(str(root))

    assert cfg == crew_config.default_config()
    assert "missing" in message
    assert global_path.read_bytes() == before
    written = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    # The repo file gets built-in defaults, NOT the global tracker override --
    # heal_config calls default_config(), never resolve_config().
    assert written["tracker"] == "files"


# --- layered_state: the collect() + resolve_config composition point ------
#
# crew_state.collect takes a plain cfg_override argument rather than
# importing this module itself -- crew_config already imports crew_state,
# so the reverse would be a real cyclic import. layered_state is where the
# two are actually wired together; these tests exercise that end to end,
# the way pm_brief.py's SessionStart brief does.


def test_layered_state_applies_a_global_override_for_a_crew_repo(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={"pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["isCrew"] is True
    assert got["pm"]["maxDispatches"] == 9


def test_layered_state_never_lets_a_global_file_make_a_plain_repo_crew(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch,
           contents={"tracker": "jira", "pm": {"maxDispatches": 9}})
    plain = tmp_path / "plain"
    plain.mkdir()

    got = crew_config.layered_state(str(plain))

    assert got["isCrew"] is False
    assert got["tracker"] is None
    assert got["triggers"] == []


def test_layered_state_schema_is_not_masked_by_the_global_layer(tmp_path, monkeypatch):
    """resolve_config's built-in-defaults layer always supplies
    SCHEMA_CURRENT, so schema must come from the raw repo file regardless --
    an unmigrated v1 repo must not read as current just because a global
    file exists on the machine."""
    _global(tmp_path, monkeypatch, contents={"pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["schema"] == 1
    assert "upgradeNeeded" in got["triggers"]


def test_layered_state_survives_a_malformed_global_file(tmp_path, monkeypatch):
    path = tmp_path / "global-config.json"
    path.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["isCrew"] is True
    assert got["pm"]["maxDispatches"] == 3  # built-in default, global ignored


def test_layered_state_fills_in_a_built_in_default_the_raw_repo_file_omits(
        tmp_path):
    """With no global file, layered_state still differs from plain
    crew_state.collect for a repo config that omits a key -- resolve_config
    fills it from the built-in default, where raw collect() would report
    None. That is the layering working, not a bug to reconcile away."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": []})  # no tracker

    assert crew_state.collect(str(root))["tracker"] is None
    assert crew_config.layered_state(str(root))["tracker"] == "files"
