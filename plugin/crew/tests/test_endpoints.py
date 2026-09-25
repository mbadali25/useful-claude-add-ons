"""Tests for the endpoint ledger, gizmoduck detection, and endpointUnscanned.

Covers: the trigger firing when a ledger record has no scan artifact at its
computed path, not firing once a real (non-empty, endpoint-matching)
artifact exists, not firing when gizmoduck is absent (including the "this
repo develops gizmoduck" gotcha), the single-repo and mono-repo path rules,
a frozen artifact path surviving a later repo-shape flip, id safety (mint
and read time), gizmoduck_installed's scope precedence, and inferred hits
surfacing as EPHEMERAL candidates -- computed fresh on every read, never
persisted -- rather than declared facts.
"""
import contextlib
import errno
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_endpoints
# The endpoint ledger moved to `crew_endpoints` in 0.16.21. The patches below
# name that module rather than `crew_state`, and the distinction is not
# cosmetic: `read_endpoints` looks `gizmoduck_installed` up in ITS OWN module
# globals, so patching a re-exported copy on `crew_state` would rebind a name
# nothing reads -- every gizmoduck-installed test would then run against the
# real detector and pass for the wrong reason. `crew_state` deliberately does
# not re-export it.
import crew_state


def _write_ledger(root, records, next_seq=None):
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    doc = {"records": records}
    if next_seq is not None:
        doc["nextSeq"] = next_seq
    (root / ".crew" / "endpoints.json").write_text(
        json.dumps(doc), encoding="utf-8")


def _fake_home(monkeypatch, tmp_path, name="fakehome"):
    """Points os.path.expanduser("~") at an empty, private directory, so a
    test's result never depends on whatever is actually installed on the
    machine running the suite -- this repo's own ~/.claude/settings.json may
    well have gizmoduck enabled for real.
    """
    home = tmp_path / name
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(
        crew_state.os.path, "expanduser",
        lambda p: str(home) if p == "~" else os.path.expanduser(p),
    )
    return home


def _write_settings(dirpath, enabled_plugins, name="settings.json"):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(
        json.dumps({"enabledPlugins": enabled_plugins}), encoding="utf-8")


# -- gizmoduck_installed: precedence ------------------------------------------

def test_gizmoduck_not_installed_by_default(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    assert not crew_endpoints.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_global_settings(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude",
                    {"gizmoduck@useful-claude-add-ons": True})
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_endpoints.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_project_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@a-fork": True})
    assert crew_endpoints.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_project_local_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@a-fork": True},
                    name="settings.local.json")
    assert crew_endpoints.gizmoduck_installed(str(root))


def test_gizmoduck_disabled_value_does_not_count(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude",
                    {"gizmoduck@useful-claude-add-ons": False})
    root = crew_fixtures.make_repo(tmp_path)
    assert not crew_endpoints.gizmoduck_installed(str(root))


def test_project_explicit_false_wins_over_global_true(tmp_path, monkeypatch):
    """Finding 4: project scope must win over global, and an explicit
    `false` there must mean off -- not "keep looking until something says
    true"."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True})
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@m": False})
    assert not crew_endpoints.gizmoduck_installed(str(root))


def test_project_local_settings_outrank_project_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@m": True})
    _write_settings(root / ".claude", {"gizmoduck@m": False},
                    name="settings.local.json")
    assert not crew_endpoints.gizmoduck_installed(str(root))


def test_string_false_does_not_count_as_installed(tmp_path, monkeypatch):
    """`"false"` (a JSON string) is truthy in Python; `if value` would read
    it as installed. Only a real boolean may decide this."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": "false"})
    root = crew_fixtures.make_repo(tmp_path)
    assert not crew_endpoints.gizmoduck_installed(str(root))


def test_malformed_project_settings_defers_to_global(tmp_path, monkeypatch):
    """A project settings.json that fails to parse carries no signal
    either way -- it must not silently read as "off" while a wider scope
    has an explicit `true`."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True})
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    assert crew_endpoints.gizmoduck_installed(str(root))


def test_global_settings_local_json_is_consulted(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True},
                    name="settings.local.json")
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_endpoints.gizmoduck_installed(str(root))


def test_in_repo_source_directory_is_not_installation(tmp_path, monkeypatch):
    """The critical gotcha: this repo SHIPS plugin/gizmoduck/ as source. That
    directory existing under root must not satisfy the check -- only Claude
    Code's own enabledPlugins settings may.
    """
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "plugin" / "gizmoduck").mkdir(parents=True)
    (root / "plugin" / "gizmoduck" / "SKILL.md").write_text(
        "source, not installed", encoding="utf-8")
    assert not crew_endpoints.gizmoduck_installed(str(root))


# -- scan_artifact_path: single repo ------------------------------------------

def test_single_repo_path_rule(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "ep-0001", "location": "src/app.py:10"}
    got = crew_endpoints.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0001.md")


def test_scan_artifact_path_rejects_a_traversal_id(tmp_path):
    """Finding 3: a hand-edited id must never reach a path join at all."""
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "../../../unrelated", "location": "src/app.py:10"}
    assert crew_endpoints.scan_artifact_path(str(root), record) is None


# -- scan_artifact_path: mono-repo ---------------------------------------------

def test_monorepo_path_rule_attributes_to_owning_package(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n",
                                              encoding="utf-8")
    pkg_dir = root / "packages" / "api"
    (pkg_dir / "src").mkdir(parents=True)
    (pkg_dir / "package.json").write_text("{}", encoding="utf-8")
    (pkg_dir / "src" / "index.ts").write_text("// route lives here",
                                              encoding="utf-8")

    record = {"id": "ep-0002", "location": "packages/api/src/index.ts:5"}
    got = crew_endpoints.scan_artifact_path(str(root), record)
    assert got == os.path.join("packages", "api", "docs", "security-scans",
                               "ep-0002.md")


def test_monorepo_detected_by_multiple_go_modules(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "services" / "a").mkdir(parents=True)
    (root / "services" / "b").mkdir(parents=True)
    (root / "services" / "a" / "go.mod").write_text("module a\n",
                                                     encoding="utf-8")
    (root / "services" / "b" / "go.mod").write_text("module b\n",
                                                     encoding="utf-8")
    assert crew_endpoints._is_monorepo(str(root))  # pylint: disable=protected-access


def test_monorepo_falls_back_to_root_when_unattributable(tmp_path):
    """A record with no path to attribute -- a bare ticket reference -- is
    not exempt from scanning. It lands at the same root bucket a single repo
    would use everywhere, not nowhere.
    """
    root = crew_fixtures.make_repo(tmp_path)
    (root / "services" / "a").mkdir(parents=True)
    (root / "services" / "b").mkdir(parents=True)
    (root / "services" / "a" / "go.mod").write_text("module a\n",
                                                     encoding="utf-8")
    (root / "services" / "b" / "go.mod").write_text("module b\n",
                                                     encoding="utf-8")

    record = {"id": "ep-0003", "location": "JIRA-123"}
    got = crew_endpoints.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0003.md")


def test_single_go_mod_at_root_is_not_a_monorepo(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "go.mod").write_text("module solo\n", encoding="utf-8")
    assert not crew_endpoints._is_monorepo(str(root))  # pylint: disable=protected-access


def test_frozen_artifact_path_survives_a_later_monorepo_flip(tmp_path):
    """Finding 6: once a scan lands and its path is frozen onto the record,
    a repo-shape change afterwards (a second manifest appearing anywhere)
    must not relocate or orphan it. Only a record with no frozen path yet
    uses the freshly computed classifier.
    """
    root = crew_fixtures.make_repo(tmp_path)
    (root / "a").mkdir()
    record = {"id": "ep-0001", "location": "a/app.py:10"}
    single_repo_path = crew_endpoints.scan_artifact_path(str(root), record)
    assert single_repo_path == os.path.join("docs", "security-scans",
                                            "ep-0001.md")

    # A second manifest appears -- the repo is now a monorepo by the
    # documented signal (more than one go.mod/Cargo.toml/pyproject.toml) --
    # and the endpoint's own directory ("a/") is now an attributable package.
    (root / "b").mkdir()
    (root / "a" / "go.mod").write_text("module a\n", encoding="utf-8")
    (root / "b" / "go.mod").write_text("module b\n", encoding="utf-8")
    assert crew_endpoints._is_monorepo(str(root))  # pylint: disable=protected-access

    # A record with NO frozen path recomputes and moves -- that is the
    # documented, accepted behaviour for anything not yet scanned.
    moved = crew_endpoints.scan_artifact_path(str(root), record)
    assert moved != single_repo_path

    # But a record that already landed a scan keeps its own frozen path --
    # read back POSIX-normalised (finding 12), regardless of the separator
    # style the caller happened to freeze it with.
    frozen_record = dict(record, artifactPath=single_repo_path)
    assert (crew_endpoints.scan_artifact_path(str(root), frozen_record)
            == single_repo_path.replace(os.sep, "/"))


# -- read_endpoints / declared endpointUnscanned ------------------------------

def test_trigger_fires_when_artifact_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"]
    state = {"schema": crew_state.SCHEMA_CURRENT, "endpoints": endpoints}
    assert "endpointUnscanned" in crew_state.evaluate_triggers(state)


# The exact marker gizmoduck's report command always writes (BLOCK 4) --
# see `cmd_report` in `plugin/gizmoduck/scripts/gizmoduck.py`, documented as
# a contract in `plugin/gizmoduck/commands/report.md`.
_REAL_REPORT_MARKER = "**Total finding instances:** 0\n"


def test_trigger_does_not_fire_once_a_real_artifact_exists(tmp_path, monkeypatch):
    """A real scan artifact: non-empty, carrying the scan marker (finding
    2/BLOCK 4), AND mentioning the endpoint it covers (finding 2)."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    state = {"schema": crew_state.SCHEMA_CURRENT, "endpoints": endpoints}
    assert "endpointUnscanned" not in crew_state.evaluate_triggers(state)


def test_empty_artifact_does_not_discharge_the_obligation(tmp_path, monkeypatch):
    """Finding 2, half 1: `touch docs/security-scans/ep-0001.md` (0 bytes)
    must not permanently discharge the obligation."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.touch()

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_artifact_for_a_different_endpoint_does_not_confirm_this_one(
        tmp_path, monkeypatch):
    """Finding 2, half 1: non-empty is necessary but not sufficient -- the
    text must actually reference THIS endpoint."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/OTHER\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_todo_note_does_not_confirm_a_scan(tmp_path, monkeypatch):
    """BLOCK 4, reproduced: a to-do note that merely MENTIONS the URL is not
    evidence a scan actually ran. `echo "TODO: scan <url> later" > ...` used
    to discharge the obligation for free because the old check was a bare
    substring match with no proof a scan tool produced the file."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example.com/pay",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "TODO: scan https://api.example.com/pay later\n", encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_declared_bare_description_endpoint_fails_closed_with_no_needle(
        tmp_path, monkeypatch):
    """BLOCK 3, reproduced: a declared record whose endpoint text is a
    free-text description (the exact shape `work.md` used to invite) yields
    no matchable needle -- and must fail CLOSED, not be discharged by any
    non-empty (even marker-carrying) file at the computed path."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0002", "endpoint": "the payments admin console",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n\n" + _REAL_REPORT_MARKER,
                             encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_endpoint_needle_covers_a_bare_hostname(tmp_path, monkeypatch):
    """BLOCK 3: the docs also invite a bare host (`report.md`: "a host or
    URL"); the needle derivation must cover that shape, not just a full
    URL or an absolute path."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0003", "endpoint": "payments.internal.example.com",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned payments.internal.example.com\n" + _REAL_REPORT_MARKER,
        encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


def test_endpoint_needle_rejects_a_bare_slash(tmp_path):
    """Finding 4's related bug: `_endpoint_needle('/')` used to return '/',
    which matches almost any markdown file containing a slash anywhere --
    not a needle at all."""
    assert crew_endpoints._endpoint_needle("/") is None  # pylint: disable=protected-access


def test_empty_artifact_does_not_discharge_a_candidate_with_no_specific_target(
        tmp_path, monkeypatch):
    """Finding 2, half 1, for the case with no needle to check: an inferred
    candidate's label ("a Flask/FastAPI route decorator") has nothing
    specific to search for, so non-empty is ALL that can be required -- but
    it must still be required. An empty file must not pass just because
    there was nothing to cross-check."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "cand-aaaaaaaa", "endpoint": "a Flask/FastAPI route decorator",
        "source": "inferred", "status": "candidate",
        "location": "app.py:1",
    }
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.touch()
    assert not crew_endpoints._artifact_confirms_scan(str(root), artifact, record)  # pylint: disable=protected-access


def test_a_traversal_id_reads_as_unscanned_not_as_scanned(tmp_path, monkeypatch):
    """Finding 3: an unsafe id must fail safe -- reported as unscanned,
    never silently treated as scanned by probing a path outside the repo."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "../../../unrelated", "endpoint": "https://api.example/v1/x",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert len(endpoints["unscanned"]) == 1
    assert endpoints["unscanned"][0]["path"] is None


def test_trigger_does_not_fire_when_gizmoduck_absent(tmp_path, monkeypatch):
    """Strictly inert: no error, no finding, with the plugin uninstalled --
    even though the ledger names an endpoint with no scan at all.
    """
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints == {"installed": False, "unscanned": []}
    state = {"schema": crew_state.SCHEMA_CURRENT, "endpoints": endpoints}
    assert "endpointUnscanned" not in crew_state.evaluate_triggers(state)


def test_closed_records_never_count_as_unscanned(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "decommissioned",
        "source": "declared", "status": "closed",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


def test_unscanned_hit_carries_status_not_just_source(tmp_path, monkeypatch):
    """Finding 10: `status` -- not `source` -- is the authoritative field.
    A record whose fields disagree must still be checkable by `status`."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "candidate",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["status"] == "candidate"


# -- declared endpoints: declare_endpoint --------------------------------------

def test_declare_endpoint_writes_an_authoritative_open_record(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://api.example/v1/widgets", "src/app.py:10",
        ticket="T-0100")
    assert record["source"] == "declared"
    assert record["status"] == "open"
    stored = crew_endpoints.load_endpoints(str(root))
    assert stored == [record]


def test_declare_endpoint_cli_rejects_an_empty_value(tmp_path, capsys):
    """Nit 15: `--declare-endpoint ""` is falsy, so a bare truthiness check
    let it fall through to the unconditional full-state print and exit 0 --
    the same silent-ignore bug a missing --location already guards against."""
    root = crew_fixtures.make_repo(tmp_path)
    code = crew_state.main(["--root", str(root), "--declare-endpoint", "",
                            "--location", "a.py:1"])
    assert code != 0
    assert "declare-endpoint" in capsys.readouterr().err


def test_declare_endpoint_rejects_an_unsafe_endpoint_id(tmp_path):
    """Finding 3: sanitise at MINT time too -- reject rather than mangle."""
    root = crew_fixtures.make_repo(tmp_path)
    result = crew_endpoints.declare_endpoint(
        str(root), "https://api.example/v1/x", "src/app.py:10",
        endpoint_id="../../../unrelated")
    assert "error" in result
    assert crew_endpoints.load_endpoints(str(root)) == []


def test_declare_endpoint_ids_do_not_collide_after_a_deletion(tmp_path):
    """Finding 7: declare a, declare b, delete a (hand-edit the committed
    ledger), declare c -- c must not mint b's id."""
    root = crew_fixtures.make_repo(tmp_path)
    first = crew_endpoints.declare_endpoint(str(root), "https://a.example/x",
                                        "a.py:1")
    second = crew_endpoints.declare_endpoint(str(root), "https://b.example/x",
                                         "b.py:1")
    assert first["id"] != second["id"]

    # Hand-edit the ledger the way a committed, human-editable file would
    # be: delete the first record but leave the mint sequence untouched.
    doc = json.loads((root / ".crew" / "endpoints.json").read_text(
        encoding="utf-8"))
    doc["records"] = [r for r in doc["records"] if r["id"] != first["id"]]
    (root / ".crew" / "endpoints.json").write_text(
        json.dumps(doc), encoding="utf-8")

    third = crew_endpoints.declare_endpoint(str(root), "https://c.example/x",
                                        "c.py:1")
    assert third["id"] not in (first["id"], second["id"])


def test_declare_endpoint_is_atomic(tmp_path):
    """Finding 8: the write goes through a temp file plus os.replace, not
    write-in-place -- no lingering .tmp file after a normal write."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_endpoints.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    leftovers = [p for p in (root / ".crew").iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_endpoints_leaves_the_original_intact_if_replace_fails(
        tmp_path, monkeypatch):
    """Finding 8, the property write-then-rename actually buys: a write
    that fails partway through must never have touched the file readers
    still see. A write-in-place design would already have clobbered the
    original the moment `open(path, "w")` ran, before any failure could be
    detected -- this is what distinguishes atomic from merely "no leftover
    .tmp file", which a naive write-in-place also satisfies trivially."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_endpoints.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    original = (root / ".crew" / "endpoints.json").read_bytes()

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(crew_endpoints.os, "replace", boom)

    crew_endpoints.declare_endpoint(str(root), "https://b.example/x", "b.py:1")
    assert (root / ".crew" / "endpoints.json").read_bytes() == original


def test_ephemeral_candidate_ids_differ_by_location(tmp_path):
    """Finding 11's "dedup key ignoring location": two candidates sharing a
    signal but at different locations must never mint the same id -- that
    would make one scan artifact silently discharge both."""
    same_signal_a = {"signal": "python-route", "location": "a.py:1"}
    same_signal_b = {"signal": "python-route", "location": "b.py:1"}
    ids = {crew_endpoints._candidate_record(c)["id"]  # pylint: disable=protected-access
          for c in (same_signal_a, same_signal_b)}
    assert len(ids) == 2


def test_written_ledger_uses_lf_not_crlf(tmp_path):
    """Nit 12: the newline="\\n" the write comment argues for, actually
    checked against the bytes on disk."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_endpoints.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    raw = (root / ".crew" / "endpoints.json").read_bytes()
    assert b"\r\n" not in raw


def test_record_scan_artifact_freezes_the_path(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(str(root), "https://a.example/x",
                                         "a.py:1")
    path = crew_endpoints.record_scan_artifact(str(root), record["id"])
    # POSIX-normalised (finding 12); the freshly-computed default from
    # scan_artifact_path itself still uses native separators.
    assert path == crew_endpoints.scan_artifact_path(
        str(root), record).replace(os.sep, "/")
    stored = crew_endpoints.load_endpoints(str(root))[0]
    assert stored["artifactPath"] == path


def test_record_scan_artifact_is_none_for_an_unknown_id(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_endpoints.record_scan_artifact(str(root), "ep-9999") is None


# -- inferred candidates: computed, never persisted (BLOCK 1) -----------------

def test_infer_endpoints_flags_a_new_flask_route(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8",
    )
    # `git diff HEAD` only sees tracked paths -- an untracked file is
    # invisible to it until staged, same as an ordinary `git add` before a
    # commit.
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    hits = crew_endpoints.infer_endpoints(str(root))
    assert any(h["signal"] == "python-route" and h["location"].startswith("app.py")
               for h in hits)


def test_infer_endpoints_empty_with_no_diff(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_infer_endpoints_ignores_a_commented_out_example(tmp_path):
    """Finding 9: a comment describing the shape must not itself be read as
    the shape."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.js").write_text(
        '// see app.post("/foo") for the pattern\n', encoding="utf-8")
    crew_fixtures._git(root, "add", "app.js")  # pylint: disable=protected-access
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_infer_endpoints_ignores_a_match_inside_someone_elses_string(tmp_path):
    """Finding 9: a config value that merely CONTAINS the shape of a route
    registration, inside its own quotes, is not one."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.js").write_text(
        'const description = "app.get(\'/x\')";\n', encoding="utf-8")
    crew_fixtures._git(root, "add", "app.js")  # pylint: disable=protected-access
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_infer_endpoints_ignores_its_own_signal_comment_in_crew_source(tmp_path):
    """Finding 9's reproduced case: crew_state.py's own comment describing
    the http-route signal must not fire the signal. (Caught here by two
    overlapping defences -- the comment-prefix skip and the self-exclusion
    -- see the next test for one that isolates just the second.)"""
    root = crew_fixtures.make_repo(tmp_path)
    scripts_dir = root / "plugin" / "crew" / "hooks" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "crew_state.py").write_text(
        '# Express/Fastify/Koa-style route registration: app.get("/x", ...)\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add",
                       "plugin/crew/hooks/scripts/crew_state.py")
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_infer_endpoints_excludes_crews_own_source_even_without_a_comment(
        tmp_path):
    """Isolates _excluded_from_inference from the comment-prefix skip: a
    REAL (non-comment, non-string) route registration under crew's own
    hooks/scripts directory must still be excluded -- any file there, not
    only crew_state.py by name."""
    root = crew_fixtures.make_repo(tmp_path)
    scripts_dir = root / "plugin" / "crew" / "hooks" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "other.py").write_text(
        '@app.route("/real-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "plugin/crew/hooks/scripts/other.py")
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_infer_endpoints_gates_openapi_path_to_spec_files(tmp_path):
    """Finding 9: an indented slash-path YAML/JSON key that is not itself
    in a spec-shaped file (a shell PATH listing in a .sh script, say) must
    not be read as an OpenAPI path entry."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "setup.sh").write_text("  /usr/local/bin:\n", encoding="utf-8")
    crew_fixtures._git(root, "add", "setup.sh")  # pylint: disable=protected-access
    assert crew_endpoints.infer_endpoints(str(root)) == []


def test_read_endpoints_surfaces_an_inferred_hit_as_an_ephemeral_candidate(
        tmp_path, monkeypatch):
    """BLOCK 1: candidates are computed inside the read path, never
    persisted. A fresh inferred hit with no matching declared record must
    surface in `unscanned` as a candidate, and the ledger file on disk must
    still hold nothing."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    hits = [h for h in endpoints["unscanned"] if h["source"] == "inferred"]
    assert len(hits) == 1
    assert hits[0]["status"] == "candidate"
    # Never written -- load_endpoints (the ledger on disk) stays empty.
    assert crew_endpoints.load_endpoints(str(root)) == []


def test_ephemeral_candidate_id_is_stable_across_reads(tmp_path, monkeypatch):
    """The same diff line must resolve to the same artifact path on every
    read, even though nothing about it is ever saved -- a scan written for
    it today has to be found tomorrow."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access

    first = crew_endpoints.read_endpoints(str(root), {})
    second = crew_endpoints.read_endpoints(str(root), {})
    first_ids = sorted(h["id"] for h in first["unscanned"])
    second_ids = sorted(h["id"] for h in second["unscanned"])
    assert first_ids == second_ids


def test_a_promoted_location_no_longer_surfaces_as_a_fresh_candidate(
        tmp_path, monkeypatch):
    """Once a location is covered by a persisted (declared) record, the same
    diff line must not ALSO surface as an inferred candidate under a
    different id."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    inferred = crew_endpoints.infer_endpoints(str(root))
    assert inferred
    location = inferred[0]["location"]

    crew_endpoints.declare_endpoint(str(root), "https://example.com/new-thing",
                               location)
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    sources = [h["source"] for h in endpoints["unscanned"]
              if h.get("path") is not None
              or h.get("source") == "inferred"]
    # Only the declared hit should reference this location; no duplicate
    # inferred hit for the same line.
    assert sources.count("inferred") == 0


# --- candidate id determinism -------------------------------------------
#
# `_candidate_record` mints its id as a sha1 of (signal, location) rather
# than from a counter, and its docstring states why: inferred candidates are
# never persisted, so there is no shared sequence to draw from, and hashing
# the pair is what lets the SAME diff line resolve to the SAME artifact path
# across repeated reads of an UNCHANGED diff -- a scan written for it today
# has to be found tomorrow. It does NOT survive a line shift: `location`
# carries a line number, so one line inserted above re-ids the candidate and
# orphans a scan already written for the old one (finding 6) -- that is a
# real, undefended gap, not something this file's tests claim to close.
#
# What IS the whole contract of an ephemeral candidate, and what this file
# exercises: a counter, a dict ordering, or a stray timestamp creeping into
# the hash input would break stability across an otherwise-unchanged diff in
# the one way that leaves no symptom: yesterday's scan simply stops being
# found, and the trigger reports the endpoint as unscanned forever while the
# artifact sits on disk.


def test_candidate_id_is_stable_across_calls():
    cand = {"signal": "route", "location": "src/api.py:42", "label": "/health"}
    first = crew_endpoints._candidate_record(cand)
    second = crew_endpoints._candidate_record(dict(cand))
    assert first["id"] == second["id"]
    assert first["id"].startswith("cand-")


def test_candidate_id_matches_the_documented_hash():
    # Pin the construction, not just its stability: a change to the hash
    # input is a change to where every previously written scan is looked
    # for, so it must be a deliberate edit to this test rather than a
    # silent behaviour change.
    cand = {"signal": "ingress", "location": "infra/main.tf:7"}
    expected = hashlib.sha1(
        b"ingress:infra/main.tf:7").hexdigest()[:8]
    assert crew_endpoints._candidate_record(cand)["id"] == f"cand-{expected}"


def test_candidate_id_varies_with_signal_and_location():
    base = {"signal": "route", "location": "src/api.py:42"}
    other_loc = dict(base, location="src/api.py:43")
    other_sig = dict(base, signal="ingress")
    ids = {crew_endpoints._candidate_record(c)["id"]
           for c in (base, other_loc, other_sig)}
    assert len(ids) == 3, "distinct (signal, location) must not collide"


def test_candidate_id_ignores_the_label():
    # The label is display text and may be improved later; changing it must
    # not relocate the artifact path and orphan an existing scan.
    a = crew_endpoints._candidate_record(
        {"signal": "route", "location": "src/api.py:42", "label": "/health"})
    b = crew_endpoints._candidate_record(
        {"signal": "route", "location": "src/api.py:42", "label": "/healthz"})
    assert a["id"] == b["id"]


# --- BLOCK 5: the traversal guard on a frozen artifactPath -------------------
#
# `.crew/endpoints.json` is a committed, hand-editable file, and `_relative_
# safe` is the documented defence against a hand-edited `artifactPath` that
# escapes the repo. Nothing named `_relative_safe` before this round -- a
# review found that deleting the guard entirely left every other test green.

def test_relative_safe_rejects_a_traversal_value(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_endpoints._relative_safe(  # pylint: disable=protected-access
        str(root), "../../../../etc/passwd", "default.md")
    assert got == "default.md"


def test_relative_safe_accepts_a_value_that_stays_inside(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_endpoints._relative_safe(  # pylint: disable=protected-access
        str(root), "docs/security-scans/ep-0001.md", "default.md")
    assert got == "docs/security-scans/ep-0001.md"


def test_frozen_artifact_path_traversal_falls_back_to_the_computed_default(
        tmp_path):
    """BLOCK 5, end to end through the function callers actually use: a
    hand-edited `artifactPath` that escapes the repo must fall back to the
    computed default, not be trusted."""
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "ep-0001", "location": "src/app.py:10",
              "artifactPath": "../../../../etc/passwd"}
    got = crew_endpoints.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0001.md")


# --- Finding 7: `location` travels on an unscanned hit -----------------------

def test_unscanned_hit_surfaces_location(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["location"] == "src/app.py:10"


def test_unsafe_id_hit_surfaces_location_too(tmp_path, monkeypatch):
    """Finding 7 on the OTHER branch of `_unscanned_hit`: an unsafe id still
    has to name where it was declared, not just a safe id's hit."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "../../../unrelated", "endpoint": "https://api.example/v1/x",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["location"] == "src/app.py:10"


def test_candidate_hit_surfaces_location_too(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    hits = [h for h in endpoints["unscanned"] if h["source"] == "inferred"]
    assert hits[0]["location"].startswith("app.py")


# --- Finding 8: a confirmed-but-never-frozen scan is detectable --------------

def test_unfrozen_confirmed_scan_is_surfaced(tmp_path, monkeypatch):
    """A declared record that reads as scanned via the freshly COMPUTED
    default path, but was never frozen there with --record-scan-artifact,
    must be detectable -- the missing freeze step is otherwise silent until
    a repo-shape change orphans the artifact."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_endpoints.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    assert endpoints["unfrozen"]
    assert endpoints["unfrozen"][0]["id"] == "ep-0001"


def test_a_frozen_scan_is_not_reported_as_unfrozen(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://api.example/v1/widgets", "src/app.py:10")
    artifact = crew_endpoints.record_scan_artifact(str(root), record["id"])
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    assert endpoints["unfrozen"] == []


# --- Finding 9: a closed record's location stays excluded from inference ----

def test_a_closed_records_location_does_not_surface_as_a_fresh_candidate(
        tmp_path, monkeypatch):
    """A dismissed candidate (promoted to declared, then closed with the
    research findings) must not keep re-surfacing forever as a NEW inferred
    candidate under a different id -- its location has to stay excluded
    from fresh inference exactly like an open one does."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    location = crew_endpoints.infer_endpoints(str(root))[0]["location"]

    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "researched and dismissed",
        "source": "declared", "status": "closed",
        "location": location, "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert not any(h.get("source") == "inferred" for h in endpoints["unscanned"])


# --- Finding 10: _MONOREPO_SKIP_DIRS ------------------------------------------

def test_vendored_manifests_do_not_count_toward_monorepo_detection(tmp_path):
    """A vendored/generated tree can legitimately carry its own manifests;
    without the skip list every repo with a vendored dependency checked in
    under node_modules/vendor/.venv/dist would misclassify as a monorepo and
    relocate every new record's scan path."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "node_modules" / "pkg-a").mkdir(parents=True)
    (root / "vendor" / "dep").mkdir(parents=True)
    (root / "node_modules" / "pkg-a" / "pyproject.toml").write_text(
        "", encoding="utf-8")
    (root / "vendor" / "dep" / "go.mod").write_text(
        "module dep\n", encoding="utf-8")
    assert not crew_endpoints._is_monorepo(str(root))  # pylint: disable=protected-access


# --- Finding 11: re-declaring an existing id must not reopen it -------------

def test_redeclare_does_not_reopen_a_closed_record(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    doc = json.loads((root / ".crew" / "endpoints.json").read_text(
        encoding="utf-8"))
    for stored in doc["records"]:
        if stored["id"] == record["id"]:
            stored["status"] = "closed"
    (root / ".crew" / "endpoints.json").write_text(
        json.dumps(doc), encoding="utf-8")

    updated = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x-renamed", "a.py:2",
        endpoint_id=record["id"])
    assert updated["status"] == "closed"
    assert updated["endpoint"] == "https://a.example/x-renamed"


def test_redeclare_preserves_an_open_record_status_too(tmp_path):
    """Not just "never reopens" -- re-declaring must not disturb status at
    all, in either direction."""
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    updated = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:2", endpoint_id=record["id"])
    assert updated["status"] == "open"


# --- Finding 12: the ledger stores POSIX separators -------------------------

def test_record_scan_artifact_stores_posix_separators(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    crew_endpoints.record_scan_artifact(str(root), record["id"])
    stored = crew_endpoints.load_endpoints(str(root))[0]
    assert "\\" not in stored["artifactPath"]
    assert stored["artifactPath"] == "docs/security-scans/" + record["id"] + ".md"


def test_scan_artifact_path_normalises_backslashes_in_a_frozen_path(tmp_path):
    """Same fix as above, checked portably: on Windows a raw backslash
    string already resolves as a path (backslash IS the native separator
    there), so a test that only checks "does the file get found" cannot
    tell this OS apart from a POSIX clone where it would not. This pins the
    RETURNED VALUE instead, which must be POSIX-normalised regardless of
    which OS the test itself runs on."""
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "ep-0001", "location": "src/app.py:10",
              "artifactPath": "docs\\security-scans\\ep-0001.md"}
    got = crew_endpoints.scan_artifact_path(str(root), record)
    assert got == "docs/security-scans/ep-0001.md"


def test_a_backslash_frozen_path_still_resolves_to_a_real_file(
        tmp_path, monkeypatch):
    """Reproduced: a ledger entry frozen with native separators -- what
    freezing on Windows produced before this fix -- must still find its
    artifact on ANY OS, not read as permanently unscanned because a
    backslash-joined string is not a path separator here."""
    monkeypatch.setattr(crew_endpoints, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "docs" / "security-scans").mkdir(parents=True)
    (root / "docs" / "security-scans" / "ep-0001.md").write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
        "artifactPath": "docs\\security-scans\\ep-0001.md",
    }])
    endpoints = crew_endpoints.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


# --- BLOCK 2: declare_endpoint under concurrency -----------------------------

def test_concurrent_threads_declaring_distinct_endpoints_all_survive(tmp_path):
    """Reproduced without the fix: 20 in-process threads declaring 20
    distinct endpoints kept 1, with 0 errors raised. The lock has to make
    every one of them land."""
    root = crew_fixtures.make_repo(tmp_path)
    n = 20
    barrier = threading.Barrier(n)

    def declare(i):
        barrier.wait()
        crew_endpoints.declare_endpoint(
            str(root), f"https://svc-{i}.example/x", f"svc_{i}.py:1")

    threads = [threading.Thread(target=declare, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    records = crew_endpoints.load_endpoints(str(root))
    assert len(records) == n
    assert len({r["id"] for r in records}) == n


# --- T-0003: the ledger fails closed, under an OS advisory lock --------------
#
# A lock timeout or a failed write must never hand back a record (or a frozen
# path) that did not land, and the lock itself is an OS advisory lock
# (`flock` on POSIX, `msvcrt.locking` on Windows) on a persistent file,
# paired with a per-file in-process mutex. Nothing in crew deletes, renames
# or reads that file, so there is no staleness, takeover or token to test.

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(crew_endpoints.__file__))


def _lock_path(root):
    return crew_endpoints._endpoints_lock_path(str(root))  # pylint: disable=protected-access


@contextlib.contextmanager
def _held_endpoints_lock(root):
    """Holds the ledger's OS lock on a descriptor of its own, the way
    another process would -- but without the in-process mutex, so a call
    made against `root` meanwhile gets the mutex and is then refused by the
    OS lock itself."""
    path = _lock_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        assert crew_endpoints._os_try_lock(fd)  # pylint: disable=protected-access
        yield path
    finally:
        try:
            crew_endpoints._os_unlock(fd)  # pylint: disable=protected-access
        finally:
            os.close(fd)


class _WorkerStopped(BaseException):
    """Raised inside an abandoned worker thread so it cannot outlive its
    test. A BaseException, so no `except OSError`/`except Exception` in the
    code under test can swallow it."""


@contextlib.contextmanager
def _bounded_worker(monkeypatch, target, on_stop=None):
    """Runs `target()` in a daemon thread and yields `(worker, outcome)`.

    Review round 1 NIT: a regressed worker that outlived its join kept
    running after `monkeypatch.undo()` restored the real functions, took the
    lock and wrote a second record into the ledger while later tests ran.
    Here, once the with-block exits, `stop` is set and the worker's next
    `os.open`/`os.fstat`/`os.replace`/`_os_try_lock`/`time.sleep` (and the
    rest guarded below) raises `_WorkerStopped` -- before any write can
    land, because the ledger only ever changes through `os.replace`.

    `on_stop` runs after `stop` is set and BEFORE the join: it is how a test
    releases a worker blocked where no guard can reach it -- a holder child
    killed so a kernel wait returns, or an Event set so a fake lock returns
    -- so the worker's next guarded call stops it.

    The guards wrap whatever the test already patched, so patch first and
    enter this second. They fire on the worker thread only."""
    stop = threading.Event()
    outcome = {}
    holder = {}

    def guarded(real):
        def call(*args, **kwargs):
            if stop.is_set() and threading.current_thread() is holder["t"]:
                raise _WorkerStopped()
            return real(*args, **kwargs)
        return call
    for name in ("open", "fstat", "rename", "remove", "replace", "link"):
        monkeypatch.setattr(crew_endpoints.os, name,
                            guarded(getattr(crew_endpoints.os, name)))
    monkeypatch.setattr(crew_endpoints, "_os_try_lock",
                        guarded(crew_endpoints._os_try_lock))  # pylint: disable=protected-access
    monkeypatch.setattr(crew_endpoints.time, "sleep",
                        guarded(crew_endpoints.time.sleep))

    def run():
        try:
            outcome["result"] = target()
        except _WorkerStopped:
            outcome["stopped"] = True
    holder["t"] = threading.Thread(target=run, daemon=True)
    holder["t"].start()
    try:
        yield holder["t"], outcome
    finally:
        stop.set()
        if on_stop is not None:
            on_stop()
        holder["t"].join(timeout=5)


_HOLDER_CHILD = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import crew_endpoints
lock, failure = crew_endpoints._acquire_endpoints_lock(sys.argv[2])
if lock is None:
    print("FAILED", failure, flush=True)
    sys.exit(1)
print("READY", flush=True)
time.sleep(600)
"""

_DECLARE_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import crew_endpoints
print(json.dumps(crew_endpoints.declare_endpoint(sys.argv[2], sys.argv[3],
                                                 sys.argv[4])))
"""


def _spawn_holder(root):
    """A child process that takes the ledger lock through crew's own code
    and holds it until killed. Returns the Popen once the child has said
    READY; the caller kills it in a `finally`. The READY read is bounded by
    a thread join, so a child that never answers fails the test rather than
    hanging it (select() does not work on Windows pipes)."""
    child = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", _HOLDER_CHILD, _SCRIPTS_DIR, str(root)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = {}
    reader = threading.Thread(
        target=lambda: line.setdefault("v", child.stdout.readline()),
        daemon=True)
    reader.start()
    reader.join(timeout=30)
    if line.get("v", "").strip() != "READY":
        _kill(child)
        pytest.fail(f"holder child did not take the lock: {line.get('v')!r}")
    return child


def _kill(child):
    child.kill()
    try:
        child.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def _declare_in_child(root, endpoint, location):
    completed = subprocess.run(
        [sys.executable, "-c", _DECLARE_CHILD, _SCRIPTS_DIR, str(root),
         endpoint, location],
        capture_output=True, text=True, timeout=60, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _seeded_ledger(root):
    first = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    assert "error" not in first
    ledger = root / ".crew" / "endpoints.json"
    return first, ledger, ledger.read_bytes()


def test_declare_endpoint_returns_error_on_lock_timeout(tmp_path, monkeypatch):
    """BLOCK 6a, reproduced: hold the lock past the (monkeypatched small)
    timeout. The old behaviour fell through and wrote anyway, unlocked --
    the lost-update shape BLOCK 2 covers, reached a different way. Nothing
    may be written, and the caller gets an error, not a record."""
    root = crew_fixtures.make_repo(tmp_path)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.05)
    with _held_endpoints_lock(root):
        result = crew_endpoints.declare_endpoint(
            str(root), "https://a.example/x", "a.py:1")
    assert "held by another writer" in result["error"]
    assert not (root / ".crew" / "endpoints.json").exists()


def test_declare_endpoint_returns_error_on_write_failure(tmp_path, monkeypatch):
    """BLOCK 6b: a failed write (os.replace raising) must never be handed
    back as a landed record."""
    root = crew_fixtures.make_repo(tmp_path)

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(crew_endpoints.os, "replace", boom)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    assert "error" in result
    assert not (root / ".crew" / "endpoints.json").exists()


def test_declare_endpoint_retries_a_windows_permission_error_then_lands(
        tmp_path, monkeypatch):
    """Windows semantics simulated on Linux: os.replace raises
    PermissionError twice (the target momentarily open by a reader) then
    succeeds. Not gated on os.name -- see _replace_with_retry."""
    root = crew_fixtures.make_repo(tmp_path)
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("simulated transient lock")
        return real_replace(*a, **kw)
    monkeypatch.setattr(crew_endpoints.os, "replace", flaky)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    assert "error" not in result
    assert calls["n"] == 3
    assert crew_endpoints.load_endpoints(str(root)) == [result]


def test_declare_endpoint_gives_up_after_persistent_permission_errors(
        tmp_path, monkeypatch):
    """The replace retry is bounded: a PermissionError that never clears
    surfaces as a failure rather than hanging or silently succeeding."""
    root = crew_fixtures.make_repo(tmp_path)
    monkeypatch.setattr(crew_endpoints, "_REPLACE_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(crew_endpoints, "_REPLACE_RETRY_SLEEP_SECONDS", 0.02)

    def always_denied(*_a, **_kw):
        raise PermissionError("simulated persistent lock")
    monkeypatch.setattr(crew_endpoints.os, "replace", always_denied)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    assert "error" in result
    assert not (root / ".crew" / "endpoints.json").exists()


def test_replace_retry_terminates_when_the_wall_clock_stands_still(
        tmp_path, monkeypatch):
    """Codex BLOCK: the retry used to be bounded by `time.time()`, which a
    clock pinned to a constant never lets reach its deadline, so a
    PermissionError that never clears spun forever while holding the lock.
    Bounded by an attempt count it gives up, returns an error, and leaves
    the ledger byte for byte as it was. Under `_bounded_worker`, so a
    regression FAILS here rather than hanging the suite."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    monkeypatch.setattr(crew_endpoints, "_REPLACE_RETRY_SLEEP_SECONDS", 0.001)
    monkeypatch.setattr(crew_endpoints.time, "time", lambda: 1_000_000.0)
    calls = {"n": 0}

    def always_denied(*_a, **_kw):
        calls["n"] += 1
        raise PermissionError("simulated persistent lock")
    monkeypatch.setattr(crew_endpoints.os, "replace", always_denied)

    with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
            str(root), "https://b.example/y", "b.py:1")) as (worker, outcome):
        worker.join(timeout=5)

        assert not worker.is_alive(), (
            f"_replace_with_retry still retrying after 5s ({calls['n']} "
            "attempts) with a frozen clock")
        assert "error" in outcome["result"]
        assert calls["n"] == crew_endpoints._REPLACE_RETRY_ATTEMPTS  # pylint: disable=protected-access
        assert ledger.read_bytes() == before


def test_lock_wait_terminates_when_the_wall_clock_stands_still(
        tmp_path, monkeypatch):
    """The wait for the ledger lock was bounded by a `time.time()`
    deadline, so while another holder kept the lock a wall clock that stood
    still (pinned, as here) never reached it and declare_endpoint spun
    forever. Bounded by `time.monotonic()` it gives up, and leaves the
    ledger byte for byte as it was. Under `_bounded_worker`, so a
    regression FAILS rather than hanging the suite."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_RETRY_SECONDS", 0.01)
    frozen = time.time()
    monkeypatch.setattr(crew_endpoints.time, "time", lambda: frozen)

    with _held_endpoints_lock(root) as lock_path:
        with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
                str(root), "https://b.example/y", "b.py:1")) as (worker, outcome):
            worker.join(timeout=5)

            assert not worker.is_alive(), (
                "declare_endpoint still waiting for the ledger lock after 5s "
                "with a frozen wall clock")
            assert "held by another writer" in outcome["result"]["error"]
            assert os.path.exists(lock_path)
            assert ledger.read_bytes() == before


def test_declare_endpoint_retries_a_transient_lock_open_error(
        tmp_path, monkeypatch):
    """Review round 1, kept: an OSError from opening the lock file returned
    at once, so a single transient Windows PermissionError failed the
    declare although the next try would have succeeded. It is retried
    within the same deadline and the record lands."""
    root = crew_fixtures.make_repo(tmp_path)
    real_open = os.open
    calls = {"n": 0}

    def denied_once(path, *args, **kwargs):
        if str(path).endswith(".oslock") and calls["n"] == 0:
            calls["n"] += 1
            raise PermissionError(13, "simulated transient lock-open denial")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(crew_endpoints.os, "open", denied_once)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert calls["n"] == 1
    assert crew_endpoints.load_endpoints(str(root)) == [result]


def test_lock_open_error_that_never_clears_fails_at_the_deadline(
        tmp_path, monkeypatch):
    """The retry above is bounded: an open error that never clears returns
    `{"error": ...}` once the deadline passes -- not at once, not never --
    names the OSError rather than blaming another holder, and leaves the
    ledger byte for byte as it was."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    real_open = os.open

    def always_denied(path, *args, **kwargs):
        if str(path).endswith(".oslock"):
            raise PermissionError(13, "simulated persistent lock-open denial")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(crew_endpoints.os, "open", always_denied)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_RETRY_SECONDS", 0.01)

    started = time.monotonic()
    with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
            str(root), "https://b.example/y", "b.py:1")) as (worker, outcome):
        worker.join(timeout=5)
        elapsed = time.monotonic() - started

        assert not worker.is_alive()
        assert elapsed >= 0.3
        assert "could not lock" in outcome["result"]["error"]
        assert "PermissionError" in outcome["result"]["error"]
        assert ledger.read_bytes() == before


def test_a_lock_call_error_that_is_not_unsupported_is_retried(
        tmp_path, monkeypatch):
    """Any OS-lock error that is neither busy nor unsupported (EIO here) is
    retried within the deadline, like an open error, and the record lands
    once it clears."""
    root = crew_fixtures.make_repo(tmp_path)
    real = crew_endpoints._os_try_lock  # pylint: disable=protected-access
    calls = {"n": 0}

    def flaky(fd):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(errno.EIO, "simulated transient lock error")
        return real(fd)
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", flaky)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert calls["n"] == 2
    assert crew_endpoints.load_endpoints(str(root)) == [result]


@pytest.mark.parametrize("exclusion", ["os-lock-only", "mutex-only"])
def test_a_second_thread_is_refused_while_the_first_holds_the_ledger(
        tmp_path, monkeypatch, exclusion):
    """Thread A is paused inside its read-modify-write; thread B's declare
    must come back with the lock error and the ledger must hold A's record
    only. Run once with each exclusion on its own. `os-lock-only` hands
    every call a fresh mutex, so B reaches the real OS lock through its own
    descriptor and only that refuses it (on Windows, this is the check that
    `msvcrt.locking` excludes a second handle in one process). `mutex-only`
    replaces `_os_try_lock` with a grant-everything fake -- the shape of
    Linux `flock` over NFS, emulated per process -- so only the mutex
    refuses B."""
    root = crew_fixtures.make_repo(tmp_path)
    if exclusion == "os-lock-only":
        monkeypatch.setattr(crew_endpoints, "_process_mutex",
                            lambda path: threading.Lock())
    else:
        monkeypatch.setattr(crew_endpoints, "_os_try_lock", lambda fd: True)
        monkeypatch.setattr(crew_endpoints, "_os_unlock", lambda fd: None)
    counted = crew_endpoints._os_try_lock  # pylint: disable=protected-access
    tries = {"n": 0}

    def counting_try(fd):
        tries["n"] += 1
        return counted(fd)
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", counting_try)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_RETRY_SECONDS", 0.01)
    entered, release = threading.Event(), threading.Event()
    real_load = crew_endpoints._load_endpoint_doc  # pylint: disable=protected-access
    a_state = {}

    def paused_load(r):
        doc = real_load(r)
        if threading.current_thread() is a_state.get("t"):
            entered.set()
            release.wait(10)
        return doc
    monkeypatch.setattr(crew_endpoints, "_load_endpoint_doc", paused_load)
    a_state["t"] = threading.Thread(target=lambda: a_state.setdefault(
        "r", crew_endpoints.declare_endpoint(
            str(root), "https://a.example/x", "a.py:1")))
    a_state["t"].start()
    try:
        assert entered.wait(10)
        with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
                str(root), "https://b.example/y", "b.py:1"),
                on_stop=release.set) as (worker, outcome):
            worker.join(timeout=5)
            assert not worker.is_alive()
            b_result = outcome["result"]
    finally:
        release.set()
        a_state["t"].join(timeout=10)

    assert "held by another writer" in b_result["error"]
    assert "error" not in a_state["r"]
    assert crew_endpoints.load_endpoints(str(root)) == [a_state["r"]]
    assert (tries["n"] > 1) == (exclusion == "os-lock-only")


def test_a_second_process_is_refused_while_a_child_holds_the_ledger(
        tmp_path, monkeypatch):
    """The OS lock is what excludes another process -- the in-process mutex
    cannot. A child takes the lock through crew's own code and sleeps; the
    parent's declare returns the lock error within its timeout plus slack,
    and the ledger is byte-identical."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_RETRY_SECONDS", 0.01)
    child = _spawn_holder(root)
    try:
        started = time.monotonic()
        with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
                str(root), "https://b.example/y", "b.py:1"),
                on_stop=child.kill) as (worker, outcome):
            worker.join(timeout=5)
            elapsed = time.monotonic() - started

            assert not worker.is_alive()
            assert "held by another writer" in outcome["result"]["error"]
            assert elapsed < 0.3 + 3
            assert ledger.read_bytes() == before
    finally:
        _kill(child)


def test_a_killed_holder_releases_the_ledger_at_once(tmp_path):
    """A holder that dies without releasing -- SIGKILL on POSIX,
    TerminateProcess on Windows, both via `Popen.kill()` -- leaves nothing
    to wait out: the kernel drops its lock, and the next declare lands
    within the default deadline. There is no stale window to expire."""
    root = crew_fixtures.make_repo(tmp_path)
    child = _spawn_holder(root)
    try:
        child.kill()
        child.wait(timeout=30)
        started = time.monotonic()
        result = crew_endpoints.declare_endpoint(
            str(root), "https://b.example/y", "b.py:1")
        elapsed = time.monotonic() - started
    finally:
        _kill(child)

    assert "error" not in result
    assert elapsed < crew_endpoints._ENDPOINTS_LOCK_TIMEOUT_SECONDS  # pylint: disable=protected-access
    assert crew_endpoints.load_endpoints(str(root)) == [result]


@pytest.mark.parametrize("code", ["ENOLCK", "EOPNOTSUPP", "EINVAL"])
def test_a_filesystem_that_cannot_lock_fails_closed_at_once(
        tmp_path, monkeypatch, code):
    """Some NFS/SMB/FUSE mounts refuse the lock outright. That must never
    mean "proceed unlocked": the declare returns an error naming the
    filesystem as unable to lock, without polling out the deadline, the
    ledger bytes are unchanged, and no temp file is left behind."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 3)
    calls = {"n": 0}

    def unsupported(_fd):
        calls["n"] += 1
        raise OSError(getattr(errno, code), f"simulated {code}")
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", unsupported)

    started = time.monotonic()
    with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
            str(root), "https://b.example/y", "b.py:1")) as (worker, outcome):
        worker.join(timeout=10)
        elapsed = time.monotonic() - started

        assert not worker.is_alive()
        assert "cannot take an OS lock" in outcome["result"]["error"]
        assert f"simulated {code}" in outcome["result"]["error"]
        assert calls["n"] == 1
        assert elapsed < 1.5
        assert ledger.read_bytes() == before
        assert [p.name for p in (root / ".crew").iterdir()
                if p.name.endswith(".tmp")] == []


def test_a_fail_closed_lock_error_leaves_the_mutex_free(tmp_path, monkeypatch):
    """The unsupported error returns early; the in-process mutex taken
    before it must still be released, or every later declare in this
    process would time out."""
    root = crew_fixtures.make_repo(tmp_path)
    real = crew_endpoints._os_try_lock  # pylint: disable=protected-access

    def unsupported(_fd):
        raise OSError(errno.ENOLCK, "simulated ENOLCK")
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", unsupported)
    failed = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", real)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)

    landed = crew_endpoints.declare_endpoint(
        str(root), "https://b.example/y", "b.py:1")

    assert "error" in failed
    assert crew_endpoints.load_endpoints(str(root)) == [landed]


@pytest.mark.skipif(os.name == "nt", reason="the POSIX primitive: real fcntl")
@pytest.mark.parametrize("code", ["ENOLCK", "EOPNOTSUPP"])
def test_posix_flock_refusing_the_lock_fails_closed(tmp_path, monkeypatch, code):
    """The same classification one level down: the real POSIX primitive,
    with `fcntl.flock` raising what an unlockable mount returns, reaches
    declare as the fail-closed error, not a busy poll."""
    root = crew_fixtures.make_repo(tmp_path)

    def refuse(_fd, _op):
        raise OSError(getattr(errno, code), f"simulated {code}")
    monkeypatch.setattr(crew_endpoints.fcntl, "flock", refuse)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert "cannot take an OS lock" in result["error"]
    assert not (root / ".crew" / "endpoints.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="the POSIX primitive: real flock")
def test_posix_flock_reports_busy_instead_of_blocking(tmp_path):
    """`LOCK_NB` is what turns a held lock into a poll the deadline can end.
    Two descriptors on one file: the second try must come back False
    promptly, not block in the kernel."""
    path = str(tmp_path / "f.oslock")
    fd1 = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fd2 = os.open(path, os.O_RDWR)
    got = {}
    try:
        assert crew_endpoints._posix_try_lock(fd1)  # pylint: disable=protected-access
        probe = threading.Thread(
            target=lambda: got.setdefault(
                "v", crew_endpoints._posix_try_lock(fd2)),  # pylint: disable=protected-access
            daemon=True)
        probe.start()
        probe.join(timeout=5)
        crew_endpoints._posix_unlock(fd1)  # pylint: disable=protected-access
        probe.join(timeout=5)
    finally:
        os.close(fd1)
        os.close(fd2)
    assert got == {"v": False}


class _FakeFcntl:
    """Records every `flock` call; raises `error` on a lock (not unlock)
    when one is set. Constants are Linux's, but only their identity
    matters here."""
    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def flock(self, fd, op):
        self.calls.append((fd, op))
        if self.error is not None and op != self.LOCK_UN:
            raise self.error


class _FakeMsvcrt:
    """Records every `locking` call with the descriptor's file position AT
    THE CALL -- `msvcrt.locking` locks from the current position, so where
    the position stood is what decides which byte was locked. Constants are
    CPython's own values for the msvcrt module."""
    LK_UNLCK, LK_LOCK, LK_NBLCK, LK_RLCK, LK_NBRLCK = 0, 1, 2, 3, 4

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def locking(self, fd, mode, nbytes):
        self.calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        if self.error is not None and mode != self.LK_UNLCK:
            raise self.error


def test_the_posix_primitive_asks_for_a_non_blocking_exclusive_flock(
        monkeypatch):
    fake = _FakeFcntl()
    monkeypatch.setattr(crew_endpoints, "fcntl", fake)

    assert crew_endpoints._posix_try_lock(7) is True  # pylint: disable=protected-access
    crew_endpoints._posix_unlock(7)  # pylint: disable=protected-access

    assert fake.calls == [(7, fake.LOCK_EX | fake.LOCK_NB), (7, fake.LOCK_UN)]


@pytest.mark.parametrize("code", ["EWOULDBLOCK", "EAGAIN"])
def test_the_posix_busy_errnos_poll_on(monkeypatch, code):
    monkeypatch.setattr(crew_endpoints, "fcntl",
                        _FakeFcntl(OSError(getattr(errno, code), "busy")))

    assert crew_endpoints._posix_try_lock(7) is False  # pylint: disable=protected-access


def test_a_posix_lock_error_that_is_not_busy_is_raised(monkeypatch):
    monkeypatch.setattr(crew_endpoints, "fcntl",
                        _FakeFcntl(OSError(errno.ENOLCK, "no locks")))

    with pytest.raises(OSError) as raised:
        crew_endpoints._posix_try_lock(7)  # pylint: disable=protected-access
    assert raised.value.errno == errno.ENOLCK


def _positioned_fd(tmp_path):
    """A descriptor whose file position is NOT 0, so a primitive that forgot
    to seek would lock the wrong byte and the fake would record it."""
    fd = os.open(str(tmp_path / "f.oslock"), os.O_RDWR | os.O_CREAT, 0o600)
    os.write(fd, b"xyz")
    return fd


def test_the_windows_primitive_locks_byte_zero_without_blocking(
        tmp_path, monkeypatch):
    """Windows-only code, run on every platform against a fake msvcrt:
    `LK_NBLCK` (fail at once rather than retry-then-raise for ~10s), one
    byte, at position 0 whatever the descriptor's position was."""
    fake = _FakeMsvcrt()
    monkeypatch.setattr(crew_endpoints, "msvcrt", fake)
    fd = _positioned_fd(tmp_path)
    try:
        assert crew_endpoints._windows_try_lock(fd) is True  # pylint: disable=protected-access
    finally:
        os.close(fd)

    assert fake.calls == [(fake.LK_NBLCK, 1, 0)]


def test_the_windows_primitive_unlocks_byte_zero(tmp_path, monkeypatch):
    fake = _FakeMsvcrt()
    monkeypatch.setattr(crew_endpoints, "msvcrt", fake)
    fd = _positioned_fd(tmp_path)
    try:
        crew_endpoints._windows_unlock(fd)  # pylint: disable=protected-access
    finally:
        os.close(fd)

    assert fake.calls == [(fake.LK_UNLCK, 1, 0)]


@pytest.mark.parametrize("code", ["EACCES", "EDEADLK"])
def test_the_windows_busy_errnos_poll_on(tmp_path, monkeypatch, code):
    """Which errno a held region raises on Windows is taken from the CRT
    documentation (EACCES for a locking violation) and NOT measured here --
    `test_windows_busy_errno_is_classified_busy_natively` measures it on
    Windows."""
    monkeypatch.setattr(crew_endpoints, "msvcrt",
                        _FakeMsvcrt(OSError(getattr(errno, code), "busy")))
    fd = _positioned_fd(tmp_path)
    try:
        assert crew_endpoints._windows_try_lock(fd) is False  # pylint: disable=protected-access
    finally:
        os.close(fd)


def test_a_windows_lock_error_that_is_not_busy_is_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_endpoints, "msvcrt",
                        _FakeMsvcrt(OSError(errno.EINVAL, "bad region")))
    fd = _positioned_fd(tmp_path)
    try:
        with pytest.raises(OSError) as raised:
            crew_endpoints._windows_try_lock(fd)  # pylint: disable=protected-access
    finally:
        os.close(fd)
    assert raised.value.errno == errno.EINVAL


def test_declare_endpoint_through_the_windows_primitive(tmp_path, monkeypatch):
    """The Windows branch wired end to end, on any platform: with the
    Windows primitives selected and msvcrt faked, a declare locks byte 0
    non-blocking, lands, and unlocks byte 0 -- and a busy fake turns into
    the "held by another writer" error, a refusing one into fail-closed."""
    root = crew_fixtures.make_repo(tmp_path)
    fake = _FakeMsvcrt()
    monkeypatch.setattr(crew_endpoints, "msvcrt", fake)
    monkeypatch.setattr(crew_endpoints, "_os_try_lock",
                        crew_endpoints._windows_try_lock)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_endpoints, "_os_unlock",
                        crew_endpoints._windows_unlock)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.1)

    landed = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    assert fake.calls == [(fake.LK_NBLCK, 1, 0), (fake.LK_UNLCK, 1, 0)]
    fake.error = OSError(errno.EACCES, "busy")
    busy = crew_endpoints.declare_endpoint(
        str(root), "https://b.example/y", "b.py:1")
    fake.error = OSError(errno.EINVAL, "refused")
    refused = crew_endpoints.declare_endpoint(
        str(root), "https://c.example/z", "c.py:1")

    assert crew_endpoints.load_endpoints(str(root)) == [landed]
    assert "held by another writer" in busy["error"]
    assert "cannot take an OS lock" in refused["error"]


def test_each_platform_gets_its_own_primitive():
    if os.name == "nt":
        expected = (crew_endpoints._windows_try_lock, crew_endpoints._windows_unlock)  # pylint: disable=protected-access
    else:
        expected = (crew_endpoints._posix_try_lock, crew_endpoints._posix_unlock)  # pylint: disable=protected-access
    assert (crew_endpoints._os_try_lock, crew_endpoints._os_unlock) == expected  # pylint: disable=protected-access


@pytest.mark.skipif(os.name != "nt", reason="the real msvcrt: Windows only")
def test_windows_busy_errno_is_classified_busy_natively(tmp_path):
    """The Windows claims the fakes above cannot make: a second handle in
    the SAME process is refused while the first holds byte 0, the errno it
    is refused with is one `_windows_try_lock` treats as busy (so it polls
    rather than failing closed), and the unlock frees it."""
    import msvcrt  # pylint: disable=import-outside-toplevel,import-error
    path = str(tmp_path / "f.oslock")
    fd1 = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fd2 = os.open(path, os.O_RDWR)
    try:
        assert crew_endpoints._windows_try_lock(fd1)  # pylint: disable=protected-access
        os.lseek(fd2, 0, os.SEEK_SET)
        with pytest.raises(OSError) as raised:
            msvcrt.locking(fd2, msvcrt.LK_NBLCK, 1)
        assert crew_endpoints._windows_try_lock(fd2) is False  # pylint: disable=protected-access
        crew_endpoints._windows_unlock(fd1)  # pylint: disable=protected-access
        assert crew_endpoints._windows_try_lock(fd2) is True  # pylint: disable=protected-access
        crew_endpoints._windows_unlock(fd2)  # pylint: disable=protected-access
    finally:
        os.close(fd1)
        os.close(fd2)
    assert raised.value.errno in (errno.EACCES, errno.EDEADLK), raised.value


@pytest.mark.skipif(os.name == "nt", reason=(
    "Windows refuses to unlink a file another handle has open, so this race "
    "cannot be staged there; the platform-neutral twin below covers the "
    "check on every OS"))
def test_a_lock_file_replaced_between_open_and_lock_is_not_trusted(
        tmp_path, monkeypatch):
    """Measured in the T-0003 scratch experiment: unlinking a held lock file
    lets a second opener lock a fresh inode alongside the first holder. So
    a grant is trusted only if the descriptor still names the file at the
    path. Here the path is replaced between this call's open and its lock;
    the acquire must end holding the file now at the path."""
    root = crew_fixtures.make_repo(tmp_path)
    path = _lock_path(root)
    real = crew_endpoints._os_try_lock  # pylint: disable=protected-access
    calls = {"n": 0}

    def replace_then_lock(fd):
        calls["n"] += 1
        if calls["n"] == 1:
            os.unlink(path)
            with open(path, "w", encoding="ascii"):
                pass
        return real(fd)
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", replace_then_lock)

    lock, failure = crew_endpoints._acquire_endpoints_lock(str(root))  # pylint: disable=protected-access
    try:
        assert failure is None
        assert os.path.samestat(os.fstat(lock[0]), os.stat(path))
        assert calls["n"] == 2
    finally:
        crew_endpoints._release_endpoints_lock(lock)  # pylint: disable=protected-access


def test_a_grant_on_a_file_no_longer_at_the_path_is_released_and_retried(
        tmp_path, monkeypatch):
    """The platform-neutral twin of the test above: `os.stat` of the lock
    path reports a different file once, as it would after a replace. The
    grant is unlocked and retried, and the acquire ends holding the file
    at the path."""
    root = crew_fixtures.make_repo(tmp_path)
    path = _lock_path(root)
    other = tmp_path / "some-other-file"
    other.write_text("x", encoding="ascii")
    real_stat = os.stat
    real_unlock = crew_endpoints._os_unlock  # pylint: disable=protected-access
    state = {"lied": 0, "unlocks": 0}

    def lying_stat(target, *args, **kwargs):
        if os.fspath(target) == path and state["lied"] == 0:
            state["lied"] += 1
            return real_stat(str(other))
        return real_stat(target, *args, **kwargs)

    def counting_unlock(fd):
        state["unlocks"] += 1
        return real_unlock(fd)
    monkeypatch.setattr(crew_endpoints.os, "stat", lying_stat)
    monkeypatch.setattr(crew_endpoints, "_os_unlock", counting_unlock)

    lock, failure = crew_endpoints._acquire_endpoints_lock(str(root))  # pylint: disable=protected-access
    try:
        assert failure is None
        assert state == {"lied": 1, "unlocks": 1}
        assert os.path.samestat(os.fstat(lock[0]), real_stat(path))
    finally:
        crew_endpoints._release_endpoints_lock(lock)  # pylint: disable=protected-access


def test_release_frees_the_lock_even_when_unlock_raises(tmp_path, monkeypatch):
    """Round 2 BLOCK :457 was a release that could fail and leave the lock
    held. Release now only unlocks and closes; a failing unlock is ignored
    and the close still happens, and closing the descriptor is what frees an
    OS lock. So a declare after it -- in this process and in a child --
    lands."""
    root = crew_fixtures.make_repo(tmp_path)

    def failing_unlock(_fd):
        raise OSError(errno.EIO, "simulated unlock failure")
    monkeypatch.setattr(crew_endpoints, "_os_unlock", failing_unlock)
    # The default deadline, not a short one: Windows documents that a lock
    # left on a closed handle is released "depending upon available system
    # resources", not at once. On Linux the close frees it immediately.

    first = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    second = crew_endpoints.declare_endpoint(
        str(root), "https://b.example/y", "b.py:1")
    third = _declare_in_child(root, "https://c.example/z", "c.py:1")

    assert [r.get("error") for r in (first, second, third)] == [None] * 3
    assert len(crew_endpoints.load_endpoints(str(root))) == 3


def test_a_regressed_worker_cannot_outlive_its_test(tmp_path, monkeypatch):
    """The guard for every bounded test above, tested itself. `_os_try_lock`
    is replaced by a fake that blocks -- the shape of a dropped `LOCK_NB`,
    which no deadline can end. The worker is stuck inside it; once the
    with-block exits, the fake is released (as killing a holder child would
    release a kernel wait), the worker's next guarded call stops it before
    anything is written, and it is dead after the join."""
    root = crew_fixtures.make_repo(tmp_path)
    _, ledger, before = _seeded_ledger(root)
    blocker = threading.Event()

    def blocking_lock(_fd):
        blocker.wait(30)
        return True
    monkeypatch.setattr(crew_endpoints, "_os_try_lock", blocking_lock)

    with _bounded_worker(monkeypatch, lambda: crew_endpoints.declare_endpoint(
            str(root), "https://b.example/y", "b.py:1"),
            on_stop=blocker.set) as (worker, outcome):
        worker.join(timeout=0.3)
        assert worker.is_alive()

    assert not worker.is_alive()
    assert outcome == {"stopped": True}
    assert ledger.read_bytes() == before


def test_the_lock_file_is_persistent_and_never_removed(tmp_path):
    """Crew never deletes or renames the lock file: deleting a held one is
    exactly what lets two holders in (see the replaced-file test). It is
    created on first use and still there after release."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_endpoints.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    crew_endpoints.declare_endpoint(str(root), "https://b.example/y", "b.py:1")

    assert os.path.isfile(_lock_path(root))
    assert _lock_path(root).endswith(os.path.join(".crew", "endpoints.json.oslock"))


def test_a_leftover_pre_oslock_lock_file_does_not_block_a_declare(tmp_path):
    """A 1.0.28 crew left `.crew/endpoints.json.lock` behind (it removed any
    it judged stale). The new lock uses another name on purpose -- see the
    constant -- so a leftover old file neither blocks a declare nor is
    touched by one."""
    root = crew_fixtures.make_repo(tmp_path)
    old = root / ".crew" / "endpoints.json.lock"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("", encoding="ascii")

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert crew_endpoints.load_endpoints(str(root)) == [result]
    assert old.exists()


def test_record_scan_artifact_returns_error_on_lock_timeout(
        tmp_path, monkeypatch):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.05)
    with _held_endpoints_lock(root):
        result = crew_endpoints.record_scan_artifact(str(root), record["id"])
    assert isinstance(result, dict) and "error" in result
    assert crew_endpoints.load_endpoints(str(root))[0].get(
        "artifactPath") is None


def test_record_scan_artifact_returns_error_on_write_failure(
        tmp_path, monkeypatch):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(crew_endpoints.os, "replace", boom)

    result = crew_endpoints.record_scan_artifact(str(root), record["id"])
    assert isinstance(result, dict) and "error" in result
    assert crew_endpoints.load_endpoints(str(root))[0].get(
        "artifactPath") is None


def test_declare_endpoint_cli_reports_failure_on_lock_timeout(
        tmp_path, monkeypatch, capsys):
    """The CLI already checked `record.get("error")` for the unsafe-id
    case; the same check catches a lock timeout, non-zero exit and all."""
    root = crew_fixtures.make_repo(tmp_path)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.05)
    with _held_endpoints_lock(root):
        code = crew_state.main(["--root", str(root), "--declare-endpoint",
                                "https://a.example/x", "--location", "a.py:1"])
    assert code != 0
    assert "error" in capsys.readouterr().out


def test_record_scan_artifact_cli_reports_failure_on_write_failure(
        tmp_path, monkeypatch, capsys):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(crew_endpoints.os, "replace", boom)

    code = crew_state.main(["--root", str(root), "--record-scan-artifact",
                            record["id"]])
    assert code != 0
    assert "NOT recorded" in capsys.readouterr().err


# --- T-0003 review round 3 (the successor plan's first round) ----------------

def _refuse_write_opens_of_the_lock_file(monkeypatch):
    """Simulates a lock file another user created (sudo, a root container on
    a bind-mounted repo): opening it for writing is refused, opening it for
    reading is not. Returns the list of flags each lock-file open used."""
    real_open = os.open
    seen = []

    def open_as_another_user(path, flags, *args, **kwargs):
        if str(path).endswith(".oslock"):
            seen.append(flags)
            if flags & (os.O_RDWR | os.O_WRONLY):
                raise PermissionError(errno.EACCES, "simulated foreign owner")
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(crew_endpoints.os, "open", open_as_another_user)
    return seen


def test_a_lock_file_crew_may_not_write_still_lets_a_declare_land(
        tmp_path, monkeypatch):
    """Round 3 FIX :427: the lock file persists, so once another user has
    created it every open for writing is refused -- and the lock was taken
    only through a read-write open, so every declare after that waited out
    the deadline and failed, for good. A lock needs no write access on a
    local filesystem, so the declare falls back to a read-only descriptor
    and lands."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    (root / ".crew" / "endpoints.json.oslock").write_text("", encoding="ascii")
    seen = _refuse_write_opens_of_the_lock_file(monkeypatch)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.5)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert crew_endpoints.load_endpoints(str(root)) == [result]
    assert seen[-1] & (os.O_RDWR | os.O_WRONLY) == 0


def test_a_lock_file_crew_cannot_open_at_all_reports_the_write_open_error(
        tmp_path, monkeypatch):
    """When the read-only fallback fails too (the file is not there to be
    read, say), the error named is the read-write open's -- the one that
    says what is actually wrong -- not the fallback's."""
    root = crew_fixtures.make_repo(tmp_path)
    _refuse_write_opens_of_the_lock_file(monkeypatch)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.2)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert "PermissionError" in result["error"]
    assert "simulated foreign owner" in result["error"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_lock_file_is_created_readable_by_other_users(tmp_path):
    """0o644 less the umask -- what any file crew creates gets -- so another
    user can at least open it read-only. A 0o600 lock file created by one
    user locked every other user out of the ledger for good."""
    root = crew_fixtures.make_repo(tmp_path)
    reference = tmp_path / "reference"
    os.close(os.open(str(reference), os.O_RDWR | os.O_CREAT, 0o644))

    crew_endpoints.declare_endpoint(str(root), "https://a.example/x", "a.py:1")

    mode = os.stat(_lock_path(root)).st_mode & 0o777
    assert mode == os.stat(str(reference)).st_mode & 0o777
    assert mode & 0o044


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason=(
    "root opens a 0o444 file for writing anyway; the patched-open test above "
    "stages the refusal there"))
def test_a_read_only_lock_file_does_not_wedge_a_declare(tmp_path, monkeypatch):
    """The unpatched form of the fallback: a real read-only lock file. On
    Windows 0o444 is the read-only attribute, so this also shows
    `msvcrt.locking` working through a read-only handle there."""
    root = crew_fixtures.make_repo(tmp_path)
    lock_file = root / ".crew" / "endpoints.json.oslock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text("", encoding="ascii")
    os.chmod(str(lock_file), 0o444)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 1)
    try:
        result = crew_endpoints.declare_endpoint(
            str(root), "https://a.example/x", "a.py:1")
    finally:
        os.chmod(str(lock_file), 0o644)

    assert crew_endpoints.load_endpoints(str(root)) == [result]


@pytest.mark.skipif(os.name != "nt", reason="the real msvcrt: Windows only")
def test_windows_locks_through_a_read_only_handle_natively(tmp_path):
    """The Windows half of the read-only fallback's premise: a read-only
    handle can take the byte-0 lock, and it excludes a second handle."""
    path = str(tmp_path / "f.oslock")
    os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o644))
    fd1 = os.open(path, os.O_RDONLY)
    fd2 = os.open(path, os.O_RDONLY)
    try:
        assert crew_endpoints._windows_try_lock(fd1) is True  # pylint: disable=protected-access
        assert crew_endpoints._windows_try_lock(fd2) is False  # pylint: disable=protected-access
        crew_endpoints._windows_unlock(fd1)  # pylint: disable=protected-access
    finally:
        os.close(fd1)
        os.close(fd2)


def test_an_identity_check_that_never_passes_is_not_reported_as_contention(
        tmp_path, monkeypatch):
    """Round 3 FIX :456: every try was GRANTED and then rejected by the
    st_dev/st_ino re-check -- nobody held the lock -- and the error said
    "held by another writer". If fstat and stat disagree on some filesystem
    (unmeasured on Windows), that message sends the reader after a holder
    that does not exist. The error names the re-check instead."""
    root = crew_fixtures.make_repo(tmp_path)
    path = _lock_path(root)
    other = tmp_path / "some-other-file"
    other.write_text("x", encoding="ascii")
    real_stat = os.stat

    def always_another_file(target, *args, **kwargs):
        if os.fspath(target) == path:
            return real_stat(str(other))
        return real_stat(target, *args, **kwargs)
    monkeypatch.setattr(crew_endpoints.os, "stat", always_another_file)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_RETRY_SECONDS", 0.01)

    result = crew_endpoints.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")

    assert "identity re-check" in result["error"]
    assert "held by another writer" not in result["error"]


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork()")
def test_a_forked_child_does_not_inherit_a_held_mutex(tmp_path, monkeypatch):
    """Round 3 NIT :367: a process that forks while one of its threads holds
    the ledger lock gave the child a mutex locked forever, so every declare
    in the child reported "held by another writer". The child starts from
    fresh mutexes. The parent releases before the child declares, which
    also unlocks the flock the child's inherited descriptor shares."""
    root = crew_fixtures.make_repo(tmp_path)
    monkeypatch.setattr(crew_endpoints, "_ENDPOINTS_LOCK_TIMEOUT_SECONDS", 0.5)
    lock, failure = crew_endpoints._acquire_endpoints_lock(str(root))  # pylint: disable=protected-access
    assert failure is None
    result_r, result_w = os.pipe()
    go_r, go_w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child reports through the pipe
        try:
            os.close(result_r)
            os.close(go_w)
            os.read(go_r, 1)
            child = crew_endpoints.declare_endpoint(
                str(root), "https://b.example/y", "b.py:1")
            os.write(result_w, json.dumps(child).encode("utf-8"))
        finally:
            os._exit(0)  # pylint: disable=protected-access
    os.close(result_w)
    os.close(go_r)
    try:
        crew_endpoints._release_endpoints_lock(lock)  # pylint: disable=protected-access
        os.write(go_w, b"x")
        chunks = []
        while True:
            chunk = os.read(result_r, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(go_w)
        os.close(result_r)
        os.waitpid(pid, 0)

    child_result = json.loads(b"".join(chunks).decode("utf-8"))
    assert "error" not in child_result
    assert crew_endpoints.load_endpoints(str(root)) == [child_result]
