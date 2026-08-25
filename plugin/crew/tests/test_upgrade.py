"""Tests for codemap/graph reconciliation and the v1 -> v2 upgrade."""
import json

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_upgrade
import graph_reconcile

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


def test_upgrade_config_sets_schema_two():
    assert crew_upgrade.upgrade_config({})["schema"] == 2


def test_upgrade_config_adds_pm_and_graph_blocks():
    got = crew_upgrade.upgrade_config({"tier": 0})
    assert got["pm"]["mode"] == "adaptive"
    assert got["pm"]["authority"] == "report-only"
    assert got["graph"]["mode"] == "code-only"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_upgrade_config_preserves_unknown_keys():
    # A config written by a newer crew than the one running must survive.
    got = crew_upgrade.upgrade_config({"somethingNew": {"a": 1}, "tier": 2})
    assert got["somethingNew"] == {"a": 1}
    assert got["tier"] == 2


def test_upgrade_config_does_not_clobber_an_existing_pm_block():
    got = crew_upgrade.upgrade_config({"pm": {"quietLines": 3}})
    assert got["pm"]["quietLines"] == 3
    assert got["pm"]["mode"] == "adaptive"  # defaults still filled in


def test_a_wrong_typed_block_does_not_crash_the_upgrade():
    """The nested shape case none of the other guards reach.

    /crew:upgrade runs against a real repository and run() writes the config
    before reconciling the codemap, so a crash here is a migration that dies
    partway, not merely a silent session.
    """
    for bad in ("yes", 1, ["a"], None, 0, True):
        got = crew_upgrade.upgrade_config({"graph": {"obsidian": bad}})
        assert got["graph"]["obsidian"]["confirmed"] is False, bad
        assert got["graph"]["obsidian"]["enabled"] is False, bad


def test_a_legitimate_nested_override_still_wins():
    got = crew_upgrade.upgrade_config(
        {"pm": {"quietLines": 3}, "graph": {"obsidian": {"dir": "/vault"}}}
    )
    assert got["pm"]["quietLines"] == 3
    assert got["pm"]["mode"] == "adaptive"          # default still filled in
    assert got["graph"]["obsidian"]["dir"] == "/vault"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_obsidian_confirmed_defaults_false_even_if_dir_is_set():
    got = crew_upgrade.upgrade_config(
        {"graph": {"obsidian": {"dir": "/somewhere"}}}
    )
    assert got["graph"]["obsidian"]["dir"] == "/somewhere"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_upgrade_config_does_not_alias_the_shared_graph_block():
    got = crew_upgrade.upgrade_config({})
    assert got["graph"]["obsidian"] is not crew_upgrade.GRAPH_BLOCK["obsidian"]
    assert crew_upgrade.GRAPH_BLOCK["obsidian"]["confirmed"] is False


def test_backup_is_taken_before_any_write(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    crew_upgrade.run(str(root), {})
    backup = root / ".crew" / "codemap.v1.bak" / "auth.md"
    assert backup.read_text(encoding="utf-8") == V1_MAP


def test_run_writes_schema_two_to_disk(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert cfg["schema"] == 2


def test_second_run_reports_already_current(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    assert crew_upgrade.run(str(root), {})["status"] == "already current"


def test_force_reruns_a_current_setup(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"schema": 2})
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
    assert cfg["roles"] == ["explorer", "dba"]
    assert cfg["tracker"] == "jira"
    assert cfg["jira"] == {"cloudId": "abc", "project": "PROJ"}
    assert cfg["myCustomKey"] == {"anything": "goes"}
    assert cfg["schema"] == 2


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
    assert cfg["schema"] == 2
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
