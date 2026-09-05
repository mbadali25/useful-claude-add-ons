"""Tests for crew_config: the single source of truth for a fresh config.

Five things must never disagree: `default_config()`, the committed template
`templates/config.template.json` (what `/crew:init` writes), the inline JSON
copy in `skills/crew-setup/SKILL.md` (prose for a human reading the skill),
the `pm` / `qa` / `dev` / `graph` blocks owned by `crew_state` and
`crew_upgrade`, and -- since 0.16.0 -- `default_global_config()` against
`templates/global.template.json`. The drift tests are what actually protect
that; everything else here is ordinary unit coverage.

The rest of this file covers the three things the guided-config work added:
`explain_config` (the value AND the layer that decided it), `inspect_global`
(what `/crew:upgrade` reports, writing nothing), and the global writer, whose
three guarantees -- merge, refuse a repo key, mark a widening of
`pm.authority` -- are enforced in code and tested here rather than trusted to
prose.
"""
import copy
import json
import os
import re

import pytest

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
_GLOBAL_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "templates", "global.template.json",
)
_SKILL_MD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "skills", "crew-setup", "SKILL.md",
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


def test_default_global_config_matches_the_committed_template():
    """Same drift gate as the repo template, on the global one.

    `/crew:config` writes this file's keys into `~/.claude/crew/config.json`,
    so a template that disagrees with `default_global_config()` is a
    walkthrough offering a key the writer refuses, or refusing one the
    template advertises. Byte-for-byte for the same reason as above.
    """
    expected = json.dumps(crew_config.default_global_config(), indent=2) + "\n"
    with open(_GLOBAL_TEMPLATE_PATH, encoding="utf-8") as handle:
        actual = handle.read()
    assert actual == expected


def test_the_global_template_is_not_a_copy_of_the_repo_one():
    """`tracker`, `jira.project`, `obsidian.boardDir`, `graph.out` and
    `platform.*` are facts about one checkout. Shipping them globally invites
    a vault path set once that every repo on the machine then inherits."""
    keys = set(crew_config.default_global_config())
    for repo_only in ("tracker", "jira", "sdp", "obsidian", "graph",
                      "platform", "tier", "roles", "verifyGate", "context",
                      "emergency"):
        assert repo_only not in keys, repo_only


def test_the_global_template_carries_no_schema():
    """`resolve_config` exempts `schema` structurally so a global value can
    never make an unmigrated repo look current. Shipping it in the template
    would hand every user the exact value that exemption exists to ignore."""
    assert "schema" not in crew_config.default_global_config()


def test_every_global_key_is_a_real_repo_config_key():
    """A global key the repo shape has never heard of would resolve into
    every repo and be read by nothing."""
    repo = crew_config.default_config()
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        node = repo
        for part in path.split("."):
            assert isinstance(node, dict) and part in node, path
            node = node[part]


def test_default_global_config_returns_a_fresh_object_each_call():
    first = crew_config.default_global_config()
    first["pm"]["authority"] = "act"
    first["qa"]["codex"]["model"] = "mutated"
    assert crew_config.default_global_config()["pm"]["authority"] == "report-only"
    assert crew_config.default_global_config()["qa"]["codex"]["model"] is None


def test_default_config_matches_crew_setup_skill_md_inline_copy():
    """The inline JSON in crew-setup/SKILL.md is prose for a human reading
    the skill, not a second definition -- crew_config's own module docstring
    says so. Compared PARSED, not byte-wise: the doc renders every nested
    object on one line for readability, which `json.dumps(..., indent=2)`
    would not reproduce, and a formatting difference is not drift. A field
    added to `default_config()` and forgotten here is drift, and this is
    the test that catches it -- the template-drift test above only covers
    `templates/config.template.json`, a file most people editing the skill
    will never open.
    """
    with open(_SKILL_MD_PATH, encoding="utf-8") as handle:
        text = handle.read()
    fences = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert len(fences) == 1, (
        "expected exactly one ```json fence in crew-setup/SKILL.md (the "
        f"config.json copy) -- found {len(fences)}. If the skill now "
        "legitimately has more than one, make this test find the right one "
        "rather than deleting the check."
    )
    doc_config = json.loads(fences[0])
    assert doc_config == crew_config.default_config()


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

    resolved = crew_config.resolve_config(str(root))

    # Every key except `schema` matches the built-in default exactly.
    expected = crew_config.default_config()
    del expected["schema"]
    assert {k: v for k, v in resolved.items() if k != "schema"} == expected
    # No repo config at all means no repo `schema` key either -- absent, not
    # the built-in default's current value. See test_resolve_config_schema_*
    # below for the structural guarantee this protects.
    assert "schema" not in resolved


def test_resolve_config_global_only(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "pm": {"maxDispatches": 9}, "qa": {"provider": "codex"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    resolved = crew_config.resolve_config(str(root))

    # The WHOLE pm block layers globally, not just `authority`. How many
    # roles one pass may dispatch is a property of the machine doing the
    # dispatching; 0.16.0 briefly filtered it out and the user ruled it back.
    assert resolved["pm"]["maxDispatches"] == 9
    assert resolved["qa"]["provider"] == "codex"
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
    """Global is the DEFAULT, not a lock -- one repo may legitimately want a
    different reviewer from the rest of the machine."""
    _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex", "fallback": "claude-haiku-9"},
        "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config={
        "qa": {"provider": "copilot"}}, git=False)

    resolved = crew_config.resolve_config(str(root))

    # Repo wins where both set it.
    assert resolved["qa"]["provider"] == "copilot"
    # Global still wins over the built-in default where repo said nothing.
    assert resolved["qa"]["fallback"] == "claude-haiku-9"
    assert resolved["pm"]["authority"] == "act"


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

    resolved = crew_config.resolve_config(str(root))
    expected = crew_config.default_config()
    del expected["schema"]
    assert {k: v for k, v in resolved.items() if k != "schema"} == expected
    assert "schema" not in resolved


# --- the global/repo split: a repo-only key takes effect NOWHERE -----------
#
# The 2026-09-05 rule, in tests. Before it, a global `tracker` or
# `graph.obsidian.dir` was inherited by every repo that did not override it,
# so setting a vault path once quietly gave every repository on the machine a
# board that did not describe it -- a reasonable-looking mistake that failed
# silently, which is the worst combination available.


def test_a_repo_only_key_in_the_global_file_takes_effect_nowhere(
        tmp_path, monkeypatch):
    """Every repo-only key at once, against a repo that overrides none of
    them. Each must resolve to the BUILT-IN default, not the global value."""
    _global(tmp_path, monkeypatch, contents={
        "tracker": "jira",
        "jira": {"project": "NOPE"},
        "tier": 3,
        "roles": ["explorer", "dba"],
        "verifyGate": False,
        "graph": {"out": "somewhere-else",
                  "obsidian": {"enabled": True, "dir": "/someone/vault"}},
        "platform": {"os": "linux"},
        "obsidian": {"boardDir": "Boards/wrong"},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    resolved = crew_config.resolve_config(str(root))
    built_in = crew_config.default_config()

    for key in ("tracker", "jira", "tier", "roles", "verifyGate", "graph",
                "platform", "obsidian"):
        assert resolved[key] == built_in[key], key


def test_a_globally_ignored_key_is_reported_rather_than_failing_silently(
        tmp_path, monkeypatch):
    """A key that quietly does nothing is worse than one refused out loud, so
    the drop is a finding rather than an implementation detail."""
    path = _global(tmp_path, monkeypatch, contents={
        "graph": {"obsidian": {"dir": "/someone/vault"}},
        "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    detail = {f["kind"]: f["detail"]
              for f in crew_config.inspect_global(str(root), str(path))
              ["findings"]}["repo-keys"]

    assert "graph" in detail
    assert "IGNORED" in detail, "the wording must not still say `inherits`"
    assert "inherit" not in detail


def test_the_filter_reports_a_nested_stray_a_top_level_diff_cannot_see(
        tmp_path, monkeypatch):
    """`graph.obsidian.dir` under an otherwise-plausible block is the exact
    mistake this finding exists to name."""
    kept, ignored = crew_config.filter_global({
        "qa": {"provider": "codex", "boardDir": "Boards/x"},
        "pm": {"authority": "act", "maxDispatches": 9},
    })
    # `pm` is admitted as a WHOLE block: maxDispatches is a fact about the
    # machine doing the dispatching. `qa.boardDir` is the stray -- a tracker
    # path is a fact about one checkout and cannot be set for every repo.
    assert kept == {"qa": {"provider": "codex"},
                    "pm": {"authority": "act", "maxDispatches": 9}}
    assert ignored == ["qa.boardDir"]


def test_the_model_table_still_layers_globally(tmp_path, monkeypatch):
    """The filter drops repo facts, not the model table -- which reviewer is
    installed here is exactly the kind of thing a global file is FOR."""
    _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex", "fallback": "claude-opus-9",
               "roles": {"review": {"provider": "codex",
                                    "model": "gpt-5.6-luna"}}},
        "dev": {"roles": {"developer": {"provider": "codex",
                                        "model": "gpt-6-astra"}}},
        "memory": {"mode": "vault", "vaultPath": "/home/me/vault"},
    })
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    resolved = crew_config.resolve_config(str(root))

    assert resolved["qa"]["provider"] == "codex"
    assert resolved["qa"]["fallback"] == "claude-opus-9"
    assert resolved["qa"]["roles"]["review"]["model"] == "gpt-5.6-luna"
    assert resolved["dev"]["roles"]["developer"]["model"] == "gpt-6-astra"
    # BOTH memory keys are global as of 0.16.0 -- one vault per person, and a
    # person who keeps their memory in a vault keeps it there everywhere.
    assert resolved["memory"] == {"mode": "vault",
                                  "vaultPath": "/home/me/vault"}


def test_memory_mode_is_globally_settable_and_the_template_ships_it():
    assert "mode" in crew_config.default_global_config()["memory"]
    assert crew_config.is_global_path("memory.mode") is True


def test_obsidian_confirmed_is_ungrantable_on_both_paths(tmp_path, monkeypatch):
    """Consent to write into the user's own notes outside the repo, not a
    capability. Two independent guards since 0.16.0, because the filtering
    change created a second way to try: the walkthrough refuses to WRITE it,
    and the resolver refuses to READ it however it got there."""
    path = _global(tmp_path, monkeypatch, contents={
        "graph": {"obsidian": {"enabled": True, "dir": "/v",
                               "confirmed": True}}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)

    # Read path: hand-written into the global file by any means at all.
    resolved = crew_config.resolve_config(str(root))
    assert resolved["graph"]["obsidian"]["confirmed"] is False
    assert resolved["graph"]["obsidian"]["enabled"] is False
    assert resolved["graph"]["obsidian"]["dir"] is None

    # Write path: refused by name, and the file is left exactly as it was.
    before = path.read_bytes()
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config(
            {"graph.obsidian.confirmed": True}, str(path))
    assert path.read_bytes() == before
    assert crew_config.is_global_path("graph.obsidian.confirmed") is False


def test_write_and_read_admit_exactly_the_same_paths():
    """What the global file may WRITE is exactly what the global layer may
    SUPPLY. Two rules with one definition, or they drift and the drift is
    silent -- a walkthrough offering a key the resolver discards."""
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        assert crew_config.is_global_path(path) is True, path
    for path in ("tracker", "jira.project", "graph.out", "tier", "roles",
                 "schema", "platform.os", "verify", "codemap.dir",
                 "graph.obsidian.confirmed"):
        assert crew_config.is_global_path(path) is False, path
    # The whole `pm` block is global, siblings included -- see the
    # default_global_config docstring for why each one is a machine or
    # person fact rather than a checkout fact.
    assert crew_config.is_global_path("pm.maxDispatches") is True


def test_a_pin_for_a_role_this_release_does_not_name_survives_the_filter():
    """`dev.roles` is an open table. A filter that only admitted four
    hardcoded role names would silently drop the fifth."""
    kept, ignored = crew_config.filter_global(
        {"dev": {"roles": {"house-style-cop": {"provider": "codex"}}}})
    assert kept["dev"]["roles"]["house-style-cop"] == {"provider": "codex"}
    assert ignored == []  # pylint: disable=use-implicit-booleaness-not-comparison
    assert crew_config.is_global_path("dev.roles.house-style-cop.model")


def test_explain_credits_no_layer_for_a_value_the_filter_dropped(
        tmp_path, monkeypatch):
    """Explaining an effective value from a layer the resolver would have
    discarded is how a source column comes to name a key that does nothing."""
    path = _global(tmp_path, monkeypatch, contents={"qa": {"boardDir": "B/x"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    rows = crew_config.explain_config(str(root), str(path))
    assert all(row["source"] != "global" for row in rows)


def test_explain_credits_the_global_layer_for_a_value_it_really_supplied(
        tmp_path, monkeypatch):
    """The other half, and the one the incident was about: a key the filter
    ADMITS has to be credited to `global`, or the source column understates
    what the machine-wide file is deciding."""
    path = _global(tmp_path, monkeypatch,
                   contents={"pm": {"maxDispatches": 9}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    rows = crew_config.explain_config(str(root), str(path))
    row = next(r for r in rows if r["path"] == "pm.maxDispatches")
    assert row["source"] == "global"
    assert row["value"] == 9


# --- resolve_config's structural schema exemption --------------------------


def test_resolve_config_schema_never_comes_from_the_global_layer(
        tmp_path, monkeypatch):
    """The exact case CI caught: a global config carrying `schema` must not
    leak into a repo that does not have its own -- an unmigrated v1 repo
    must not read as current just because someone's global file says 2."""
    _global(tmp_path, monkeypatch, contents={"schema": 1})
    root = crew_fixtures.make_repo(
        tmp_path, config={"tier": 0, "roles": []}, git=False)  # no schema key

    resolved = crew_config.resolve_config(str(root))

    assert "schema" not in resolved
    assert resolved.get("schema") != 1


def test_resolve_config_schema_comes_from_the_repo_file_when_present(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": 2}, git=False)
    # 2, not SCHEMA_CURRENT: the point is that the REPO FILE's own number is
    # what comes back, whatever this release's current one happens to be.
    assert crew_config.resolve_config(str(root))["schema"] == 2


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
    _global(tmp_path, monkeypatch,
            contents={"pm": {"authority": "act", "maxDispatches": 9}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT,
                          "tier": 0, "roles": []})

    got = crew_config.layered_state(str(root))

    assert got["isCrew"] is True
    assert got["pm"]["authority"] == "act"
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
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT, "tier": 0, "roles": []})

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
        tmp_path, config={"schema": crew_state.SCHEMA_CURRENT, "tier": 0, "roles": []})  # no tracker

    assert crew_state.collect(str(root))["tracker"] is None
    assert crew_config.layered_state(str(root))["tracker"] == "files"


# --- explain_config: the source column -------------------------------------


def _sources(rows):
    return {row["path"]: (row["value"], row["source"]) for row in rows}


def test_explain_names_the_layer_that_decided_each_value(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "qa": {"provider": "codex"}, "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(
        tmp_path, config={"qa": {"provider": "copilot"}}, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))

    assert got["qa.provider"] == ("copilot", "repo")
    assert got["pm.authority"] == ("act", "global")
    assert got["dev.provider"] == ("claude", "default")


def test_explain_reports_the_pm_regression_out_loud(tmp_path, monkeypatch):
    """The incident: a global file with tier, roles, qa and sdp but NO pm
    block resolved every repo to report-only while the user believed the PM
    was autonomous. Nothing surfaced it, because every file was valid."""
    path = _global(tmp_path, monkeypatch, contents={
        "tier": 2, "roles": ["explorer"], "qa": {"provider": "codex"},
        "sdp": {"closeOnDone": True}})
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 2}, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))
    assert got["pm.authority"] == ("report-only", "default")

    report = crew_config.inspect_global(str(root), str(path))
    kinds = {f["kind"]: f["detail"] for f in report["findings"]}
    assert "pm.authority" in kinds["missing-keys"]
    assert "report-only" in kinds["authority"] and "default" in kinds["authority"]


def test_explain_ignores_a_scalar_where_a_block_belongs(tmp_path, monkeypatch):
    """merge_defaults discards it, so the layer did NOT supply the value --
    and a source column that said otherwise would be worse than none."""
    path = _global(tmp_path, monkeypatch, contents={"pm": "act"})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)

    got = _sources(crew_config.explain_config(str(root), str(path)))
    assert got["pm.authority"] == ("report-only", "default")


def test_explain_works_with_no_repo_at_all(tmp_path, monkeypatch):
    """/crew:config is reachable standalone, for a user with no repo in mind."""
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    got = _sources(crew_config.explain_config(str(tmp_path / "nowhere"), str(path)))
    assert got["pm.authority"] == ("act", "global")


# --- inspect_global: what /crew:upgrade reports -----------------------------


def _kinds(root, path):
    return [f["kind"] for f in crew_config.inspect_global(root, path)["findings"]]


def test_inspect_reports_an_absent_global_file(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert "absent" in _kinds(str(root), str(path))


def test_inspect_reports_a_global_file_that_does_not_parse(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents=None)
    path.write_text("{ half-edited", encoding="utf-8")
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert "unreadable" in _kinds(str(root), str(path))


def test_inspect_reports_repo_keys_and_an_inert_schema(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "schema": 2, "tracker": "jira", "pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    kinds = {f["kind"]: f["detail"]
             for f in crew_config.inspect_global(str(root), str(path))["findings"]}
    assert "tracker" in kinds["repo-keys"]
    assert "inert-schema" in kinds


def test_inspect_never_writes_anything(tmp_path, monkeypatch):
    """upgrade.md's step 5 is "Report - do not resolve", and this is the
    strongest version of that rule: the file is outside the repo."""
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    before = path.read_bytes()
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    crew_config.inspect_global(str(root), str(path))
    assert path.read_bytes() == before


# --- writing the global file -----------------------------------------------


def test_a_write_merges_and_preserves_unknown_keys(tmp_path, monkeypatch):
    """A walkthrough that asks about six settings must not cost the seventh."""
    path = _global(tmp_path, monkeypatch, contents={
        "tracker": "jira", "somethingNobodyHereKnows": {"a": 1},
        "pm": {"authority": "report-only", "quietLines": 3}})

    merged, changes = crew_config.write_global_config(
        {"pm.authority": "act"}, str(path))

    assert merged["tracker"] == "jira"
    assert merged["somethingNobodyHereKnows"] == {"a": 1}
    assert merged["pm"]["quietLines"] == 3
    assert merged["pm"]["authority"] == "act"
    assert json.loads(path.read_text(encoding="utf-8")) == merged
    assert [c["path"] for c in changes] == ["pm.authority"]


def test_a_write_refuses_a_key_that_describes_a_repository(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    before = path.read_bytes()
    for repo_key in ("tracker", "jira.project", "graph.out", "tier", "roles"):
        with pytest.raises(crew_config.GlobalWriteRefused) as caught:
            crew_config.write_global_config({repo_key: "x"}, str(path))
        assert repo_key in str(caught.value)
    assert path.read_bytes() == before


def test_obsidian_confirmed_is_not_settable_from_a_guided_flow(tmp_path, monkeypatch):
    """Consent to write into the user's own notes outside the repo, not a
    capability. Un-grantable here by construction, not by remembering."""
    path = _global(tmp_path, monkeypatch, contents={})
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config(
            {"graph.obsidian.confirmed": True}, str(path))


def test_a_widening_of_authority_is_always_marked(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, contents={
        "pm": {"authority": "report-only"}})
    _, changes = crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert changes[0]["widens_authority"] is True

    # Narrowing is not a widening, and neither is a no-op.
    path.write_text(json.dumps({"pm": {"authority": "act"}}), encoding="utf-8")
    _, narrowing = crew_config.plan_global_write(
        {"pm.authority": "report-only"}, str(path))
    assert narrowing[0]["widens_authority"] is False
    _, nothing = crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert not nothing


def test_a_plan_writes_nothing(tmp_path, monkeypatch):
    """Dry run is the default, and it is what the user says yes to."""
    path = _global(tmp_path, monkeypatch, contents=None)
    crew_config.plan_global_write({"pm.authority": "act"}, str(path))
    assert not path.exists()


def test_a_write_creates_the_directory_when_there_is_no_global_file(
        tmp_path, monkeypatch):
    path = tmp_path / "fresh" / "crew" / "config.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    merged, changes = crew_config.write_global_config({"pm.authority": "act"})
    assert merged == {"pm": {"authority": "act"}}
    assert changes[0]["before"] is None
    assert json.loads(path.read_text(encoding="utf-8")) == merged


def test_a_written_global_file_does_not_leak_a_repo_key(tmp_path, monkeypatch):
    """Every key the walkthrough can write is a machine fact, so a global file
    it produced cannot carry a repo one into a repo that did not ask."""
    path = tmp_path / "written.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    updates = {p: None for p in
               crew_config.leaf_paths(crew_config.default_global_config())}
    merged, _ = crew_config.write_global_config(updates)
    root = crew_fixtures.make_repo(tmp_path, config={"schema": crew_state.SCHEMA_CURRENT}, git=False)
    resolved = crew_config.resolve_config(str(root))
    assert resolved["tracker"] == "files"
    assert resolved["graph"]["out"] == crew_state.GRAPH_OUT_DEFAULT
    assert "schema" not in merged


# --- the CLI ---------------------------------------------------------------


def test_cli_set_is_a_dry_run_without_apply(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'pm.authority="act"']) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "pm.authority" in out
    assert "! pm.authority widens" in out
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_cli_apply_writes(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'qa.provider="codex"',
         "--apply"]) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "qa": {"provider": "codex"}}
    assert "wrote" in capsys.readouterr().out


def test_cli_refuses_a_repo_key_with_exit_two(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={})
    assert crew_config.main(
        ["--global-path", str(path), "--set", 'tracker="jira"', "--apply"]) == 2
    assert "tracker" in capsys.readouterr().err


def test_cli_reporting_exits_zero_even_with_findings(tmp_path, monkeypatch, capsys):
    """A machine with no global config is a normal machine. /crew:upgrade
    reads this output, not its status."""
    path = _global(tmp_path, monkeypatch, contents=None)
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert crew_config.main(
        ["--root", str(root), "--global-path", str(path), "--check-global"]) == 0
    assert "absent" in capsys.readouterr().out


def test_cli_explain_prints_a_source_column(tmp_path, monkeypatch, capsys):
    path = _global(tmp_path, monkeypatch, contents={"pm": {"authority": "act"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert crew_config.main(
        ["--root", str(root), "--global-path", str(path), "--explain"]) == 0
    out = capsys.readouterr().out
    assert "source" in out
    assert "pm.authority" in out and "global" in out


# --- _layer_supplies agrees with merge_defaults, by construction -----------
#
# `_layer_supplies` is a second implementation of `merge_defaults`' policy:
# it answers "which layer decided this value", which the merged result cannot
# be asked. Two implementations of one rule drift, and the drift is silent --
# the source column would name the wrong layer and nothing would fail. These
# tests pin them to each other by running both, rather than by asserting the
# mirror in a docstring.


_SENTINEL = "___layer_value___"


def _dig_or_missing(node, parts):
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return crew_config._MISSING  # pylint: disable=protected-access
        node = node[part]
    return node


def _layer_carrying(parts, value):
    """A config whose only content is `value` at the dotted path `parts`."""
    out = {}
    node = out
    for part in parts[:-1]:
        node[part] = {}
        node = node[part]
    node[parts[-1]] = value
    return out


def _decided_by_layer(defaults, layer, parts):
    """Ground truth: did the layer's value survive the real merge?"""
    merged = crew_state.merge_defaults(copy.deepcopy(defaults), layer)
    return _dig_or_missing(merged, parts) == _SENTINEL


@pytest.mark.parametrize(
    "path", sorted(crew_config.leaf_paths(crew_config.default_global_config())))
def test_layer_supplies_agrees_with_merge_defaults_on_every_global_leaf(path):
    """Every key the walkthrough can set, set by a layer, is credited to it."""
    defaults = crew_config.default_config()
    parts = tuple(path.split("."))
    layer = _layer_carrying(parts, _SENTINEL)
    # pylint: disable=protected-access
    assert (crew_config._layer_supplies(layer, parts, defaults)
            is _decided_by_layer(defaults, layer, parts))


def test_layer_supplies_agrees_when_the_layer_is_silent():
    """A layer that says nothing decides nothing, at every depth."""
    defaults = crew_config.default_config()
    for path in crew_config.leaf_paths(crew_config.default_global_config()):
        parts = tuple(path.split("."))
        # pylint: disable=protected-access
        assert crew_config._layer_supplies({}, parts, defaults) is False


def test_layer_supplies_agrees_on_the_scalar_over_dict_discard():
    """merge_defaults throws a scalar-over-dict away; so must the credit.

    This is the one rule of the two that is easy to get wrong, and getting it
    wrong reads as "global set qa" when the global file's `"qa": "codex"` was
    discarded and the built-in default is what actually applies.
    """
    defaults = crew_config.default_config()
    # `qa` holds a dict by default, so a scalar there is discarded whole.
    layer = {"qa": _SENTINEL}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa", "provider"),
                                       defaults) is False
    merged = crew_state.merge_defaults(copy.deepcopy(defaults), layer)
    assert merged["qa"] == defaults["qa"], "merge_defaults kept the scalar"


def test_layer_supplies_credits_a_whole_subtree_replacement():
    """Where the default holds no dict, the layer replaces the subtree.

    `merge_defaults` only recurses where BOTH sides hold a dict, so a layer
    supplying a block the defaults do not model wins outright -- and the
    credit has to follow, or a user-invented key would read as `default`.
    """
    defaults = {"pm": {"authority": "report-only"}}
    layer = {"custom": {"nested": _SENTINEL}}
    parts = ("custom", "nested")
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, parts, defaults) is True
    assert _decided_by_layer(defaults, layer, parts) is True


def test_layer_supplies_discards_a_scalar_named_at_a_block_path():
    """A layer naming a whole block with a scalar decides nothing there.

    The path here is `qa` itself, not a leaf under it. `leaf_paths` never
    yields such a path, so nothing else in this file exercises the last hop
    of `_layer_supplies` -- and an unexercised branch is how the mirror
    drifts from `merge_defaults` without a test noticing.
    """
    defaults = crew_config.default_config()
    layer = {"qa": _SENTINEL}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa",), defaults) is False
    assert _decided_by_layer(defaults, layer, ("qa",)) is False


def test_layer_supplies_credits_a_block_replaced_by_a_block():
    """A dict over a dict default is a real override, at the block path too."""
    defaults = crew_config.default_config()
    layer = {"qa": {"provider": _SENTINEL}}
    # pylint: disable=protected-access
    assert crew_config._layer_supplies(layer, ("qa", "provider"),
                                       defaults) is True
    assert _decided_by_layer(defaults, layer, ("qa", "provider")) is True


# --- a per-role pin, layered ------------------------------------------------
#
# `/crew:model` tells a user to put a project's pin in the repo file and a
# person's in the global one, which only works if the two layer sensibly at
# the ROLE level. `merge_defaults` recurses to whatever depth both sides hold
# a dict, so they merge per key rather than the repo's object replacing the
# global's wholesale -- documented behaviour deserves a test, whichever way it
# turns out to go.


def test_a_repo_pin_merges_into_a_global_one_rather_than_replacing_it(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "dev": {"roles": {"developer": {"provider": "codex",
                                        "model": "gpt-5.6-sol"}}},
    })
    root = crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "dev": {"roles": {"developer": {"model": "gpt-6-astra"}}},
    }, git=False)

    resolved = crew_config.resolve_config(str(root))
    pin = resolved["dev"]["roles"]["developer"]

    assert pin["model"] == "gpt-6-astra"     # the repo decided the model
    assert pin["provider"] == "codex"        # and the global provider survived
    assert crew_state.resolve_role(resolved, "dev", "developer")["family"] \
        == "gpt"


def test_a_global_pin_reaches_a_role_the_repo_never_mentions(
        tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, contents={
        "qa": {"roles": {"review": {"provider": "copilot",
                                    "model": "kimi-k2.7-code"}}},
    })
    root = crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT}, git=False)

    got = crew_state.resolve_role(crew_config.resolve_config(str(root)),
                                  "qa", "review")

    assert got["provider"] == "copilot"
    assert got["family"] == "kimi"
    assert got["source"] == "role-pin"
