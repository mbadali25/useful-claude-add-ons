"""`crew_migrate.py`: preview, apply, rollback, and the crash in between.

Every test runs against a copy under `tmp_path`. The config and metrics are
byte copies of THIS repository's machine-local `.crew/config.json` (schema 7,
53 roles) and `.crew/metrics.md` as they stood on 2026-09-23, kept in
`migrate_fixtures/` because both files are gitignored and a clone has neither.
The codemap is copied from the tracked `.crew/codemap/` at run time.
"""
import hashlib
import json
import os
import re
import shutil

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
    assert (crew["notes"], "note   pm.authority: autonomous - autopilot arrives in 1.1.0" in out,
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
    assert (code, "autopilot arrives in 1.1.0" in capsys.readouterr().out,
            crew_migrate.to_legacy(crew) == original) == (0, True, True)
