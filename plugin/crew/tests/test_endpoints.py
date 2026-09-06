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
import hashlib
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
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
    assert not crew_state.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_global_settings(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude",
                    {"gizmoduck@useful-claude-add-ons": True})
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_project_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@a-fork": True})
    assert crew_state.gizmoduck_installed(str(root))


def test_gizmoduck_installed_via_project_local_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@a-fork": True},
                    name="settings.local.json")
    assert crew_state.gizmoduck_installed(str(root))


def test_gizmoduck_disabled_value_does_not_count(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude",
                    {"gizmoduck@useful-claude-add-ons": False})
    root = crew_fixtures.make_repo(tmp_path)
    assert not crew_state.gizmoduck_installed(str(root))


def test_project_explicit_false_wins_over_global_true(tmp_path, monkeypatch):
    """Finding 4: project scope must win over global, and an explicit
    `false` there must mean off -- not "keep looking until something says
    true"."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True})
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@m": False})
    assert not crew_state.gizmoduck_installed(str(root))


def test_project_local_settings_outrank_project_settings(tmp_path, monkeypatch):
    _fake_home(monkeypatch, tmp_path)
    root = crew_fixtures.make_repo(tmp_path)
    _write_settings(root / ".claude", {"gizmoduck@m": True})
    _write_settings(root / ".claude", {"gizmoduck@m": False},
                    name="settings.local.json")
    assert not crew_state.gizmoduck_installed(str(root))


def test_string_false_does_not_count_as_installed(tmp_path, monkeypatch):
    """`"false"` (a JSON string) is truthy in Python; `if value` would read
    it as installed. Only a real boolean may decide this."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": "false"})
    root = crew_fixtures.make_repo(tmp_path)
    assert not crew_state.gizmoduck_installed(str(root))


def test_malformed_project_settings_defers_to_global(tmp_path, monkeypatch):
    """A project settings.json that fails to parse carries no signal
    either way -- it must not silently read as "off" while a wider scope
    has an explicit `true`."""
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True})
    root = crew_fixtures.make_repo(tmp_path)
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    assert crew_state.gizmoduck_installed(str(root))


def test_global_settings_local_json_is_consulted(tmp_path, monkeypatch):
    home = _fake_home(monkeypatch, tmp_path)
    _write_settings(home / ".claude", {"gizmoduck@m": True},
                    name="settings.local.json")
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.gizmoduck_installed(str(root))


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
    assert not crew_state.gizmoduck_installed(str(root))


# -- scan_artifact_path: single repo ------------------------------------------

def test_single_repo_path_rule(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "ep-0001", "location": "src/app.py:10"}
    got = crew_state.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0001.md")


def test_scan_artifact_path_rejects_a_traversal_id(tmp_path):
    """Finding 3: a hand-edited id must never reach a path join at all."""
    root = crew_fixtures.make_repo(tmp_path)
    record = {"id": "../../../unrelated", "location": "src/app.py:10"}
    assert crew_state.scan_artifact_path(str(root), record) is None


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
    got = crew_state.scan_artifact_path(str(root), record)
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
    assert crew_state._is_monorepo(str(root))  # pylint: disable=protected-access


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
    got = crew_state.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0003.md")


def test_single_go_mod_at_root_is_not_a_monorepo(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "go.mod").write_text("module solo\n", encoding="utf-8")
    assert not crew_state._is_monorepo(str(root))  # pylint: disable=protected-access


def test_frozen_artifact_path_survives_a_later_monorepo_flip(tmp_path):
    """Finding 6: once a scan lands and its path is frozen onto the record,
    a repo-shape change afterwards (a second manifest appearing anywhere)
    must not relocate or orphan it. Only a record with no frozen path yet
    uses the freshly computed classifier.
    """
    root = crew_fixtures.make_repo(tmp_path)
    (root / "a").mkdir()
    record = {"id": "ep-0001", "location": "a/app.py:10"}
    single_repo_path = crew_state.scan_artifact_path(str(root), record)
    assert single_repo_path == os.path.join("docs", "security-scans",
                                            "ep-0001.md")

    # A second manifest appears -- the repo is now a monorepo by the
    # documented signal (more than one go.mod/Cargo.toml/pyproject.toml) --
    # and the endpoint's own directory ("a/") is now an attributable package.
    (root / "b").mkdir()
    (root / "a" / "go.mod").write_text("module a\n", encoding="utf-8")
    (root / "b" / "go.mod").write_text("module b\n", encoding="utf-8")
    assert crew_state._is_monorepo(str(root))  # pylint: disable=protected-access

    # A record with NO frozen path recomputes and moves -- that is the
    # documented, accepted behaviour for anything not yet scanned.
    moved = crew_state.scan_artifact_path(str(root), record)
    assert moved != single_repo_path

    # But a record that already landed a scan keeps its own frozen path --
    # read back POSIX-normalised (finding 12), regardless of the separator
    # style the caller happened to freeze it with.
    frozen_record = dict(record, artifactPath=single_repo_path)
    assert (crew_state.scan_artifact_path(str(root), frozen_record)
            == single_repo_path.replace(os.sep, "/"))


# -- read_endpoints / declared endpointUnscanned ------------------------------

def test_trigger_fires_when_artifact_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
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
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    state = {"schema": crew_state.SCHEMA_CURRENT, "endpoints": endpoints}
    assert "endpointUnscanned" not in crew_state.evaluate_triggers(state)


def test_empty_artifact_does_not_discharge_the_obligation(tmp_path, monkeypatch):
    """Finding 2, half 1: `touch docs/security-scans/ep-0001.md` (0 bytes)
    must not permanently discharge the obligation."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.touch()

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_artifact_for_a_different_endpoint_does_not_confirm_this_one(
        tmp_path, monkeypatch):
    """Finding 2, half 1: non-empty is necessary but not sufficient -- the
    text must actually reference THIS endpoint."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/OTHER\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_todo_note_does_not_confirm_a_scan(tmp_path, monkeypatch):
    """BLOCK 4, reproduced: a to-do note that merely MENTIONS the URL is not
    evidence a scan actually ran. `echo "TODO: scan <url> later" > ...` used
    to discharge the obligation for free because the old check was a bare
    substring match with no proof a scan tool produced the file."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example.com/pay",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "TODO: scan https://api.example.com/pay later\n", encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_declared_bare_description_endpoint_fails_closed_with_no_needle(
        tmp_path, monkeypatch):
    """BLOCK 3, reproduced: a declared record whose endpoint text is a
    free-text description (the exact shape `work.md` used to invite) yields
    no matchable needle -- and must fail CLOSED, not be discharged by any
    non-empty (even marker-carrying) file at the computed path."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0002", "endpoint": "the payments admin console",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n\n" + _REAL_REPORT_MARKER,
                             encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"]


def test_endpoint_needle_covers_a_bare_hostname(tmp_path, monkeypatch):
    """BLOCK 3: the docs also invite a bare host (`report.md`: "a host or
    URL"); the needle derivation must cover that shape, not just a full
    URL or an absolute path."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0003", "endpoint": "payments.internal.example.com",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned payments.internal.example.com\n" + _REAL_REPORT_MARKER,
        encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


def test_endpoint_needle_rejects_a_bare_slash(tmp_path):
    """Finding 4's related bug: `_endpoint_needle('/')` used to return '/',
    which matches almost any markdown file containing a slash anywhere --
    not a needle at all."""
    assert crew_state._endpoint_needle("/") is None  # pylint: disable=protected-access


def test_empty_artifact_does_not_discharge_a_candidate_with_no_specific_target(
        tmp_path, monkeypatch):
    """Finding 2, half 1, for the case with no needle to check: an inferred
    candidate's label ("a Flask/FastAPI route decorator") has nothing
    specific to search for, so non-empty is ALL that can be required -- but
    it must still be required. An empty file must not pass just because
    there was nothing to cross-check."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "cand-aaaaaaaa", "endpoint": "a Flask/FastAPI route decorator",
        "source": "inferred", "status": "candidate",
        "location": "app.py:1",
    }
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.touch()
    assert not crew_state._artifact_confirms_scan(str(root), artifact, record)  # pylint: disable=protected-access


def test_a_traversal_id_reads_as_unscanned_not_as_scanned(tmp_path, monkeypatch):
    """Finding 3: an unsafe id must fail safe -- reported as unscanned,
    never silently treated as scanned by probing a path outside the repo."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "../../../unrelated", "endpoint": "https://api.example/v1/x",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
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
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints == {"installed": False, "unscanned": []}
    state = {"schema": crew_state.SCHEMA_CURRENT, "endpoints": endpoints}
    assert "endpointUnscanned" not in crew_state.evaluate_triggers(state)


def test_closed_records_never_count_as_unscanned(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "decommissioned",
        "source": "declared", "status": "closed",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


def test_unscanned_hit_carries_status_not_just_source(tmp_path, monkeypatch):
    """Finding 10: `status` -- not `source` -- is the authoritative field.
    A record whose fields disagree must still be checkable by `status`."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "candidate",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["status"] == "candidate"


# -- declared endpoints: declare_endpoint --------------------------------------

def test_declare_endpoint_writes_an_authoritative_open_record(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(
        str(root), "https://api.example/v1/widgets", "src/app.py:10",
        ticket="T-0100")
    assert record["source"] == "declared"
    assert record["status"] == "open"
    stored = crew_state.load_endpoints(str(root))
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
    result = crew_state.declare_endpoint(
        str(root), "https://api.example/v1/x", "src/app.py:10",
        endpoint_id="../../../unrelated")
    assert "error" in result
    assert crew_state.load_endpoints(str(root)) == []


def test_declare_endpoint_ids_do_not_collide_after_a_deletion(tmp_path):
    """Finding 7: declare a, declare b, delete a (hand-edit the committed
    ledger), declare c -- c must not mint b's id."""
    root = crew_fixtures.make_repo(tmp_path)
    first = crew_state.declare_endpoint(str(root), "https://a.example/x",
                                        "a.py:1")
    second = crew_state.declare_endpoint(str(root), "https://b.example/x",
                                         "b.py:1")
    assert first["id"] != second["id"]

    # Hand-edit the ledger the way a committed, human-editable file would
    # be: delete the first record but leave the mint sequence untouched.
    doc = json.loads((root / ".crew" / "endpoints.json").read_text(
        encoding="utf-8"))
    doc["records"] = [r for r in doc["records"] if r["id"] != first["id"]]
    (root / ".crew" / "endpoints.json").write_text(
        json.dumps(doc), encoding="utf-8")

    third = crew_state.declare_endpoint(str(root), "https://c.example/x",
                                        "c.py:1")
    assert third["id"] not in (first["id"], second["id"])


def test_declare_endpoint_is_atomic(tmp_path):
    """Finding 8: the write goes through a temp file plus os.replace, not
    write-in-place -- no lingering .tmp file after a normal write."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
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
    crew_state.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    original = (root / ".crew" / "endpoints.json").read_bytes()

    def boom(*_a, **_kw):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(crew_state.os, "replace", boom)

    crew_state.declare_endpoint(str(root), "https://b.example/x", "b.py:1")
    assert (root / ".crew" / "endpoints.json").read_bytes() == original


def test_ephemeral_candidate_ids_differ_by_location(tmp_path):
    """Finding 11's "dedup key ignoring location": two candidates sharing a
    signal but at different locations must never mint the same id -- that
    would make one scan artifact silently discharge both."""
    same_signal_a = {"signal": "python-route", "location": "a.py:1"}
    same_signal_b = {"signal": "python-route", "location": "b.py:1"}
    ids = {crew_state._candidate_record(c)["id"]  # pylint: disable=protected-access
          for c in (same_signal_a, same_signal_b)}
    assert len(ids) == 2


def test_written_ledger_uses_lf_not_crlf(tmp_path):
    """Nit 12: the newline="\\n" the write comment argues for, actually
    checked against the bytes on disk."""
    root = crew_fixtures.make_repo(tmp_path)
    crew_state.declare_endpoint(str(root), "https://a.example/x", "a.py:1")
    raw = (root / ".crew" / "endpoints.json").read_bytes()
    assert b"\r\n" not in raw


def test_record_scan_artifact_freezes_the_path(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(str(root), "https://a.example/x",
                                         "a.py:1")
    path = crew_state.record_scan_artifact(str(root), record["id"])
    # POSIX-normalised (finding 12); the freshly-computed default from
    # scan_artifact_path itself still uses native separators.
    assert path == crew_state.scan_artifact_path(
        str(root), record).replace(os.sep, "/")
    stored = crew_state.load_endpoints(str(root))[0]
    assert stored["artifactPath"] == path


def test_record_scan_artifact_is_none_for_an_unknown_id(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.record_scan_artifact(str(root), "ep-9999") is None


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
    hits = crew_state.infer_endpoints(str(root))
    assert any(h["signal"] == "python-route" and h["location"].startswith("app.py")
               for h in hits)


def test_infer_endpoints_empty_with_no_diff(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert crew_state.infer_endpoints(str(root)) == []


def test_infer_endpoints_ignores_a_commented_out_example(tmp_path):
    """Finding 9: a comment describing the shape must not itself be read as
    the shape."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.js").write_text(
        '// see app.post("/foo") for the pattern\n', encoding="utf-8")
    crew_fixtures._git(root, "add", "app.js")  # pylint: disable=protected-access
    assert crew_state.infer_endpoints(str(root)) == []


def test_infer_endpoints_ignores_a_match_inside_someone_elses_string(tmp_path):
    """Finding 9: a config value that merely CONTAINS the shape of a route
    registration, inside its own quotes, is not one."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.js").write_text(
        'const description = "app.get(\'/x\')";\n', encoding="utf-8")
    crew_fixtures._git(root, "add", "app.js")  # pylint: disable=protected-access
    assert crew_state.infer_endpoints(str(root)) == []


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
    assert crew_state.infer_endpoints(str(root)) == []


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
    assert crew_state.infer_endpoints(str(root)) == []


def test_infer_endpoints_gates_openapi_path_to_spec_files(tmp_path):
    """Finding 9: an indented slash-path YAML/JSON key that is not itself
    in a spec-shaped file (a shell PATH listing in a .sh script, say) must
    not be read as an OpenAPI path entry."""
    root = crew_fixtures.make_repo(tmp_path)
    (root / "setup.sh").write_text("  /usr/local/bin:\n", encoding="utf-8")
    crew_fixtures._git(root, "add", "setup.sh")  # pylint: disable=protected-access
    assert crew_state.infer_endpoints(str(root)) == []


def test_read_endpoints_surfaces_an_inferred_hit_as_an_ephemeral_candidate(
        tmp_path, monkeypatch):
    """BLOCK 1: candidates are computed inside the read path, never
    persisted. A fresh inferred hit with no matching declared record must
    surface in `unscanned` as a candidate, and the ledger file on disk must
    still hold nothing."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access

    endpoints = crew_state.read_endpoints(str(root), {})
    hits = [h for h in endpoints["unscanned"] if h["source"] == "inferred"]
    assert len(hits) == 1
    assert hits[0]["status"] == "candidate"
    # Never written -- load_endpoints (the ledger on disk) stays empty.
    assert crew_state.load_endpoints(str(root)) == []


def test_ephemeral_candidate_id_is_stable_across_reads(tmp_path, monkeypatch):
    """The same diff line must resolve to the same artifact path on every
    read, even though nothing about it is ever saved -- a scan written for
    it today has to be found tomorrow."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access

    first = crew_state.read_endpoints(str(root), {})
    second = crew_state.read_endpoints(str(root), {})
    first_ids = sorted(h["id"] for h in first["unscanned"])
    second_ids = sorted(h["id"] for h in second["unscanned"])
    assert first_ids == second_ids


def test_a_promoted_location_no_longer_surfaces_as_a_fresh_candidate(
        tmp_path, monkeypatch):
    """Once a location is covered by a persisted (declared) record, the same
    diff line must not ALSO surface as an inferred candidate under a
    different id."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    inferred = crew_state.infer_endpoints(str(root))
    assert inferred
    location = inferred[0]["location"]

    crew_state.declare_endpoint(str(root), "https://example.com/new-thing",
                               location)
    endpoints = crew_state.read_endpoints(str(root), {})
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
    first = crew_state._candidate_record(cand)
    second = crew_state._candidate_record(dict(cand))
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
    assert crew_state._candidate_record(cand)["id"] == f"cand-{expected}"


def test_candidate_id_varies_with_signal_and_location():
    base = {"signal": "route", "location": "src/api.py:42"}
    other_loc = dict(base, location="src/api.py:43")
    other_sig = dict(base, signal="ingress")
    ids = {crew_state._candidate_record(c)["id"]
           for c in (base, other_loc, other_sig)}
    assert len(ids) == 3, "distinct (signal, location) must not collide"


def test_candidate_id_ignores_the_label():
    # The label is display text and may be improved later; changing it must
    # not relocate the artifact path and orphan an existing scan.
    a = crew_state._candidate_record(
        {"signal": "route", "location": "src/api.py:42", "label": "/health"})
    b = crew_state._candidate_record(
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
    got = crew_state._relative_safe(  # pylint: disable=protected-access
        str(root), "../../../../etc/passwd", "default.md")
    assert got == "default.md"


def test_relative_safe_accepts_a_value_that_stays_inside(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_state._relative_safe(  # pylint: disable=protected-access
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
    got = crew_state.scan_artifact_path(str(root), record)
    assert got == os.path.join("docs", "security-scans", "ep-0001.md")


# --- Finding 7: `location` travels on an unscanned hit -----------------------

def test_unscanned_hit_surfaces_location(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["location"] == "src/app.py:10"


def test_unsafe_id_hit_surfaces_location_too(tmp_path, monkeypatch):
    """Finding 7 on the OTHER branch of `_unscanned_hit`: an unsafe id still
    has to name where it was declared, not just a safe id's hit."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    _write_ledger(root, [{
        "id": "../../../unrelated", "endpoint": "https://api.example/v1/x",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"][0]["location"] == "src/app.py:10"


def test_candidate_hit_surfaces_location_too(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    endpoints = crew_state.read_endpoints(str(root), {})
    hits = [h for h in endpoints["unscanned"] if h["source"] == "inferred"]
    assert hits[0]["location"].startswith("app.py")


# --- Finding 8: a confirmed-but-never-frozen scan is detectable --------------

def test_unfrozen_confirmed_scan_is_surfaced(tmp_path, monkeypatch):
    """A declared record that reads as scanned via the freshly COMPUTED
    default path, but was never frozen there with --record-scan-artifact,
    must be detectable -- the missing freeze step is otherwise silent until
    a repo-shape change orphans the artifact."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = {
        "id": "ep-0001", "endpoint": "https://api.example/v1/widgets",
        "source": "declared", "status": "open",
        "location": "src/app.py:10", "createdAt": "2026-09-01T00:00:00Z",
    }
    _write_ledger(root, [record])
    artifact = crew_state.scan_artifact_path(str(root), record)
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    assert endpoints["unfrozen"]
    assert endpoints["unfrozen"][0]["id"] == "ep-0001"


def test_a_frozen_scan_is_not_reported_as_unfrozen(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(
        str(root), "https://api.example/v1/widgets", "src/app.py:10")
    artifact = crew_state.record_scan_artifact(str(root), record["id"])
    artifact_path = root / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "scanned clean: https://api.example/v1/widgets\n"
        + _REAL_REPORT_MARKER, encoding="utf-8")

    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []
    assert endpoints["unfrozen"] == []


# --- Finding 9: a closed record's location stays excluded from inference ----

def test_a_closed_records_location_does_not_surface_as_a_fresh_candidate(
        tmp_path, monkeypatch):
    """A dismissed candidate (promoted to declared, then closed with the
    research findings) must not keep re-surfacing forever as a NEW inferred
    candidate under a different id -- its location has to stay excluded
    from fresh inference exactly like an open one does."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
    root = crew_fixtures.make_repo(tmp_path)
    (root / "app.py").write_text(
        '@app.route("/new-thing")\ndef handler():\n    pass\n',
        encoding="utf-8")
    crew_fixtures._git(root, "add", "app.py")  # pylint: disable=protected-access
    location = crew_state.infer_endpoints(str(root))[0]["location"]

    _write_ledger(root, [{
        "id": "ep-0001", "endpoint": "researched and dismissed",
        "source": "declared", "status": "closed",
        "location": location, "createdAt": "2026-09-01T00:00:00Z",
    }])
    endpoints = crew_state.read_endpoints(str(root), {})
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
    assert not crew_state._is_monorepo(str(root))  # pylint: disable=protected-access


# --- Finding 11: re-declaring an existing id must not reopen it -------------

def test_redeclare_does_not_reopen_a_closed_record(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    doc = json.loads((root / ".crew" / "endpoints.json").read_text(
        encoding="utf-8"))
    for stored in doc["records"]:
        if stored["id"] == record["id"]:
            stored["status"] = "closed"
    (root / ".crew" / "endpoints.json").write_text(
        json.dumps(doc), encoding="utf-8")

    updated = crew_state.declare_endpoint(
        str(root), "https://a.example/x-renamed", "a.py:2",
        endpoint_id=record["id"])
    assert updated["status"] == "closed"
    assert updated["endpoint"] == "https://a.example/x-renamed"


def test_redeclare_preserves_an_open_record_status_too(tmp_path):
    """Not just "never reopens" -- re-declaring must not disturb status at
    all, in either direction."""
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    updated = crew_state.declare_endpoint(
        str(root), "https://a.example/x", "a.py:2", endpoint_id=record["id"])
    assert updated["status"] == "open"


# --- Finding 12: the ledger stores POSIX separators -------------------------

def test_record_scan_artifact_stores_posix_separators(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    record = crew_state.declare_endpoint(
        str(root), "https://a.example/x", "a.py:1")
    crew_state.record_scan_artifact(str(root), record["id"])
    stored = crew_state.load_endpoints(str(root))[0]
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
    got = crew_state.scan_artifact_path(str(root), record)
    assert got == "docs/security-scans/ep-0001.md"


def test_a_backslash_frozen_path_still_resolves_to_a_real_file(
        tmp_path, monkeypatch):
    """Reproduced: a ledger entry frozen with native separators -- what
    freezing on Windows produced before this fix -- must still find its
    artifact on ANY OS, not read as permanently unscanned because a
    backslash-joined string is not a path separator here."""
    monkeypatch.setattr(crew_state, "gizmoduck_installed", lambda root=None: True)
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
    endpoints = crew_state.read_endpoints(str(root), {})
    assert endpoints["unscanned"] == []


# --- BLOCK 2: declare_endpoint under concurrency -----------------------------

def test_concurrent_threads_declaring_distinct_endpoints_all_survive(tmp_path):
    """Reproduced without the fix: 20 in-process threads declaring 20
    distinct endpoints kept 1, with 0 errors raised. The lock has to make
    every one of them land."""
    import threading

    root = crew_fixtures.make_repo(tmp_path)
    n = 20
    barrier = threading.Barrier(n)

    def declare(i):
        barrier.wait()
        crew_state.declare_endpoint(
            str(root), f"https://svc-{i}.example/x", f"svc_{i}.py:1")

    threads = [threading.Thread(target=declare, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    records = crew_state.load_endpoints(str(root))
    assert len(records) == n
    assert len({r["id"] for r in records}) == n
