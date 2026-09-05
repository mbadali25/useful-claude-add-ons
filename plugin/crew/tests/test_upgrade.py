"""Tests for codemap/graph reconciliation and the v1 -> v2 upgrade."""
import json
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state
import crew_upgrade
import graph_reconcile


def test_head_never_inherits_the_parent_stdin(tmp_path, monkeypatch):
    """crew_upgrade._head must pin stdin, for the same reason git_out does
    in crew_state.py: an inherited stdin handle is torn down and rebuilt by
    pytest's fd capturing on every test, and the resulting transient OSError
    (WinError 6 on Windows, EBADF on a CI runner whose stdin is a pipe) is
    swallowed by _head's except clause and turned into a silently wrong
    None -- indistinguishable from git being absent.
    """
    calls = []
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        calls.append(kwargs)
        return real_run(*args, **kwargs)  # pylint: disable=subprocess-run-check

    monkeypatch.setattr(crew_upgrade.subprocess, "run", recording_run)

    root = crew_fixtures.make_repo(tmp_path)
    assert crew_upgrade._head(str(root))  # pylint: disable=protected-access

    assert calls, "expected _head to have called subprocess.run"
    for kwargs in calls:
        assert kwargs.get("stdin") == subprocess.DEVNULL, (
            "_head's subprocess.run call is missing stdin=subprocess.DEVNULL "
            f"-- kwargs were: {kwargs}"
        )

V1_MAP = """# auth
anchor: repo@0000000
verified: 2026-01-01

## Does
Authenticates requests.

## Entry points
- `src/auth.py:10` — called by the router

## Calls out to
- billing at `src/auth.py:99`

## Landmines
- The session cache is not invalidated on password change.

## Unverified
- Whether the legacy path is still reachable.
"""


def test_split_sections_finds_every_heading():
    got = graph_reconcile.split_sections(V1_MAP)
    assert set(got) >= {"Does", "Entry points", "Calls out to",
                        "Landmines", "Unverified"}


def test_landmines_survive_byte_identical():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": ["- `x.py:1` — new"]})
    assert "The session cache is not invalidated on password change." in out["body"]


def test_does_section_survives():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Authenticates requests." in out["body"]


def test_derived_facts_are_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    )
    assert "src/cli.py:7" in out["body"]
    assert "Entry points" in out["touched"]


def test_a_line_number_shift_is_not_a_conflict():
    """The noise case. The map says src/auth.py:10, the graph says :44 --
    same file, moved line. Reporting that as a contradiction would make
    UPGRADE.md mostly line-drift noise on any repo that has been refactored,
    and a report nobody reads protects nothing.
    """
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/auth.py:44` — called by the cron"]}
    )
    assert out["conflicts"] == []  # pylint: disable=use-implicit-booleaness-not-comparison
    assert "src/auth.py:10" in out["body"]   # the human's note is still there
    assert out["added"] == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_a_file_the_graph_does_not_know_is_a_conflict():
    # billing.py is claimed by the map and absent from the graph entirely.
    out = graph_reconcile.reconcile(
        V1_MAP, {"Calls out to": ["- payments at `src/pay.py:3`"]}
    )
    assert "src/billing.py" not in V1_MAP  # guard: the fixture says `src/auth.py:99`
    assert any("auth.py" in c for c in out["conflicts"])
    assert "src/auth.py:99" in out["body"]  # kept regardless


def test_a_new_file_from_the_graph_is_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cron.py:1` — called by the scheduler"]}
    )
    assert "src/cron.py:1" in out["body"]
    assert out["added"]
    assert "Entry points" in out["touched"]


def test_a_keep_section_is_never_touched_even_if_derived_is_supplied():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Landmines": ["- graph says something"]}
    )
    assert "graph says something" not in out["body"]
    assert "Landmines" not in out["touched"]


def test_untouched_sections_are_not_in_touched():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Calls out to" not in out["touched"]


def test_reconcile_is_idempotent():
    derived = {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    once = graph_reconcile.reconcile(V1_MAP, derived)
    assert once["added"], "first pass must actually add something"
    twice = graph_reconcile.reconcile(once["body"], derived)
    assert twice["body"] == once["body"]
    assert twice["added"] == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_a_heading_the_map_never_had_is_created_not_dropped():
    """The silent-loss case.

    A v1 note written before anyone recorded owned tables is exactly the note
    most likely to lack the heading, and exactly the one the graph has most to
    add to. Dropping those facts without a word is the worst shape a gap can
    take in an upgrade tool.
    """
    note = "# a\n\n## Does\nthing\n\n## Landmines\n- keep me\n"
    out = graph_reconcile.reconcile(
        note, {"Owns data": ["- users via `src/db.py:4`"]}
    )
    assert "users via" in out["body"]
    assert out["added"]
    assert "Owns data" in out["touched"]
    assert "- keep me" in out["body"]


def test_creating_a_heading_is_idempotent():
    note = "# a\n\n## Does\nthing\n"
    derived = {"Owns data": ["- users via `src/db.py:4`"]}
    once = graph_reconcile.reconcile(note, derived)
    twice = graph_reconcile.reconcile(once["body"], derived)
    assert twice["added"] == []  # pylint: disable=use-implicit-booleaness-not-comparison
    assert twice["body"] == once["body"]


def test_an_empty_derived_list_does_not_create_an_empty_heading():
    note = "# a\n\n## Does\nthing\n"
    out = graph_reconcile.reconcile(note, {"Owns data": []})
    assert "Owns data" not in out["body"]
    assert out["touched"] == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_conflict_strings_are_ascii():
    # /crew:upgrade reports these, and a cp437 console cannot encode an em-dash.
    note = "# a\n\n## Entry points\n- `src/auth.py:10` - router\n"
    out = graph_reconcile.reconcile(
        note, {"Entry points": ["- `src/cron.py:1` - cron"]}
    )
    assert out["conflicts"]
    for line in out["conflicts"]:
        line.encode("ascii")


def _cfg(cfg):
    """`upgrade_config`'s config half.

    It returns `(out, notes)` as of 0.16.0 -- the notes are what the run has
    to SAY, and a caller that only wants the dict has to say so. The tests
    below that are about the notes call `crew_upgrade.upgrade_config` directly.
    """
    out, _ = crew_upgrade.upgrade_config(cfg)
    return out


def test_upgrade_config_stamps_the_current_schema():
    assert _cfg({})["schema"] == crew_state.SCHEMA_CURRENT


def test_upgrade_config_adds_pm_and_graph_blocks():
    got = _cfg({"tier": 0})
    assert got["pm"]["mode"] == "adaptive"
    assert got["pm"]["authority"] == "report-only"
    assert got["graph"]["mode"] == "code-only"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_a_specialist_role_is_kept_and_not_reported_as_unknown():
    """`rolesUnknown` drives a report line reading "kept, not on this
    release's ladder", which is true of a typo and false of a specialist.
    A repo that deliberately onboarded `node-developer` would otherwise be
    told on every single upgrade that crew does not recognise it.
    """
    _out, notes = crew_upgrade.upgrade_config(
        {"roles": ["explorer", "node-developer", "wharrgarbl"], "tier": 0})

    assert "node-developer" not in notes["rolesUnknown"]
    assert "wharrgarbl" in notes["rolesUnknown"]


def test_a_specialist_survives_the_upgrade_it_did_not_ask_for():
    out, _notes = crew_upgrade.upgrade_config(
        {"roles": ["explorer", "node-developer"], "tier": 2})

    assert "node-developer" in out["roles"], "an opted-in role must not vanish"
    # ...and the upgrade still must not ADD one.
    assert "sharepoint-developer" not in out["roles"]


def test_upgrade_config_preserves_unknown_keys():
    # A config written by a newer crew than the one running must survive.
    got = _cfg({"somethingNew": {"a": 1}, "tier": 2})
    assert got["somethingNew"] == {"a": 1}
    assert got["tier"] == 2


def test_upgrade_config_does_not_clobber_an_existing_pm_block():
    got = _cfg({"pm": {"quietLines": 3}})
    assert got["pm"]["quietLines"] == 3
    assert got["pm"]["mode"] == "adaptive"  # defaults still filled in


def test_a_wrong_typed_nested_block_is_kept_and_reported_not_destroyed():
    """The nested shape case none of the other guards reach.

    /crew:upgrade runs against a real repository and run() writes the config
    before reconciling the codemap, so a crash here is a migration that dies
    partway, not merely a silent session. It must not crash -- and, since
    0.16.0, it must not quietly swallow the value either.

    Until 0.16.0 the merge replaced a wrong-typed nested value with the
    default, added nothing to `unmigrated`, and stamped the schema current:
    the config came back looking migrated with the user's value gone. The
    contract now matches what the report has always claimed -- "left exactly
    as written".
    """
    for bad in ("yes", 1, ["a"], None, 0, True):
        got, notes = crew_upgrade.upgrade_config({"graph": {"obsidian": bad}})
        # Kept verbatim, not replaced by the default block.
        assert got["graph"]["obsidian"] == bad, bad
        # Named, so the operator can fix it by hand.
        assert "graph.obsidian" in notes["unmigrated"], bad
        # And NOT claimed as current, so the next run retries it.
        assert notes["schemaStamped"] is False, bad
        assert got.get("schema") != crew_state.SCHEMA_CURRENT, bad


def test_a_legitimate_nested_override_still_wins():
    got = _cfg(
        {"pm": {"quietLines": 3}, "graph": {"obsidian": {"dir": "/vault"}}}
    )
    assert got["pm"]["quietLines"] == 3
    assert got["pm"]["mode"] == "adaptive"          # default still filled in
    assert got["graph"]["obsidian"]["dir"] == "/vault"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_obsidian_confirmed_defaults_false_even_if_dir_is_set():
    got = _cfg(
        {"graph": {"obsidian": {"dir": "/somewhere"}}}
    )
    assert got["graph"]["obsidian"]["dir"] == "/somewhere"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_upgrade_config_does_not_alias_the_shared_graph_block():
    got = _cfg({})
    assert got["graph"]["obsidian"] is not crew_upgrade.GRAPH_BLOCK["obsidian"]
    assert crew_upgrade.GRAPH_BLOCK["obsidian"]["confirmed"] is False


def test_backup_is_taken_before_any_write(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    crew_upgrade.run(str(root), {})
    backup = root / ".crew" / "codemap.v1.bak" / "auth.md"
    assert backup.read_text(encoding="utf-8") == V1_MAP


def test_run_writes_the_current_schema_to_disk(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert cfg["schema"] == crew_state.SCHEMA_CURRENT


def test_second_run_reports_already_current(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    assert crew_upgrade.run(str(root), {})["status"] == "already current"


def test_force_reruns_a_current_setup(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"schema": crew_state.SCHEMA_CURRENT})
    assert crew_upgrade.run(str(root), {}, force=True)["status"] == "upgraded"


def test_conflicts_land_in_the_report_not_in_the_map(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    # The graph knows src/cron.py and does NOT know src/auth.py at all, so the
    # map's src/auth.py claim is a genuine contradiction rather than line drift.
    derived = {"auth": {"Entry points": ["- `src/cron.py:1` — scheduler"]}}
    out = crew_upgrade.run(str(root), derived)
    report = (root / ".crew" / "codemap" / "UPGRADE.md").read_text(encoding="utf-8")
    assert "auth.py" in report
    body = (root / ".crew" / "codemap" / "auth.md").read_text(encoding="utf-8")
    assert "src/auth.py:10" in body   # the contradicted claim is KEPT
    assert "src/cron.py:1" in body    # the graph's fact is ADDED
    assert out["conflicts"]


def test_report_does_not_double_prefix_the_no_conflicts_line(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    crew_upgrade.run(str(root), {})
    report = (root / ".crew" / "codemap" / "UPGRADE.md").read_text(encoding="utf-8")
    assert "- - none" not in report
    assert "- none" in report


def test_anchor_is_bumped_only_on_a_touched_file(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"tier": 0},
        codemap={"auth": V1_MAP, "billing": V1_MAP.replace("# auth", "# billing")},
    )
    derived = {"auth": {"Entry points": ["- `src/cron.py:1` — scheduler"]}}
    crew_upgrade.run(str(root), derived)
    head = crew_fixtures.head_sha(root)
    auth = (root / ".crew" / "codemap" / "auth.md").read_text(encoding="utf-8")
    billing = (root / ".crew" / "codemap" / "billing.md").read_text(encoding="utf-8")
    assert head in auth
    # billing was not re-verified, so claiming freshness for it would be a lie.
    assert head not in billing
    assert "0000000" in billing


def test_run_on_a_repo_with_no_codemap_still_upgrades_config(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    assert crew_upgrade.run(str(root), {})["status"] == "upgraded"


def test_run_on_a_non_crew_directory_reports_not_crew(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert crew_upgrade.run(str(plain), {})["status"] == "not a crew repo"


def test_bom_prefixed_config_upgrades_normally(tmp_path):
    # Windows Notepad's default save. Must not be treated as unreadable, and
    # every existing key -- including one this module has never heard of --
    # must survive the round trip.
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text(
        json.dumps({
            "tier": 2,
            "roles": ["explorer", "dba"],
            "tracker": "jira",
            "jira": {"cloudId": "abc", "project": "PROJ"},
            "myCustomKey": {"anything": "goes"},
        }),
        encoding="utf-8-sig",
    )
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "upgraded"
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert cfg["tier"] == 2
    # Roles migrate forward now, so this is a superset rather than an
    # equality -- what this test is about is that the BOM did not eat the
    # file, not the ladder.
    assert {"explorer", "dba"} <= set(cfg["roles"])
    assert cfg["tracker"] == "jira"
    assert cfg["jira"] == {"cloudId": "abc", "project": "PROJ"}
    assert cfg["myCustomKey"] == {"anything": "goes"}
    assert cfg["schema"] == crew_state.SCHEMA_CURRENT


def test_unparseable_config_is_refused_not_overwritten(tmp_path):
    # This is the destructive case BLOCK B exists to close: a config that
    # fails to parse must be reported and left byte-identical, never
    # silently replaced with upgrade_config({}).
    root = crew_fixtures.make_repo(tmp_path)
    original = "{not valid json at all"
    (root / ".crew" / "config.json").write_text(original, encoding="utf-8")
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "config unreadable"
    assert (root / ".crew" / "config.json").read_text(encoding="utf-8") == original
    assert not (root / ".crew" / "config.json.v1.bak").exists()


def test_null_schema_does_not_raise(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"schema": None, "tier": 1})
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "upgraded"
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert cfg["schema"] == crew_state.SCHEMA_CURRENT
    assert cfg["tier"] == 1


def test_absent_config_is_unchanged(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert not (root / ".crew" / "config.json").exists()
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "not a crew repo"
    assert not (root / ".crew" / "config.json").exists()


def test_config_is_backed_up_before_being_overwritten(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    backup = root / ".crew" / "config.json.v1.bak"
    assert json.loads(backup.read_text(encoding="utf-8")) == {"tier": 0}


def test_config_backup_is_not_overwritten_by_a_second_run(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    backup = root / ".crew" / "config.json.v1.bak"
    backup.write_text('{"sentinel": true}', encoding="utf-8")
    crew_upgrade.run(str(root), {}, force=True)
    assert json.loads(backup.read_text(encoding="utf-8")) == {"sentinel": True}


# --- 0.16.0: qa, dev, roles and tier migrate too ---------------------------


def test_upgrade_config_brings_the_provider_table_forward():
    """The reported bug. A config predating 0.14.4 has neither `qa.order` nor
    a `dev` block, and an absent `qa.order` made /crew:model report zero
    candidates and "no independent reviewer" for a setup that reviews fine."""
    got = _cfg({"tier": 0, "roles": ["explorer", "qa-reviewer"],
                "qa": {"provider": "codex"}})
    assert got["qa"]["order"] == ["codex", "copilot", "claude"]
    assert got["qa"]["provider"] == "codex"          # the user's value survives
    assert got["qa"]["codex"] == {"model": None, "reasoningEffort": None}
    assert got["dev"] == crew_state.DEV_DEFAULTS


def test_upgrade_config_does_not_alias_the_shared_provider_blocks():
    got = _cfg({})
    got["qa"]["codex"]["model"] = "mutated"
    got["dev"]["copilot"]["model"] = "mutated"
    assert crew_state.QA_DEFAULTS["codex"]["model"] is None
    assert crew_state.DEV_DEFAULTS["copilot"]["model"] is None


def test_upgrade_adds_roles_the_declared_tier_already_entitles():
    """Adding, not reporting: the decision the spec records. A repo already at
    tier 2 gets the tier-2 roles later releases added."""
    got, notes = crew_upgrade.upgrade_config(
        {"tier": 2, "roles": ["explorer", "qa-reviewer", "developer",
                              "docs-writer", "planner"]})
    for role in ("dba", "browser-tester", "analyst", "security",
                 "smoke-author", "infrastructure-architect", "scribe",
                 "researcher"):
        assert role in got["roles"], role
    assert notes["rolesAdded"] == [
        "security", "smoke-author", "dba", "browser-tester", "analyst",
        "infrastructure-architect", "scribe", "researcher"]
    assert notes["tierFrom"] == 2 and notes["tierTo"] == 2


def test_upgrade_never_grows_a_crew_past_its_declared_tier():
    """The guard that keeps "add the new roles" from meaning "add every role".
    Moving UP a tier is /crew:scale's job and needs evidence."""
    got, notes = crew_upgrade.upgrade_config(
        {"tier": 0, "roles": ["explorer", "qa-reviewer"]})
    assert got["roles"] == ["explorer", "qa-reviewer"]
    assert not notes["rolesAdded"]
    assert notes["tierTo"] == 0


def test_upgrade_recomputes_tier_from_the_roles_actually_listed():
    """A config claiming tier 0 while listing `planner` is at tier 2 whatever
    the number says -- and the report has to name the move."""
    got, notes = crew_upgrade.upgrade_config(
        {"tier": 0, "roles": ["explorer", "planner"]})
    assert got["tier"] == 2
    assert notes["tierFrom"] == 0 and notes["tierTo"] == 2
    assert "dba" in got["roles"]


def test_upgrade_keeps_a_role_this_release_does_not_know():
    got, notes = crew_upgrade.upgrade_config(
        {"tier": 1, "roles": ["explorer", "house-style-cop"]})
    assert "house-style-cop" in got["roles"]
    assert notes["rolesUnknown"] == ["house-style-cop"]
    # Unknown to the ladder means its tier is genuinely unknown; guessing one
    # would move a crew up on the strength of a string nobody recognises.
    assert notes["tierTo"] == 1


def test_upgrade_never_removes_a_role():
    """Offboarding keeps its explicit-yes gate; nothing here may take a role
    away. Removing one destroys the coverage that would have told you whether
    the removal was right."""
    before = ["explorer", "qa-reviewer", "planner", "something-custom"]
    got, _ = crew_upgrade.upgrade_config({"tier": 2, "roles": before})
    assert set(before) <= set(got["roles"])


def test_a_wrong_typed_block_is_left_alone_and_schema_is_not_stamped():
    """`schema` stamped current unconditionally is how the whole class of bug
    stayed invisible: the next run reports "already current" and skips."""
    for key in ("pm", "graph", "qa", "dev"):
        got, notes = crew_upgrade.upgrade_config({key: "oops", "tier": 0})
        assert got[key] == "oops", key            # the user's value, untouched
        assert notes["unmigrated"] == [key], key
        assert notes["schemaStamped"] is False, key
        assert "schema" not in got, key


def test_wrong_typed_roles_is_reported_not_silently_replaced():
    got, notes = crew_upgrade.upgrade_config({"roles": "explorer", "tier": 2})
    assert got["roles"] == "explorer"
    assert notes["unmigrated"] == ["roles"]
    assert "schema" not in got


def test_run_reports_unmigrated_blocks_in_its_status(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0, "qa": "oops"})
    out = crew_upgrade.run(str(root), {})
    assert out["status"] == "upgraded with unmigrated blocks"
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert "schema" not in cfg
    # And the repo therefore still reports an upgrade as needed, rather than
    # being marked done with a block nobody migrated.
    again = crew_upgrade.run(str(root), {})
    assert again["status"] == "upgraded with unmigrated blocks"


def test_the_report_states_roles_added_and_the_tier_move(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"tier": 2, "roles": ["explorer", "qa-reviewer"]},
        codemap={"auth": V1_MAP})
    out = crew_upgrade.run(str(root), {})
    assert "## Config" in out["report"]
    assert "roles added: security" in out["report"]
    assert "planner" in out["report"]
    written = (root / ".crew" / "codemap" / "UPGRADE.md").read_text(encoding="utf-8")
    assert written == out["report"]


# --- 0.16.0: schema 2 -> 3, the per-role provider table --------------------
#
# Bumping SCHEMA_CURRENT makes every existing crew repo report `upgradeNeeded`
# at session start, so this migration is mandatory rather than optional. A
# mandatory migration that silently re-routed someone's development work to a
# different model would be indefensible, so the identical-behaviour property
# is PROVEN here rather than asserted in a docstring -- and proven on the
# resolver, not on the dict, since the dict obviously differs once keys are
# added.


# A config exactly as 0.15.x wrote it: the 0.14.4 provider table, no per-role
# entries, no fallback, `schema: 2`.
V2_CONFIG = {
    "schema": 2,
    "tier": 1,
    "roles": ["explorer", "qa-reviewer", "security", "smoke-author",
              "developer"],
    "qa": {
        "provider": "auto",
        "order": ["codex", "copilot", "claude"],
        "codex": {"model": None, "reasoningEffort": "high"},
        "copilot": {"model": "kimi-k3"},
    },
    "dev": {
        "provider": "codex",
        "codex": {"model": "gpt-6-astra", "reasoningEffort": None},
        "copilot": {"model": None},
    },
    "tracker": "files",
}

_EVERY_ROLE = (crew_state.QA_ROLE_KINDS + crew_state.DEV_ROLE_KINDS
               + ("something-nobody-named",))


def _dispatch(cfg):
    """Every role's resolved provider/model/family, for both blocks."""
    out = {}
    for kind in ("qa", "dev"):
        for role in _EVERY_ROLE:
            got = crew_state.resolve_role(cfg, kind, role)
            out[f"{kind}.{role}"] = (got["provider"], got["model"],
                                     got["family"], got["reasoningEffort"])
    return out


def test_a_v2_config_migrates_to_v3_with_identical_dispatch():
    """The behaviour gate. Every role resolves to the same provider, model,
    family and reasoning effort before and after -- so a repo that upgrades
    keeps dispatching exactly where it did, and opting in stays a choice."""
    before = _dispatch(V2_CONFIG)
    after, _ = crew_upgrade.upgrade_config(V2_CONFIG)

    assert _dispatch(after) == before
    # And the values themselves are the v2 ones, not coincidentally-equal
    # defaults -- a resolver that returned None for everything would satisfy
    # the equality above and prove nothing.
    assert before["dev.developer"] == ("codex", "gpt-6-astra", "gpt", None)
    assert before["qa.review"] == ("auto", None, None, None)


def test_the_migration_adds_the_schema_3_keys_empty():
    got, notes = crew_upgrade.upgrade_config(V2_CONFIG)

    assert got["schema"] == 3
    assert got["qa"]["roles"] == {}  # pylint: disable=use-implicit-booleaness-not-comparison
    assert got["dev"]["roles"] == {}  # pylint: disable=use-implicit-booleaness-not-comparison
    assert got["qa"]["fallback"] == crew_state.FALLBACK_DEFAULT
    assert got["dev"]["fallback"] == crew_state.FALLBACK_DEFAULT
    assert notes["schemaFrom"] == 2
    assert set(notes["providerKeysAdded"]) == set(crew_upgrade.SCHEMA_3_KEYS)


def test_the_migration_preserves_every_v2_provider_value():
    got, _ = crew_upgrade.upgrade_config(V2_CONFIG)
    assert got["qa"]["codex"]["reasoningEffort"] == "high"
    assert got["qa"]["copilot"]["model"] == "kimi-k3"
    assert got["dev"]["provider"] == "codex"
    assert got["dev"]["codex"]["model"] == "gpt-6-astra"
    assert got["tracker"] == "files"


def test_the_migration_never_writes_a_role_pin_nobody_chose():
    """`/crew:init` and `/crew:upgrade` OFFER the recommended table. Shipping
    it as a migration would route developer work to codex the moment a repo
    upgraded, with no opt-in left to give."""
    got, _ = crew_upgrade.upgrade_config({"schema": 2, "tier": 0,
                                          "roles": ["explorer"]})
    assert got["dev"]["roles"] == {}  # pylint: disable=use-implicit-booleaness-not-comparison
    assert got["dev"]["provider"] == "claude"
    assert crew_state.resolve_role(got, "dev", "developer")["provider"] == "claude"


def test_a_config_that_already_has_the_v3_keys_is_not_reported_as_gaining_them():
    """Computed from the incoming file, not from the version number -- a
    hand-edited config carrying `dev.roles` already must not be reported as
    having just been given it."""
    cfg = json.loads(json.dumps(V2_CONFIG))
    cfg["dev"]["roles"] = {"developer": {"provider": "codex",
                                         "model": "gpt-6-astra"}}
    got, notes = crew_upgrade.upgrade_config(cfg)
    assert "dev.roles" not in notes["providerKeysAdded"]
    assert "qa.roles" in notes["providerKeysAdded"]
    assert got["dev"]["roles"]["developer"]["model"] == "gpt-6-astra"


def test_the_report_states_what_schema_three_added_and_that_it_is_neutral(
        tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=V2_CONFIG,
                                   codemap={"auth": V1_MAP})
    out = crew_upgrade.run(str(root), {})
    assert "dev.roles" in out["report"]
    assert "NEUTRAL" in out["report"]
    assert "dispatches exactly as it did" in out["report"]
    assert "/crew:model" in out["report"]


def test_an_unmigrated_block_is_not_reported_as_having_gained_v3_keys():
    """A `qa` left exactly as the user wrote it did not gain anything, and
    saying otherwise would claim work the migration explicitly declined."""
    _, notes = crew_upgrade.upgrade_config({"qa": "oops", "tier": 0})
    assert not any(k.startswith("qa.") for k in notes["providerKeysAdded"])


def test_the_report_says_so_when_nothing_was_added(tmp_path):
    """Stated every run, including when the answer is none -- a report that
    only speaks up on change cannot be trusted when it is silent."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"tier": 0, "roles": ["explorer", "qa-reviewer"]},
        codemap={"auth": V1_MAP})
    out = crew_upgrade.run(str(root), {})
    assert "roles added: none" in out["report"]
    assert "tier: 0 (unchanged)" in out["report"]
