"""`crew_migrate.py`: preview, apply, rollback, and the crash in between.

Every test runs against a copy under `tmp_path`. The config and metrics are
byte copies of THIS repository's machine-local `.crew/config.json` (schema 7,
53 roles) and `.crew/metrics.md` as they stood on 2026-09-23, kept in
`migrate_fixtures/` because both files are gitignored and a clone has neither.
The codemap is copied from the tracked `.crew/codemap/` at run time.
"""
import builtins
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_migrate

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FIXTURES = os.path.join(HERE, "migrate_fixtures")
TICKET = "# T-0001 Fix the thing\nstatus: open\n\n## Want\nIt works.\n"


def _snapshot(root, skip_backups=True):
    """{relpath: (sha256, mtime_ns)} for every file under root."""
    out = {}
    for base, dirs, files in os.walk(root):
        rel_base = os.path.relpath(base, root).replace(os.sep, "/")
        if skip_backups and rel_base.startswith(".crew/backups"):
            dirs[:] = []
            continue
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            out[os.path.relpath(path, root).replace(os.sep, "/")] = (
                digest, os.stat(path).st_mtime_ns)
        out.update({os.path.relpath(os.path.join(base, d), root).replace(os.sep, "/") + "/": ("dir", 0)
                    for d in dirs})
    if skip_backups:
        out = {k: v for k, v in out.items() if not k.startswith(".crew/backups")}
    return out


def _bytes_only(snap):
    return {k: v[0] for k, v in snap.items()}


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = tmp_path / "repo"
    crew = root / ".crew"
    crew.mkdir(parents=True)
    shutil.copy(os.path.join(FIXTURES, "config.json"), crew / "config.json")
    shutil.copy(os.path.join(FIXTURES, "metrics.md"), crew / "metrics.md")
    shutil.copytree(os.path.join(REPO, ".crew", "codemap"), crew / "codemap")
    (crew / "pm-journal.md").write_text("## 2026-09-23T01:00:00Z\nnote\n", encoding="utf-8")
    tickets = root / ".work" / "tickets"
    tickets.mkdir(parents=True)
    (tickets / "T-0001.md").write_text(TICKET, encoding="utf-8")
    (tickets / "notes.txt").write_text("not a ticket\n", encoding="utf-8")
    cache = root / ".work" / "cache"
    cache.mkdir()
    (cache / "ABC-12.md").write_text("# ABC-12 jira ticket\n", encoding="utf-8")
    (cache / "SDP-4410.md").write_text("# SDP-4410 desk ticket\n", encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text(
        "T-0001 | open | low | repo | Fix the thing\n", encoding="utf-8")
    return str(root)


def _load(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def test_preview_writes_nothing(repo, capsys):
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo])

    assert code == 0
    assert _snapshot(repo, skip_backups=False) == before
    assert "write  .crew/crew.json" in capsys.readouterr().out


def test_real_config_round_trips_through_crew_json(repo):
    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    original = json.loads(_load(repo, ".crew/config.json"))

    assert crew["schema"] == 1
    assert crew_migrate.to_legacy(crew) == original


def test_real_roles_map_onto_the_four_agent_roster(repo):
    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))

    assert crew["agents"] == ["explorer", "reviewer", "security", "researcher"]


def test_apply_leaves_codemap_config_and_journal_bytes_unchanged(repo):
    before = _snapshot(repo)
    kept = {k: v for k, v in _bytes_only(before).items()
            if k.startswith(".crew/codemap/") or k in (".crew/config.json", ".crew/metrics.md",
                                                        ".crew/pm-journal.md", ".work/tickets/T-0001.md")}

    crew_migrate.main(["--root", repo, "--apply"])

    after = _bytes_only(_snapshot(repo))
    assert {k: after.get(k) for k in kept} == kept


def test_apply_writes_metrics_jsonl_one_object_per_row_with_unknowns(repo):
    crew_migrate.main(["--root", repo, "--apply"])

    rows = [json.loads(line) for line in _load(repo, ".crew/metrics.jsonl").splitlines()]

    assert [(r["ticket"], r["block"], r["fix"], r["tokens"]) for r in rows[:2]] == [
        ("crew-0.20.15-pm-unnamed", 0, 8, "UNKNOWN"),
        ("crew-0.20.15-pm-unnamed", 1, 3, "UNKNOWN"),
    ] and len(rows) == 7


@pytest.mark.parametrize("line,field", [
    ("2026-09-23 | T-9 | codex | n/a | 2", "block"),
    ("2026-09-23 | T-9 | codex | 1", "fix"),
    ("| | codex | 1 | 2", "date"),
    ("2026-09-23 | T-9 | codex single round | 1 | 2", "reviewRound"),
])
def test_metrics_missing_or_unparseable_value_is_unknown(line, field):
    rows, _ = crew_migrate.metrics_rows(line)

    assert rows[0][field] == "UNKNOWN"


def test_metrics_header_and_separator_are_skipped_and_counted():
    text = "date | ticket | reviewer | BLOCK | FIX\n--- | --- | --- | --- | ---\n# prose\n"

    rows, skipped = crew_migrate.metrics_rows(text)

    assert (rows, skipped) == ([], 3)


def test_apply_imports_file_ticket_with_provenance(repo):
    crew_migrate.main(["--root", repo, "--apply"])

    prov = json.loads(_load(repo, ".work/tickets/T-0001/provenance.json"))

    assert (prov["source"], prov["sources"][0]["originalPath"], prov["indexLine"],
            _load(repo, ".work/tickets/T-0001/ticket.md")) == (
        "files", ".work/tickets/T-0001.md", "T-0001 | open | low | repo | Fix the thing", TICKET)


@pytest.mark.parametrize("ticket_id,source", [("ABC-12", "jira"), ("SDP-4410", "sdp")])
def test_apply_imports_tracker_caches_with_their_source(repo, ticket_id, source):
    crew_migrate.main(["--root", repo, "--apply"])

    prov = json.loads(_load(repo, f".work/tickets/{ticket_id}/provenance.json"))

    assert (prov["id"], prov["source"]) == (ticket_id, source)


def test_obsidian_cache_differing_from_file_ticket_keeps_both(repo):
    cfg = json.loads(_load(repo, ".crew/config.json"))
    cfg["tracker"] = "obsidian"
    with open(os.path.join(repo, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg))
    with open(os.path.join(repo, ".work", "cache", "T-0001.md"), "w", encoding="utf-8") as fh:
        fh.write("# T-0001 board copy\n")

    crew_migrate.main(["--root", repo, "--apply"])

    assert _load(repo, ".work/tickets/T-0001/ticket.obsidian.md") == "# T-0001 board copy\n"


def test_non_ticket_file_is_reported_not_silently_ignored(repo, capsys):
    crew_migrate.main(["--root", repo])

    assert "skip   .work/tickets/notes.txt" in capsys.readouterr().out


def test_apply_archives_journal_as_a_copy_and_reports_it_retireable(repo, capsys):
    crew_migrate.main(["--root", repo, "--apply"])

    out = capsys.readouterr().out
    assert (_load(repo, ".crew/archive/pm-journal.md") == _load(repo, ".crew/pm-journal.md")
            and "retireable  .crew/pm-journal.md" in out)


def test_rollback_restores_tree_byte_identical(repo, capsys):
    before = _bytes_only(_snapshot(repo))
    crew_migrate.main(["--root", repo, "--apply"])
    backup = re.search(r"--rollback (\S+)\)", capsys.readouterr().out).group(1)

    code = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(repo))) == (0, before)


def test_rollback_refuses_when_a_created_file_was_edited(repo, capsys):
    crew_migrate.main(["--root", repo, "--apply"])
    backup = re.search(r"--rollback (\S+)\)", capsys.readouterr().out).group(1)
    with open(os.path.join(repo, ".crew", "crew.json"), "a", encoding="utf-8") as fh:
        fh.write(" ")

    code = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (code, os.path.exists(os.path.join(repo, ".crew", "metrics.jsonl"))) == (1, True)


@pytest.mark.parametrize("fail_at", [1, 3, "last"])
def test_crash_mid_apply_leaves_the_old_tree(repo, monkeypatch, fail_at):
    before = _bytes_only(_snapshot(repo))
    total = len(crew_migrate.build_plan(repo)["writes"])
    stop = total if fail_at == "last" else fail_at
    real = os.replace
    backups = os.path.join(repo, ".crew", "backups") + os.sep
    calls = {"target": 0, "crashed_on": None}

    def flaky(src, dst):
        if src.endswith(crew_migrate.TMP_SUFFIX) and not dst.startswith(backups):
            calls["target"] += 1
            if calls["target"] == stop:
                calls["crashed_on"] = os.path.relpath(dst, repo).replace(os.sep, "/")
                raise OSError("injected crash")
        return real(src, dst)
    monkeypatch.setattr(crew_migrate.os, "replace", flaky)
    plan = crew_migrate.build_plan(repo)

    with pytest.raises(OSError, match="injected crash"):
        crew_migrate.apply_plan(plan)

    assert (calls["crashed_on"], _bytes_only(_snapshot(repo))) == (
        plan["writes"][stop - 1]["path"], before)


def test_hard_kill_mid_apply_is_reported_then_rolled_back(repo, capsys):
    before = _bytes_only(_snapshot(repo))
    crew_migrate.main(["--root", repo, "--apply"])
    backup = re.search(r"--rollback (\S+)\)", capsys.readouterr().out).group(1)
    manifest_path = os.path.join(repo, backup, "manifest.json")
    manifest = json.loads(_load(repo, manifest_path))
    manifest["state"] = "committing"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest))
    last = os.path.join(repo, manifest["targets"][-1]["path"])
    os.replace(last, last + crew_migrate.TMP_SUFFIX)

    refused = crew_migrate.main(["--root", repo, "--apply"])
    rolled = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (refused, rolled, _bytes_only(_snapshot(repo))) == (1, 0, before)


def test_unknown_config_keys_are_preserved_and_reported(repo, capsys):
    cfg = json.loads(_load(repo, ".crew/config.json"))
    cfg["futureKey"] = {"nested": [1, 2]}
    cfg["qa"]["newLeaf"] = "kept"
    with open(os.path.join(repo, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg))

    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    assert (crew["unmapped"], crew["review"]["newLeaf"], crew_migrate.to_legacy(crew) == cfg,
            "unmapped  config key 'futureKey'" in capsys.readouterr().out) == (
        {"futureKey": {"nested": [1, 2]}}, "kept", True, True)


@pytest.mark.parametrize("schema", [8, "7", None, True])
def test_unknown_schema_is_refused_and_nothing_written(repo, schema):
    cfg = json.loads(_load(repo, ".crew/config.json"))
    cfg["schema"] = schema
    with open(os.path.join(repo, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg))
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False)) == (1, before)


def test_existing_different_target_is_a_conflict_and_apply_writes_nothing(repo):
    with open(os.path.join(repo, ".crew", "crew.json"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False)) == (1, before)


def test_second_apply_is_a_no_op(repo, capsys):
    crew_migrate.main(["--root", repo, "--apply"])
    capsys.readouterr()
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, "nothing to write" in capsys.readouterr().out,
            _snapshot(repo, skip_backups=False)) == (0, True, before)


def test_mapping_table_in_docstring_matches_code():
    rows = re.findall(r"^\| `(\w+)`\s+\| `([\w.]+)`", crew_migrate.__doc__, re.M)

    assert tuple(rows) == crew_migrate.MAPPING


def test_symlinked_ticket_dir_is_a_conflict_and_nothing_is_written_through_it(repo, tmp_path):
    """Codex BLOCK: T-0002.md plus `.work/tickets/T-0002` symlinked to a
    directory outside the repo -- apply wrote ticket.md there."""
    outside = tmp_path / "outside"
    outside.mkdir()
    tickets = os.path.join(repo, ".work", "tickets")
    with open(os.path.join(tickets, "T-0002.md"), "w", encoding="utf-8") as fh:
        fh.write(TICKET)
    os.symlink(str(outside), os.path.join(tickets, "T-0002"), target_is_directory=True)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, os.listdir(outside)) == (1, [])


def test_existing_staging_name_is_a_conflict_and_is_left_intact(repo):
    """Codex BLOCK: a sibling `.crew/crew.json.crew-migrate.tmp` was
    truncated by staging and then deleted by the cleanup."""
    sentinel = os.path.join(repo, ".crew", "crew.json" + crew_migrate.TMP_SUFFIX)
    with open(sentinel, "wb") as fh:
        fh.write(b"sentinel bytes\n")
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False)) == (1, before)


def test_staging_name_created_after_the_plan_is_never_truncated(repo):
    plan = crew_migrate.build_plan(repo)
    before = _bytes_only(_snapshot(repo))
    sentinel = os.path.join(repo, ".crew", "crew.json" + crew_migrate.TMP_SUFFIX)
    with open(sentinel, "wb") as fh:
        fh.write(b"sentinel bytes\n")

    with pytest.raises(crew_migrate.MigrateError, match="appeared since the plan"):
        crew_migrate.apply_plan(plan)

    assert _bytes_only(_snapshot(repo)) == dict(
        before, **{".crew/crew.json" + crew_migrate.TMP_SUFFIX:
                   hashlib.sha256(b"sentinel bytes\n").hexdigest()})


def test_target_created_after_the_plan_is_not_overwritten_and_apply_is_undone(repo):
    """Codex BLOCK: build_plan, then a different .crew/crew.json appears,
    then apply_plan -- the new file was overwritten."""
    plan = crew_migrate.build_plan(repo)
    before = _bytes_only(_snapshot(repo))
    with open(os.path.join(repo, ".crew", "crew.json"), "wb") as fh:
        fh.write(b"{\"mine\": true}\n")

    with pytest.raises(crew_migrate.MigrateError, match="changed since the plan"):
        crew_migrate.apply_plan(plan)

    assert _bytes_only(_snapshot(repo)) == dict(
        before, **{".crew/crew.json": hashlib.sha256(b"{\"mine\": true}\n").hexdigest()})


def _applied_backup(repo, capsys):
    crew_migrate.main(["--root", repo, "--apply"])
    return re.search(r"--rollback (\S+)\)", capsys.readouterr().out).group(1)


def _rewrite_manifest(repo, backup, edit):
    path = os.path.join(repo, backup, "manifest.json")
    manifest = json.loads(_load(repo, path))
    edit(manifest)
    text = json.dumps(manifest)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_rollback_refuses_a_manifest_path_outside_the_repo(repo, tmp_path, capsys):
    """Codex BLOCK: a manifest naming ../victim with the victim's sha256 made
    --rollback delete it."""
    victim = tmp_path / "victim"
    victim.write_bytes(b"not yours\n")
    backup = _applied_backup(repo, capsys)
    _rewrite_manifest(repo, backup, lambda m: m["targets"].extend([
        {"path": "../victim", "existed": False,
         "sha256": hashlib.sha256(b"not yours\n").hexdigest()}]))
    applied = _bytes_only(_snapshot(repo))

    code = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (code, victim.exists(), _bytes_only(_snapshot(repo))) == (1, True, applied)


def test_rollback_refuses_to_remove_through_a_symlinked_dir(repo, tmp_path, capsys):
    backup = _applied_backup(repo, capsys)
    ticket_dir = os.path.join(repo, ".work", "tickets", "T-0001")
    outside = tmp_path / "outside"
    shutil.move(ticket_dir, str(outside))
    os.symlink(str(outside), ticket_dir, target_is_directory=True)

    code = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (code, sorted(os.listdir(outside))) == (1, ["provenance.json", "ticket.md"])


def test_autonomous_pm_authority_is_noted_in_report_and_crew_json(repo, capsys):
    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    out = capsys.readouterr().out
    assert (crew["notes"], "note   pm.authority: autonomous - /crew:autopilot drives one ticket" in out,
            crew["retired"]["pm"]["authority"]) == (
        [crew_migrate.AUTOPILOT_NOTE], True, "autonomous")


@pytest.mark.parametrize("pm", [{"authority": "act"}, {"authority": "report-only"}, {}, None])
def test_non_autonomous_pm_authority_adds_no_note(repo, pm, capsys):
    cfg = json.loads(_load(repo, ".crew/config.json"))
    if pm is None:
        cfg.pop("pm")
    else:
        cfg["pm"] = pm
    with open(os.path.join(repo, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cfg))

    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    assert ("notes" in crew, "autopilot" in capsys.readouterr().out) == (False, False)


def test_autopilot_note_survives_preview_and_round_trip(repo, capsys):
    original = json.loads(_load(repo, ".crew/config.json"))

    code = crew_migrate.main(["--root", repo, "--preview"])

    crew, _unmapped = crew_migrate.to_crew(original)
    assert (code, "set autopilot.mode: plan to enable" in capsys.readouterr().out,
            crew_migrate.to_legacy(crew) == original) == (0, True, True)


def test_autopilot_note_names_the_shipped_command_not_a_future_release():
    """T-0004 shipped `/crew:autopilot`; the note must stop promising 1.1.0."""
    note = crew_migrate.AUTOPILOT_NOTE

    assert ("arrives in 1.1.0" in note, "/crew:autopilot" in note,
            "autopilot.mode: plan" in note) == (False, True, True)


AUTOPILOT = {"mode": "off", "maxPhases": 12, "deploy": "none"}


def _write_config(root, cfg):
    text = json.dumps(cfg)
    with open(os.path.join(root, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(text)


def _with_autopilot(root, value=None, **extra):
    """The fixture config with `autopilot` (and `extra` keys) added; the PM
    block is made non-autonomous so the PM note does not appear."""
    cfg = json.loads(_load(root, ".crew/config.json"))
    cfg["pm"] = {"authority": "act"}
    cfg["autopilot"] = dict(AUTOPILOT) if value is None else value
    cfg.update(extra)
    _write_config(root, cfg)
    return cfg


def test_autopilot_key_lands_at_top_level_not_unmapped(repo, capsys):
    _with_autopilot(repo)

    code = crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    assert (code, crew.get("autopilot"), "unmapped" in crew,
            "unmapped  config key 'autopilot'" in capsys.readouterr().out) == (
        0, AUTOPILOT, False, False)


def test_autopilot_key_note_names_config_json(repo, capsys):
    _with_autopilot(repo)
    before = _snapshot(repo, skip_backups=False)

    preview_code = crew_migrate.main(["--root", repo, "--preview"])
    preview = capsys.readouterr().out
    unchanged = _snapshot(repo, skip_backups=False) == before
    crew_migrate.main(["--root", repo, "--apply"])
    applied = capsys.readouterr().out

    crew = json.loads(_load(repo, ".crew/crew.json"))
    line = f"note   {crew_migrate.AUTOPILOT_FILE_NOTE}"
    note = crew_migrate.AUTOPILOT_FILE_NOTE
    assert (preview_code, unchanged, preview.count(line), applied.count(line), crew["notes"],
            "autopilot" in note, ".crew/config.json" in note, "never read" in note) == (
        0, True, 1, 1, [note], True, True, True)


@pytest.mark.parametrize("value", [{"mode": "plan"}, {}, "plan", None, 12])
def test_autopilot_key_round_trips_whatever_its_value(value):
    cfg = {"schema": 7, "tracker": "files", "autopilot": value}

    crew, unmapped = crew_migrate.to_crew(cfg)

    assert (crew_migrate.to_legacy(crew) == cfg, unmapped, crew["notes"]) == (
        True, [], [crew_migrate.AUTOPILOT_FILE_NOTE])


def test_autonomous_pm_and_autopilot_key_give_both_notes_in_order():
    cfg = {"schema": 7, "pm": {"authority": "autonomous"}, "autopilot": dict(AUTOPILOT)}

    crew, _unmapped = crew_migrate.to_crew(cfg)

    assert crew["notes"] == [crew_migrate.AUTOPILOT_NOTE, crew_migrate.AUTOPILOT_FILE_NOTE]


def test_unknown_key_beside_autopilot_is_still_unmapped(repo, capsys):
    cfg = _with_autopilot(repo, futureKey={"nested": [1]})

    crew_migrate.main(["--root", repo, "--apply"])

    crew = json.loads(_load(repo, ".crew/crew.json"))
    out = capsys.readouterr().out
    assert (crew["unmapped"], crew["autopilot"], crew_migrate.to_legacy(crew) == cfg,
            "unmapped  config key 'futureKey'" in out,
            "unmapped  config key 'autopilot'" in out) == (
        {"futureKey": {"nested": [1]}}, AUTOPILOT, True, True, False)


def test_migrated_autopilot_is_reported_by_settings_once_config_json_is_gone(repo):
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    _with_autopilot(repo)
    crew_migrate.main(["--root", repo, "--apply"])
    kept = crew_autopilot.settings(repo)["warnings"]
    os.remove(os.path.join(repo, ".crew", "config.json"))

    gone = crew_autopilot.settings(repo)["warnings"]

    def named(warnings):
        return [w for w in warnings if ".crew/crew.json" in w]

    assert (named(kept), len(named(gone))) == ([], 1)


def test_crew_json_from_an_older_mapping_is_a_conflict_and_is_left_intact(repo):
    cfg = _with_autopilot(repo)
    old, _unmapped = crew_migrate.to_crew(cfg)
    old["unmapped"] = {"autopilot": old.pop("autopilot")}
    old.pop("notes")
    text = json.dumps(old, indent=2) + "\n"
    with open(os.path.join(repo, ".crew", "crew.json"), "w", encoding="utf-8") as fh:
        fh.write(text)
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False)) == (1, before)


def test_autopilot_note_names_both_files_and_the_stricter_rule():
    """Since T-0050 the personal autopilot keys are read from the machine-global
    file too, so a note naming only `.crew/config.json` would mislead."""
    note = crew_migrate.AUTOPILOT_FILE_NOTE

    assert ("never read" in note, ".crew/config.json" in note,
            "~/.claude/crew/config.json" in note, "stricter" in note, "20a" in note) == (
        True, True, True, True, True)


# --- ids beyond T- and the Complete/ archive (L-0509) ----------------------------

@pytest.mark.parametrize("ticket_id,tracker,indexed,source", [
    ("L-0509", "obsidian", False, "obsidian"),
    ("W-0001", "obsidian", False, "obsidian"),
    ("L-0509", "files", True, "files-cache"),
    ("T-0001", "files", False, "files-cache"),
    ("SDP-12", "sdp", False, "sdp"),
    ("SDP-12", "files", False, "sdp"),
    ("PROJ-7", "jira", False, "jira"),
    ("L-0509", "jira", True, "jira"),
    ("ABC-12", "files", False, "jira"),
])
def test_cache_source_follows_the_tracker(ticket_id, tracker, indexed, source):
    index = {ticket_id} if indexed else set()

    assert crew_migrate._cache_source(ticket_id, tracker, index) == source  # pylint: disable=protected-access


def test_an_l_prefixed_cache_file_this_box_minted_is_not_labelled_jira(repo):
    with open(os.path.join(repo, ".work", "cache", "L-0509.md"), "w", encoding="utf-8") as fh:
        fh.write("# L-0509 cached\n")
    with open(os.path.join(repo, ".work", "INDEX.md"), "a", encoding="utf-8") as fh:
        fh.write("L-0509 | open | low | repo | Archive\n")

    crew_migrate.main(["--root", repo, "--apply"])

    assert json.loads(_load(repo, ".work/tickets/L-0509/provenance.json"))["source"] == "files-cache"


def test_migrate_skips_an_archived_target(repo, capsys):
    os.makedirs(os.path.join(repo, ".work", "tickets", "Complete", "T-0001"))

    code = crew_migrate.main(["--root", repo, "--apply"])

    out = capsys.readouterr().out
    assert code == 0
    assert "skip   .work/tickets/T-0001.md: archived in Complete/; not migrated" in out
    assert not os.path.exists(os.path.join(repo, ".work", "tickets", "T-0001"))


def test_migrate_apply_refuses_a_could_not_tell_target(repo):
    os.makedirs(os.path.join(repo, ".work", "tickets", "Complete", "T-0001"))
    os.makedirs(os.path.join(repo, ".work", "tickets", "T-0001"))
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False)) == (1, before)


# ------------------------------------------------- T-0038: the pre-0.20 upgrade stage
#
# A config with no `schema` key, or an integer 1-6, is brought to the current
# schema by `crew_upgrade.upgrade_config` in the same apply. `.crew/config.json`
# is the one file migrate overwrites, so each test below is about getting the
# user's original bytes back: the in-process undo and `--rollback` restore it,
# never remove it.

V1_CONFIG = {"tier": 0, "tracker": "files"}
CREW_MIGRATE = os.path.join(os.path.dirname(HERE), "hooks", "scripts", "crew_migrate.py")
ABSENT = "absent"


def _write_config(repo, cfg):
    text = json.dumps(cfg, indent=2) + "\n"
    with open(os.path.join(repo, ".crew", "config.json"), "w", encoding="utf-8") as fh:
        fh.write(text)


def _pre_0_20(cfg_schema):
    cfg = dict(V1_CONFIG)
    if cfg_schema != ABSENT:
        cfg["schema"] = cfg_schema
    return cfg


@pytest.fixture(name="v1_repo")
def _v1_repo(repo):
    _write_config(repo, V1_CONFIG)
    return repo


def _crew_upgrade():
    import crew_upgrade  # pylint: disable=import-outside-toplevel
    return crew_upgrade


@pytest.mark.parametrize("cfg_schema", [ABSENT, 3])
def test_pre_0_20_preview_shows_both_stages_and_writes_nothing(repo, capsys, cfg_schema):
    _write_config(repo, _pre_0_20(cfg_schema))
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo])

    out = capsys.readouterr().out
    assert (code, _snapshot(repo, skip_backups=False), "upgrade  .crew/config.json" in out,
            "upgrade  ## Config" in out, "write  .crew/crew.json" in out) == (
        0, before, True, True, True)


def test_schema_7_config_is_never_rewritten(repo):
    path = os.path.join(repo, ".crew", "config.json")
    before = _snapshot(repo)[".crew/config.json"]

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo)[".crew/config.json"], os.path.exists(path)) == (0, before, True)


def test_unmigrated_block_is_a_conflict_and_nothing_is_written(repo, capsys):
    _write_config(repo, {"qa": "oops"})
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    said = capsys.readouterr()
    assert (code, _snapshot(repo, skip_backups=False),
            "CONFLICT  .crew/config.json: the pre-0.20 upgrade left these blocks unmigrated"
            in said.out + said.err, "qa" in said.out + said.err) == (1, before, True, True)


@pytest.mark.parametrize("cfg_schema", [0, -1])
def test_schema_zero_or_negative_is_refused(repo, capsys, cfg_schema):
    _write_config(repo, _pre_0_20(cfg_schema))
    before = _snapshot(repo, skip_backups=False)

    code = crew_migrate.main(["--root", repo, "--apply"])

    assert (code, _snapshot(repo, skip_backups=False),
            "is not a schema crew ever wrote" in capsys.readouterr().err) == (1, before, True)


@pytest.mark.parametrize("cfg_schema", [ABSENT, 3])
def test_pre_0_20_config_upgrades_then_migrates_in_one_apply(repo, cfg_schema):
    original = _pre_0_20(cfg_schema)
    _write_config(repo, original)

    code = crew_migrate.main(["--root", repo, "--apply"])

    upgraded = json.loads(_load(repo, ".crew/config.json"))
    crew = json.loads(_load(repo, ".crew/crew.json"))
    named = f"upgraded from schema {cfg_schema} to 7"
    assert (code, upgraded, upgraded["schema"], crew["migratedFrom"]["schema"],
            crew_migrate.to_legacy(crew) == upgraded,
            any(named in note for note in crew.get("notes", []))) == (
        0, _crew_upgrade().upgrade_config(copy.deepcopy(original))[0], 7, 7, True, True)


def test_pre_0_20_second_apply_is_a_no_op(v1_repo, capsys):
    crew_migrate.main(["--root", v1_repo, "--apply"])
    capsys.readouterr()
    before = _snapshot(v1_repo, skip_backups=False)

    code = crew_migrate.main(["--root", v1_repo, "--apply"])

    out = capsys.readouterr().out
    assert (code, "nothing to write" in out, "CONFLICT" in out,
            _snapshot(v1_repo, skip_backups=False)) == (0, True, False, before)


@pytest.mark.parametrize("notes", [5, "x", {"a": 1}])
def test_existing_crew_json_with_malformed_notes_is_a_conflict_not_a_crash(v1_repo, capsys, notes):
    """Review: a non-list `notes` in an existing crew.json is a different
    target (a conflict found in preview), never an uncaught TypeError."""
    with open(os.path.join(v1_repo, ".crew", "crew.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"schema": 1, "notes": notes}) + "\n")
    before = _snapshot(v1_repo, skip_backups=False)

    code = crew_migrate.main(["--root", v1_repo, "--preview"])

    assert (code, "CONFLICT" in capsys.readouterr().out, _snapshot(v1_repo, skip_backups=False)) == (
        1, True, before)


def test_upgraded_config_bytes_match_crew_upgrade_run(tmp_path):
    roots = []
    for name in ("via-migrate", "via-upgrade"):
        root = tmp_path / name / ".crew"
        root.mkdir(parents=True)
        (root / "config.json").write_text(json.dumps(V1_CONFIG) + "\n", encoding="utf-8")
        roots.append(str(tmp_path / name))

    code = crew_migrate.main(["--root", roots[0], "--apply"])
    result = _crew_upgrade().run(roots[1], {})

    assert (code, result["status"], _load(roots[0], ".crew/config.json").encode("utf-8")) == (
        0, "upgraded", _load(roots[1], ".crew/config.json").encode("utf-8"))


@pytest.mark.parametrize("fail_at", [1, 2, "last"])
def test_crash_mid_apply_on_a_pre_0_20_repo_restores_config_json(v1_repo, monkeypatch, fail_at):
    before = _bytes_only(_snapshot(v1_repo))
    plan = crew_migrate.build_plan(v1_repo)
    stop = len(plan["writes"]) if fail_at == "last" else fail_at
    real = os.replace
    backups = os.path.join(v1_repo, ".crew", "backups") + os.sep
    calls = {"target": 0}

    def flaky(src, dst):
        if not dst.startswith(backups) and src.endswith(crew_migrate.TMP_SUFFIX):
            calls["target"] += 1
            if calls["target"] == stop:
                raise OSError("injected crash")
        return real(src, dst)
    monkeypatch.setattr(crew_migrate.os, "replace", flaky)

    with pytest.raises(OSError, match="injected crash"):
        crew_migrate.apply_plan(plan)

    assert (plan["writes"][0]["path"], _bytes_only(_snapshot(v1_repo)),
            os.path.isfile(os.path.join(v1_repo, ".crew", "config.json"))) == (
        ".crew/config.json", before, True)


@pytest.mark.parametrize("edited", [".crew/config.json", "created"])
def test_crash_mid_apply_leaves_a_file_edited_since_it_landed(v1_repo, monkeypatch, capsys, edited):
    """Group review (g1-ports): the in-process undo checks, as --rollback
    does, that a landed file still holds what apply wrote; one edited in
    between is left as it is and named, never overwritten or removed."""
    plan = crew_migrate.build_plan(v1_repo)
    target = plan["writes"][0]["path"] if edited != "created" else plan["writes"][1]["path"]
    full = os.path.join(v1_repo, *target.split("/"))
    real = os.replace
    backups = os.path.join(v1_repo, ".crew", "backups") + os.sep
    calls = {"target": 0}

    def flaky(src, dst):
        if not dst.startswith(backups) and src.endswith(crew_migrate.TMP_SUFFIX):
            calls["target"] += 1
            if calls["target"] == len(plan["writes"]):
                with open(full, "wb") as fh:
                    fh.write(b"edited by someone else\n")
                raise OSError("injected crash")
        return real(src, dst)
    monkeypatch.setattr(crew_migrate.os, "replace", flaky)

    with pytest.raises(OSError, match="injected crash"):
        crew_migrate.apply_plan(plan)

    with open(full, "rb") as fh:
        kept = fh.read()
    others = [w["path"] for w in plan["writes"][:-1] if w["path"] != target and not w.get("replaces")]
    assert (len(plan["writes"]) > 2, kept, target in capsys.readouterr().err,
            [p for p in others if os.path.exists(os.path.join(v1_repo, *p.split("/")))]) == (
        True, b"edited by someone else\n", True, [])


def _mode(repo, rel):
    return os.stat(os.path.join(repo, *rel.split("/"))).st_mode & 0o777


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
@pytest.mark.parametrize("undo", ["applied", "--rollback", "in-process"])
def test_a_private_config_json_keeps_its_mode(v1_repo, monkeypatch, capsys, undo):
    """Group review r3 (g1-ports): the upgraded config.json, and the original
    the undo writes back, keep their bits (0640: neither the umask default nor
    mkstemp's 0600); created files are never executable."""
    os.chmod(os.path.join(v1_repo, ".crew", "config.json"), 0o640)
    plan = crew_migrate.build_plan(v1_repo)
    created = [w["path"] for w in plan["writes"] if not w.get("replaces")]
    if undo == "in-process":
        real = os.replace
        backups = os.path.join(v1_repo, ".crew", "backups") + os.sep
        calls = {"target": 0}

        def flaky(src, dst):
            if not dst.startswith(backups) and src.endswith(crew_migrate.TMP_SUFFIX):
                calls["target"] += 1
                if calls["target"] == len(plan["writes"]):
                    raise OSError("injected crash")
            return real(src, dst)
        monkeypatch.setattr(crew_migrate.os, "replace", flaky)
        with pytest.raises(OSError, match="injected crash"):
            crew_migrate.apply_plan(plan)
        modes = []
    else:
        backup = _applied_backup(v1_repo, capsys)
        modes = sorted({_mode(v1_repo, rel) & 0o111 for rel in created})
        if undo == "--rollback":
            assert crew_migrate.main(["--root", v1_repo, "--rollback", backup]) == 0

    assert (_mode(v1_repo, ".crew/config.json"), modes) == (0o640, [] if undo == "in-process" else [0])


def test_pre_0_20_rollback_restores_config_json_byte_identical(v1_repo, capsys):
    before = _bytes_only(_snapshot(v1_repo))
    backup = _applied_backup(v1_repo, capsys)

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(v1_repo)),
            "restored  .crew/config.json" in capsys.readouterr().out) == (0, before, True)


def test_hard_kill_before_config_replace_rolls_back_without_touching_it(v1_repo, capsys):
    original = _snapshot(v1_repo)[".crew/config.json"][0]
    with open(os.path.join(v1_repo, ".crew", "config.json"), "rb") as fh:
        original_bytes = fh.read()
    backup = _applied_backup(v1_repo, capsys)
    _rewrite_manifest(v1_repo, backup, lambda m: m.update(state="committing"))
    crew_migrate.atomic_write(os.path.join(v1_repo, ".crew", "config.json"), original_bytes)
    stamp = _snapshot(v1_repo)[".crew/config.json"]

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, _snapshot(v1_repo)[".crew/config.json"], stamp[0]) == (0, stamp, original)


def test_rollback_refuses_when_config_json_was_edited_after_apply(v1_repo, capsys):
    backup = _applied_backup(v1_repo, capsys)
    with open(os.path.join(v1_repo, ".crew", "config.json"), "a", encoding="utf-8") as fh:
        fh.write(" ")
    applied = _bytes_only(_snapshot(v1_repo))

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, os.path.exists(os.path.join(v1_repo, ".crew", "crew.json")),
            _bytes_only(_snapshot(v1_repo))) == (1, True, applied)


def test_rollback_refuses_when_the_backed_up_original_does_not_match_the_manifest(
        v1_repo, capsys):
    backup = _applied_backup(v1_repo, capsys)
    with open(os.path.join(v1_repo, backup, "sources", ".crew", "config.json"), "ab") as fh:
        fh.write(b"{\"forged\": true}\n")
    applied = _bytes_only(_snapshot(v1_repo))

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(v1_repo))) == (1, applied)


def test_rollback_refuses_a_config_target_without_an_original_hash(v1_repo, capsys):
    backup = _applied_backup(v1_repo, capsys)
    _rewrite_manifest(v1_repo, backup, lambda m: [
        t.pop("originalSha256") for t in m["targets"] if t["path"] == ".crew/config.json"])
    applied = _bytes_only(_snapshot(v1_repo))

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(v1_repo))) == (1, applied)


def test_rollback_refuses_a_config_target_not_marked_existed(v1_repo, capsys):
    """A forged manifest marks config.json as a file apply created, so the
    remove path would delete the user's only config. Refused by name."""
    backup = _applied_backup(v1_repo, capsys)
    _rewrite_manifest(v1_repo, backup, lambda m: [
        t.update(existed=False) for t in m["targets"] if t["path"] == ".crew/config.json"])
    applied = _bytes_only(_snapshot(v1_repo))

    code = crew_migrate.main(["--root", v1_repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(v1_repo))) == (1, applied)


def test_rollback_refuses_a_created_target_marked_existed(repo, capsys):
    """The other half of the same rule: only config.json may be restored."""
    backup = _applied_backup(repo, capsys)
    _rewrite_manifest(repo, backup, lambda m: [
        t.update(existed=True, originalSha256=t["sha256"]) for t in m["targets"]
        if t["path"] == ".crew/crew.json"])
    applied = _bytes_only(_snapshot(repo))

    code = crew_migrate.main(["--root", repo, "--rollback", backup])

    assert (code, _bytes_only(_snapshot(repo))) == (1, applied)


def test_crew_migrate_cli_upgrades_a_pre_0_20_repo_from_a_clean_interpreter(v1_repo, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "PYTHONPATH": "", "HOME": str(home), "USERPROFILE": str(home)}

    done = subprocess.run([sys.executable, CREW_MIGRATE, "--root", v1_repo], env=env,
                          cwd=str(tmp_path), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)

    assert (done.returncode, "upgrade  .crew/config.json" in done.stdout, done.stderr) == (
        0, True, "")


def test_missing_crew_upgrade_is_refused_and_nothing_written(v1_repo, monkeypatch, capsys):
    before = _snapshot(v1_repo, skip_backups=False)
    real_loader = crew_migrate._upgrade_module  # pylint: disable=protected-access

    def refuse():
        raise crew_migrate.MigrateError("cannot load crew_upgrade from <test>: gone")
    monkeypatch.setattr(crew_migrate, "_upgrade_module", refuse)
    stubbed = crew_migrate.main(["--root", v1_repo, "--apply"])
    monkeypatch.setattr(crew_migrate, "_upgrade_module", real_loader)
    real_import = builtins.__import__

    def no_crew_upgrade(name, *args, **kwargs):
        if name == "crew_upgrade":
            raise ImportError("No module named 'crew_upgrade'")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_crew_upgrade)
    real = crew_migrate.main(["--root", v1_repo, "--apply"])
    monkeypatch.setattr(builtins, "__import__", real_import)

    err = capsys.readouterr().err
    assert (stubbed, real, _snapshot(v1_repo, skip_backups=False),
            err.count("cannot load crew_upgrade")) == (1, 1, before, 2)


def test_upgrade_stage_bound_is_crew_states_current_schema():
    """The stage runs below LEGACY_SCHEMA_MAX; that bound IS SCHEMA_CURRENT."""
    import crew_state  # pylint: disable=import-outside-toplevel

    assert crew_migrate.LEGACY_SCHEMA_MAX == crew_state.SCHEMA_CURRENT


def test_upgrade_command_is_a_removal_stub():
    path = os.path.join(os.path.dirname(HERE), "commands", "upgrade.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    description = re.search(r"^description: (.*)$", text, re.M).group(1)

    assert (len(text.splitlines()) <= 12, description.startswith("Removed"),
            "/crew:migrate" in text, "crew_upgrade.py" in text, "```" in text,
            re.search(r"^allowed-tools: Read$", text, re.M) is not None) == (
        True, True, True, False, False, True)
