"""Tests for crew_config_menu: the data-driven `/crew:config` menu (T-0075).

The menu is a view over `crew_config`'s own key lists, so the invariants here
are the ones that keep it from drifting: every row is a real key for its
layer, every writable row offers a value, and every value offered is one the
writer accepts. Save, delete and restore are tested for order -- validate
before write, back up before remove -- because that order is the feature.
"""
# The tests read and write fixture files through inline open() calls; the
# rewrite to `with` blocks is tracked in the T-0075 round-6 follow-up ticket.
# pylint: disable=consider-using-with
import errno
import json
import os
import shlex
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_config_files
import crew_config_menu as menu
import crew_fixtures
import crew_platform
import crew_state

_PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_TS = "20260927T120000Z"


def _now():
    import datetime  # pylint: disable=import-outside-toplevel
    return datetime.datetime(2026, 9, 27, 12, 0, 0,
                             tzinfo=datetime.timezone.utc)


def _repo(tmp_path, updates=None, global_cfg=None):
    """A repo holding defaults plus `updates`, and a global file. Returns
    `(root, global_path)` as strings."""
    cfg = crew_config.default_config()
    for dotted, value in (updates or {}).items():
        crew_config._set_path(cfg, dotted.split("."), value)  # pylint: disable=protected-access
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    gpath = tmp_path / "global.json"
    if global_cfg is not None:
        gpath.write_text(json.dumps(global_cfg), encoding="utf-8")
    return str(root), str(gpath)


def _rows(spec):
    return [row for area in spec["areas"] for row in area["rows"]]


def _table_key(row):
    return row.get("table") or row["path"]


# --- Step 3: the spec -------------------------------------------------------


def test_empty_role_entry_is_no_pin():
    absent = crew_state.resolve_role({"qa": {"provider": "codex"}}, "qa", "review")

    empty = crew_state.resolve_role(
        {"qa": {"provider": "codex", "roles": {"review": {}}}}, "qa", "review")

    assert empty == absent


def test_machine_menu_keys_are_exactly_the_global_leaves(tmp_path):
    root, gpath = _repo(tmp_path)

    rows = _rows(menu.menu_spec(root, "machine", gpath))

    writable = {_table_key(r) for r in rows if r["writable"]}
    assert writable == set(crew_config.leaf_paths(
        crew_config.default_global_config()))


def test_repo_menu_keys_are_real_repo_keys(tmp_path):
    root, gpath = _repo(tmp_path)
    leaves = set(crew_config.leaf_paths(crew_config.default_config()))

    rows = _rows(menu.menu_spec(root, "repo", gpath))

    assert {_table_key(r) for r in rows} == leaves
    assert all(crew_config.is_repo_path(r["path"]) for r in rows if r["writable"])


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_every_leaf_lands_in_exactly_one_area(tmp_path, layer):
    root, gpath = _repo(tmp_path)

    spec = menu.menu_spec(root, layer, gpath)

    paths = [r["path"] for r in _rows(spec)]
    assert len(paths) == len(set(paths))
    assert [a["id"] for a in spec["areas"]] == [a[0] for a in menu.AREAS]


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_every_writable_setting_offers_a_selectable_value(tmp_path, layer):
    root, gpath = _repo(tmp_path)

    rows = _rows(menu.menu_spec(root, layer, gpath))

    empty = [r["path"] for r in rows if r["writable"] and not r["choices"]]
    assert empty == []


_FIXTURES = {
    "plain": ({"guards.forcePush": "ask"}, {"pm": {"authority": "act"}}),
    "badprovider": ({"qa.provider": "gpt"}, {"qa": {"provider": "gpt"}}),
    "legacynull": ({"pm.authority": None}, {"pm": {"authority": None}}),
}


@pytest.mark.parametrize("fixture", sorted(_FIXTURES))
@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_every_offered_choice_is_accepted_by_the_writer(tmp_path, layer, fixture):
    root, gpath = _repo(tmp_path, *_FIXTURES[fixture])
    rows = _rows(menu.menu_spec(root, layer, gpath))

    refused = []
    for row in rows:
        for choice in row["choices"]:
            update = {row["path"]: choice["value"]}
            try:
                if layer == "machine":
                    crew_config.plan_global_write(update, gpath)
                else:
                    crew_config.plan_repo_write(root, update, gpath)
            except (crew_config.GlobalWriteRefused, crew_config.RepoWriteRefused,
                    crew_config.ProviderError) as exc:
                refused.append((row["path"], choice["value"], str(exc)))

    assert refused == []


def test_refused_rows_offer_no_choices_and_name_a_reason(tmp_path):
    root, gpath = _repo(tmp_path)

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    for path in ("scope.mode", "scope.allowCliApproval", "platform.os",
                 "schema", "context.autoClear.onlyRepos"):
        assert (rows[path]["writable"], rows[path]["choices"]) == (False, [])
        assert rows[path]["refusedReason"]


@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_a_refused_snapshot_probe_names_the_refusal(tmp_path, layer):
    # `except ... as exc` unbinds exc when the block ends, so a probe that
    # closed over it raised NameError the first time the menu called it.
    root, gpath = _repo(tmp_path, global_cfg={})
    target = os.path.join(root, ".crew", "config.json") if layer == "repo" else gpath
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("{bad")

    probe, _, reason = menu._probe_for(root, layer, gpath, None)  # pylint: disable=protected-access

    assert (probe("qa.provider", "codex"), bool(reason)) == (reason, True)


def test_repo_veto_rows_offer_only_a_veto(tmp_path):
    root, gpath = _repo(tmp_path)

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    for path in crew_config.REPO_VETO_ONLY:
        assert {json.dumps(c["value"]) for c in rows[path]["choices"]} <= {
            "false", "null"}


def test_machine_menu_never_offers_a_repo_only_key(tmp_path):
    root, gpath = _repo(tmp_path)

    paths = {r["path"] for r in _rows(menu.menu_spec(root, "machine", gpath))
             if r["writable"] or r["choices"]}

    for bad in ("tracker", "jira.project", "scope.mode",
                "scope.allowCliApproval", "platform.os",
                "context.autoClear.unsafeFocus"):
        assert bad not in paths
    assert not any(p.startswith(("autopilot.", "scope.", "platform."))
                   for p in paths
                   if not crew_config.is_global_path(p))


def test_machine_menu_shows_platform_and_schema_read_only(tmp_path):
    root, gpath = _repo(tmp_path)
    expected = ["schema"] + [p for p in crew_config.leaf_paths(
        crew_config.default_config()) if p.startswith("platform.")]

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "machine", gpath))}

    shown = [(p, rows[p]["writable"], rows[p]["choices"],
              bool(rows[p]["refusedReason"])) for p in expected if p in rows]
    assert shown == [(p, False, [], True) for p in expected]


def test_repo_veto_rows_never_offer_a_held_zero(tmp_path):
    root, gpath = _repo(tmp_path, {"context.autoClear.enabled": 0,
                                   "resume.auto": 0})

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    offered = [(p, c["value"]) for p in sorted(crew_config.REPO_VETO_ONLY)
               for c in rows[p]["choices"] if not crew_config.is_repo_veto(c["value"])]
    assert offered == []


@pytest.mark.parametrize("state", ["missing", "notjson", "empty", "array"])
def test_repo_rows_are_read_only_without_a_readable_config(tmp_path, state):
    root, gpath = _repo(tmp_path)
    if state == "missing":
        os.remove(_config(root))
    else:
        with open(_config(root), "w", encoding="utf-8") as handle:
            handle.write({"notjson": "{nope", "empty": "{}", "array": "[]"}[state])

    spec = menu.menu_spec(root, "repo", gpath)

    offered = [r["path"] for r in _rows(spec) if r["writable"] or r["choices"]]
    assert (offered, bool(spec["refusedReason"])) == ([], True)
    assert all(r["refusedReason"] for r in _rows(spec))


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_choices_are_filtered_through_the_merged_file(tmp_path, layer):
    if layer == "repo":
        root, gpath = _repo(tmp_path, {"qa.provider": "gpt"})
        blocked = "tracker"
    else:
        root, gpath = _repo(tmp_path, global_cfg={"qa": {"provider": "gpt"}})
        blocked = "pm.authority"

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, layer, gpath))}

    assert (rows[blocked]["writable"], rows[blocked]["choices"]) == (False, [])
    assert "qa.provider" in rows[blocked]["refusedReason"]
    assert rows["qa.provider"]["writable"]
    assert "codex" in [c["value"] for c in rows["qa.provider"]["choices"]]


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_menu_spec_reads_a_non_list_qa_order(tmp_path, capsys, layer):
    if layer == "repo":
        root, gpath = _repo(tmp_path, {"qa.order": 1})
        blocked = "tracker"
    else:
        root, gpath = _repo(tmp_path, global_cfg={"qa": {"order": True}})
        blocked = "pm.authority"

    code = menu.main(["--root", root, "--global-path", gpath, "spec",
                      "--layer", layer, "--json"])

    rows = {r["path"]: r for r in _rows(json.loads(capsys.readouterr().out))}
    assert (code, rows[blocked]["writable"]) == (0, False)
    assert "qa.order" in rows[blocked]["refusedReason"]
    assert rows["qa.order"]["writable"]


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_menu_spec_reads_an_object_at_a_leaf(tmp_path, capsys, layer):
    if layer == "machine":
        root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": {"a": 1}}})
        blocked, bad = "notify.chatId", "pm.authority"
    else:
        root, gpath = _repo(tmp_path, {"notify.chatId": {}})
        blocked, bad = "tracker", "notify.chatId"

    code = menu.main(["--root", root, "--global-path", gpath, "spec",
                      "--layer", layer, "--json"])

    rows = {r["path"]: r for r in _rows(json.loads(capsys.readouterr().out))}
    assert (code, rows[blocked]["writable"]) == (0, False)
    assert bad in rows[blocked]["refusedReason"]
    assert rows[bad]["writable"]
    assert layer == "repo" or "act" in [c["value"] for c in rows[bad]["choices"]]


def test_save_refuses_an_object_at_a_leaf(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={})
    before = open(gpath, "rb").read()

    code = menu.main(["--root", root, "--global-path", gpath, "save", "--changes",
                      '{"machine":{"pm.authority":{"a":1}}}'])

    out, err = capsys.readouterr()
    assert (code, "refused, nothing written" in err, "->" in out) == (2, True, False)
    assert open(gpath, "rb").read() == before


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_menu_spec_reads_a_non_object_open_table(tmp_path, capsys, layer):
    if layer == "machine":
        root, gpath = _repo(tmp_path, global_cfg={"qa": {"roles": 1}})
        blocked, bad = "pm.authority", "qa.roles"
    else:
        root, gpath = _repo(tmp_path, {"qa.roles.review": "codex"})
        blocked, bad = "tracker", "qa.roles.review"

    code = menu.main(["--root", root, "--global-path", gpath, "spec",
                      "--layer", layer, "--json"])

    rows = {r["path"]: r for r in _rows(json.loads(capsys.readouterr().out))}
    assert (code, rows[blocked]["writable"]) == (0, False)
    assert bad in rows[blocked]["refusedReason"]
    assert rows["qa.roles.review"]["writable"]
    assert any(isinstance(c["value"], dict) for c in rows["qa.roles.review"]["choices"])


def test_save_refuses_a_non_object_at_an_open_table(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    code = menu.main(["--root", root, "--global-path", gpath, "save", "--changes",
                      '{"repo":{"qa.roles":1}}'])

    assert (code, "refused, nothing written" in capsys.readouterr().err) == (2, True)
    assert open(_config(root), "rb").read() == before


def test_pending_set_unblocks_rows(tmp_path, capsys):
    root, gpath = _repo(tmp_path, {"qa.provider": "gpt"})
    pending = {"repo": {"qa.provider": "codex"}}

    rows = {r["path"]: r for r in _rows(
        menu.menu_spec(root, "repo", gpath, pending=pending))}
    code = menu.main(["--root", root, "--global-path", gpath, "spec", "--layer",
                      "repo", "--area", "memory", "--json", "--pending",
                      json.dumps(pending)])
    cli = {r["path"]: r for r in json.loads(capsys.readouterr().out)[
        "areas"][0]["rows"]}

    assert (rows["tracker"]["writable"], code, cli["tracker"]["writable"]) == (
        True, 0, True)


def test_menu_offers_null_only_where_the_writer_takes_it(tmp_path):
    root, gpath = _repo(tmp_path, {"context.autoClear.enabled": False})

    machine = _rows(menu.menu_spec(root, "machine", gpath))
    repo = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    offered = [r["path"] for r in machine if crew_config.enum_values(r["path"])
               and None in [c["value"] for c in r["choices"]]]
    tags = {p: [c["tags"] for c in repo[p]["choices"] if c["value"] is None]
            for p in ("guards.forcePush", "context.autoClear.enabled")}
    assert offered == []
    assert ["inherit machine" in t for t in tags["guards.forcePush"]] == [True]
    assert ["clear veto" in t for t in tags["context.autoClear.enabled"]] == [True]


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_spec_prints_the_layer_digest(tmp_path, capsys, layer):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    target = gpath if layer == "machine" else _config(root)
    raw = open(target, "rb").read()

    spec = menu.menu_spec(root, layer, gpath)
    menu.main(["--root", root, "--global-path", gpath, "spec", "--layer", layer,
               "--area", "guards"])
    out = capsys.readouterr().out
    os.remove(target)
    absent = menu.menu_spec(root, layer, gpath)["digest"]

    assert spec["digest"] == crew_config_files.digest(raw)
    assert f"digest: {spec['digest']}" in out
    assert absent == ("absent" if layer == "machine" else None)


def test_machine_rows_stay_writable_without_a_global_file(tmp_path):
    root, gpath = _repo(tmp_path)

    spec = menu.menu_spec(root, "machine", gpath)

    assert (spec["exists"], spec["refusedReason"]) == (False, None)
    assert any(r["writable"] for r in _rows(spec))


@pytest.mark.parametrize("repo_pin,global_pin,source", [
    ({"model": "gpt-5.6-luna"}, {"provider": "codex"}, "repo+global"),
    (None, {"provider": "codex", "model": "gpt-5.6-luna"}, "global"),
    ({"provider": "codex", "model": "gpt-5.6-luna"}, None, "repo"),
])
def test_role_row_names_both_layers_it_merges(tmp_path, repo_pin, global_pin,
                                              source):
    root, gpath = _repo(
        tmp_path,
        {"qa.roles": {"review": repo_pin}} if repo_pin else None,
        {"qa": {"roles": {"review": global_pin}}} if global_pin else {})

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    assert (rows["qa.roles.review"]["value"], rows["qa.roles.review"]["source"]) == (
        {"provider": "codex", "model": "gpt-5.6-luna"}, source)


def test_recommendation_is_listed_first(tmp_path):
    root, gpath = _repo(tmp_path)

    for layer in ("machine", "repo"):
        for row in _rows(menu.menu_spec(root, layer, gpath)):
            if row["writable"] and row["recommendation"] is not None:
                assert row["choices"][0]["value"] == row["recommendation"]["value"]
                assert "recommended" in row["choices"][0]["tags"]


def test_recommendations_are_real_keys_and_offered_choices(tmp_path):
    root, gpath = _repo(tmp_path)
    by_layer = {layer: {r["path"]: r for r in _rows(
        menu.menu_spec(root, layer, gpath))} for layer in ("machine", "repo")}

    for path, (value, reason) in menu.RECOMMENDATIONS.items():
        assert reason
        assert path in by_layer["repo"], path
        for rows in by_layer.values():
            if path in rows and rows[path]["writable"]:
                assert value in [c["value"] for c in rows[path]["choices"]]


def test_known_values_keys_are_real_leaves():
    leaves = set(crew_config.leaf_paths(crew_config.default_config()))

    assert set(menu.known_values()) <= leaves


def test_row_shows_current_value_and_source(tmp_path):
    root, gpath = _repo(tmp_path, {"tracker": "jira"},
                        {"pm": {"authority": "act"}})
    explain = {r["path"]: r for r in crew_config.explain_config(root, gpath)}

    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    assert (rows["pm.authority"]["value"], rows["pm.authority"]["source"]) == (
        explain["pm.authority"]["value"], explain["pm.authority"]["source"])
    assert (rows["tracker"]["value"], rows["tracker"]["source"]) == ("jira", "repo")
    assert rows["graph.tool"]["source"] in ("repo", "default")


def test_a_new_default_key_appears_without_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_state, "AUTOPILOT_DEFAULTS",
                        dict(crew_state.AUTOPILOT_DEFAULTS, newKnob=1))
    root, gpath = _repo(tmp_path)

    rows = {r["path"] for r in _rows(menu.menu_spec(root, "repo", gpath))}

    assert "autopilot.newKnob" in rows


# --- Step 4: save -----------------------------------------------------------

_MACHINE_SET = {"pm.authority": "act", "notify.provider": "telegram",
                "guards.forcePush": "ask", "memory.mode": "vault"}
_REPO_SET = {"tracker": "jira", "verifyGate": True, "autopilot.maxPhases": 6}


def _count_replaces(monkeypatch):
    calls = []
    real = os.replace

    def _counting(src, dst):
        calls.append(os.path.basename(dst))
        return real(src, dst)
    monkeypatch.setattr(crew_config.os, "replace", _counting)
    return calls


def test_save_writes_each_layer_once(tmp_path, monkeypatch):
    root, gpath = _repo(tmp_path, {"verifyGate": False})
    calls = _count_replaces(monkeypatch)

    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=True, global_path=gpath)

    # T-0050: Save also refreshes the owner's profile once per layer written.
    assert (code, sorted(c for c in calls if c != "profile.json")) == (
        0, ["config.json", "global.json"])
    assert calls.count("profile.json") == 2


def test_save_with_machine_changes_only_leaves_the_repo_file(tmp_path, monkeypatch):
    root, gpath = _repo(tmp_path)
    repo_file = os.path.join(root, ".crew", "config.json")
    before = open(repo_file, "rb").read()
    calls = _count_replaces(monkeypatch)

    menu.save(root, {"machine": _MACHINE_SET}, apply=True, global_path=gpath)

    assert ([c for c in calls if c != "profile.json"],
            open(repo_file, "rb").read()) == (["global.json"], before)


def test_save_validates_both_layers_before_writing_either(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "report-only"}})
    repo_file = os.path.join(root, ".crew", "config.json")
    before = (open(gpath, "rb").read(), open(repo_file, "rb").read())

    code = menu.save(root, {"machine": _MACHINE_SET,
                            "repo": {"scope.mode": "block"}},
                     apply=True, global_path=gpath)

    assert code == 2
    assert "scope.mode" in capsys.readouterr().err
    assert (open(gpath, "rb").read(), open(repo_file, "rb").read()) == before


def test_save_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    root, gpath = _repo(tmp_path)
    calls = _count_replaces(monkeypatch)

    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=False, global_path=gpath)

    out = capsys.readouterr().out
    assert (code, calls) == (0, [])
    assert "dry run" in out and "! pm.authority widens to" in out


def test_save_changing_a_key_back_is_no_change(tmp_path, monkeypatch, capsys):
    root, gpath = _repo(tmp_path, {"tracker": "jira"},
                        {"pm": {"authority": "act"}})
    calls = _count_replaces(monkeypatch)

    code = menu.save(root, {"machine": {"pm.authority": "act"},
                            "repo": {"tracker": "jira"}},
                     apply=True, global_path=gpath)

    assert (code, calls) == (0, [])
    assert "nothing to change" in capsys.readouterr().out


def test_save_reports_a_partial_os_failure(tmp_path, monkeypatch, capsys):
    root, gpath = _repo(tmp_path)

    def _fail(*_args, **_kwargs):
        raise OSError("read-only file system")
    monkeypatch.setattr(menu.crew_config, "write_repo_config", _fail)
    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=True, global_path=gpath)

    captured = capsys.readouterr()
    assert code == 1
    assert "machine layer: written" in captured.out
    assert "repo layer: NOT written" in captured.err
    assert json.loads(open(gpath, encoding="utf-8").read())["pm"]["authority"] == "act"


def test_save_reports_a_partial_refusal(tmp_path, monkeypatch, capsys):
    root, gpath = _repo(tmp_path)
    real = crew_config.write_global_config

    def _write_then_lose_the_repo_file(updates, path=None, **kwargs):
        out = real(updates, path, **kwargs)
        os.remove(_config(root))
        return out
    monkeypatch.setattr(menu.crew_config, "write_global_config",
                        _write_then_lose_the_repo_file)
    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=True, global_path=gpath)

    captured = capsys.readouterr()
    assert (code, "machine layer: written" in captured.out,
            "repo layer: NOT written" in captured.err) == (1, True, True)


def test_save_reports_a_refusal_on_the_first_write(tmp_path, monkeypatch, capsys):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    def _refuse(*_args, **_kwargs):
        raise crew_config.GlobalWriteRefused("the global file changed")
    monkeypatch.setattr(menu.crew_config, "write_global_config", _refuse)
    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=True, global_path=gpath)

    err = capsys.readouterr().err
    assert (code, "machine layer: NOT written" in err,
            "nothing was written" in err) == (1, True, True)
    assert open(_config(root), "rb").read() == before


def test_save_cli_takes_a_json_change_set(tmp_path, capsys):
    root, gpath = _repo(tmp_path)

    code = menu.main(["--root", root, "--global-path", gpath, "save",
                      "--changes", json.dumps({"repo": {"tracker": "sdp"}}),
                      "--apply"])

    assert code == 0, capsys.readouterr()
    written = json.loads(open(os.path.join(root, ".crew", "config.json"),
                              encoding="utf-8").read())
    assert written["tracker"] == "sdp"


# --- Step 5: delete and restore ---------------------------------------------


def _config(root):
    return os.path.join(root, ".crew", "config.json")


def _delete(root, gpath):
    """The owner's flow: the preview, then `--apply` bound to the two digests
    that preview printed (review round 3)."""
    try:
        plan = menu.plan_delete(root, gpath)
        expect = {"repo": plan["digest"], "machine": plan["machine"]}
    except menu.DeleteRefused:
        expect = None
    return menu.delete_repo_config(root, "repo", True, now=_now(),
                                   global_path=gpath, expect=expect)


def _backups(root):
    return sorted(n for n in os.listdir(os.path.join(root, ".crew"))
                  if n.startswith("config.json.bak-"))


@pytest.mark.parametrize("confirm,apply", [(None, True), ("wrong", True),
                                           ("repo", False)])
def test_delete_refuses_without_confirmation(tmp_path, confirm, apply):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()
    plan = menu.plan_delete(root, gpath)

    code = menu.delete_repo_config(root, confirm, apply, now=_now(),
                                   global_path=gpath, expect={
                                       "repo": plan["digest"],
                                       "machine": plan["machine"]})

    assert code == (0 if confirm == "repo" else 2)
    assert (_backups(root), open(_config(root), "rb").read()) == ([], before)


def test_delete_writes_backup_first(tmp_path, monkeypatch):
    root, gpath = _repo(tmp_path)
    original = open(_config(root), "rb").read()
    seen = []
    real_move = crew_config_files.move_aside

    def _checking_move(src, dest):
        got = real_move(src, dest)
        seen.append((os.path.exists(src), open(dest, "rb").read() == original))
        return got
    monkeypatch.setattr(crew_config_files, "move_aside", _checking_move)

    code = _delete(root, gpath)

    assert (code, seen, os.path.exists(_config(root))) == (0, [(False, True)], False)


def test_delete_refuses_when_the_move_fails(tmp_path, monkeypatch):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    def _fail(*_args, **_kwargs):
        raise OSError("read-only file system")
    monkeypatch.setattr(crew_config_files, "move_aside", _fail)
    code = _delete(root, gpath)

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (2, before, [])


def test_delete_backup_name_never_collides(tmp_path):
    root, gpath = _repo(tmp_path)
    crew_dir = os.path.join(root, ".crew")
    for name, body in ((f"config.json.bak-{_TS}", b"older"),
                       ("config.json.broken", b"broken")):
        with open(os.path.join(crew_dir, name), "wb") as handle:
            handle.write(body)

    _delete(root, gpath)

    assert _backups(root) == [f"config.json.bak-{_TS}", f"config.json.bak-{_TS}-2"]
    assert open(os.path.join(crew_dir, f"config.json.bak-{_TS}"), "rb").read() == b"older"
    assert open(os.path.join(crew_dir, "config.json.broken"), "rb").read() == b"broken"


_BOM = b"\xef\xbb\xbf"
_UNRESTORABLE = {"notjson": b"{not json", "empty": b"", "emptyobject": b"{}",
                 "array": b"[1]", "bom-notjson": _BOM + b"{nope"}


def _write_config(root, data):
    with open(_config(root), "wb") as handle:
        handle.write(data)


@pytest.mark.parametrize("state", sorted(_UNRESTORABLE))
def test_delete_refuses_a_config_restore_would_refuse(tmp_path, capsys, state):
    root, gpath = _repo(tmp_path)
    _write_config(root, _UNRESTORABLE[state])

    code = _delete(root, gpath)

    err = capsys.readouterr().err
    assert (code, open(_config(root), "rb").read(), _backups(root)) == (
        2, _UNRESTORABLE[state], [])
    assert "config.json.broken" in err and "by hand" in err


_PREDICATE_TABLE = dict(_UNRESTORABLE, **{
    "object": b'{"tracker": "jira"}\n', "bom": _BOM + b'{"tracker": "jira"}\n',
    "crlf": b'{\r\n  "tracker": "jira"\r\n}\r\n', "string": b'"x"',
    "null": b"null", "whitespace": b" \n"})


def test_delete_and_restore_share_one_predicate(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    verdicts = {}

    for name, data in sorted(_PREDICATE_TABLE.items()):
        _write_config(root, data)
        deleted = menu.delete_repo_config(root, "repo", False, now=_now(),
                                          global_path=gpath)
        with open(backup, "wb") as handle:
            handle.write(data)
        restored = menu.restore_repo_config(root, backup, False, now=_now())
        verdicts[name] = (deleted, restored)
    capsys.readouterr()

    assert {n: d == r for n, (d, r) in verdicts.items()} == {
        n: True for n in _PREDICATE_TABLE}
    assert {n for n, (d, _r) in verdicts.items() if d == 0} == {
        "object", "bom", "crlf"}


def test_delete_backs_up_by_rename(tmp_path, monkeypatch):
    import shutil  # pylint: disable=import-outside-toplevel
    root, gpath = _repo(tmp_path)
    inode = os.stat(_config(root)).st_ino

    def _fail(*_args, **_kwargs):
        raise OSError("a copy is not how this backs up")
    monkeypatch.setattr(shutil, "copy2", _fail)
    monkeypatch.setattr(shutil, "copyfile", _fail)
    code = _delete(root, gpath)

    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    assert (code, os.path.exists(_config(root))) == (0, False)
    if os.name != "nt":
        assert os.stat(backup).st_ino == inode


def test_delete_refuses_when_the_file_changed_after_the_plan(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    plan = menu.plan_delete(root, gpath)
    newer = b'{"tracker": "sdp", "x-new": 1}\n'
    _write_config(root, newer)

    code = menu.apply_delete(root, plan, "repo", now=_now(), expect={
        "repo": plan["digest"], "machine": plan["machine"]})

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (2, newer, [])
    assert "changed since the preview" in capsys.readouterr().err


def test_delete_refuses_while_the_lock_is_held(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(crew_config_files, "LOCK_WAIT_SECONDS", 0.1)
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()
    with open(_config(root) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("4242")

    code = _delete(root, gpath)

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (2, before, [])
    assert "config.json.lock" in capsys.readouterr().err


def test_delete_then_restore_is_byte_identical_with_bom_and_crlf(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    text = json.dumps(dict(crew_config.default_config(), tracker="jira"), indent=2)
    original = _BOM + text.replace("\n", "\r\n").encode("utf-8") + b"\r\n"
    _write_config(root, original)
    _delete(root, gpath)
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")

    code = menu.restore_repo_config(root, backup, True, now=_now())

    capsys.readouterr()
    assert (code, open(_config(root), "rb").read()) == (0, original)


def _preview(root, gpath, capsys):
    menu.delete_repo_config(root, None, False, now=_now(), global_path=gpath)
    return capsys.readouterr().out


@pytest.mark.parametrize("leaf,line", [
    ("x-local", "x-local: 1 -> (removed)"),
    ("foo.bar", "foo.bar: 2 -> (removed)"),
    ("tracker", 'tracker: "jira" -> "files"'),
], ids=["x-local", "foo.bar", "tracker"])
def test_delete_preview_lists_every_leaf_of_the_file(tmp_path, capsys, leaf, line):
    root, gpath = _repo(tmp_path, {"x-local": 1, "foo": {"bar": 2},
                                   "tracker": "jira"})

    rows = {r["path"]: r for r in menu.plan_delete(root, gpath)["rows"]}
    out = _preview(root, gpath, capsys)

    assert line in out
    assert rows[leaf].get("removed", False) is (leaf != "tracker")


def test_delete_preview_names_platform_as_re_detected(tmp_path, capsys):
    root, gpath = _repo(tmp_path, {"platform.os": "linux",
                                   "platform.shell": "bash", "tracker": "jira"})

    out = _preview(root, gpath, capsys)

    group = out.split("re-detected by platform-sync at the next SessionStart", 1)
    assert len(group) == 2
    assert "platform.os" in group[1] and "platform.os" not in group[0]
    assert "platform.os: \"linux\" -> null" not in out
    assert 'tracker: "jira" -> "files"' in out


_HEADER = "re-detected by platform-sync at the next SessionStart"


@pytest.mark.parametrize("leaf,value,redetected", [
    ("x-local", 1, False), ("distro", "Ubuntu", True), ("os", "linux", True),
], ids=["x-local", "distro", "os"])
def test_delete_preview_platform_rows_follow_the_sync_writer(
        tmp_path, capsys, leaf, value, redetected):
    dotted = "platform." + leaf
    root, gpath = _repo(tmp_path, {dotted: value})
    with open(_config(root), encoding="utf-8") as handle:
        parsed = json.load(handle)

    row = {r["path"]: r for r in menu.delete_preview(root, parsed, gpath)}[dotted]
    before, _, after = _preview(root, gpath, capsys).partition(_HEADER)

    if redetected:
        assert (row.get("redetected"), row.get("removed")) == (True, None)
        assert (dotted in before, dotted in after) == (False, True)
    else:
        assert (row.get("removed"), row.get("redetected")) == (True, None)
        assert f"{dotted}: 1 -> (removed)" in before and dotted not in after


def test_delete_preview_redetected_header_does_not_promise_a_value(tmp_path, capsys):
    root, gpath = _repo(tmp_path, {"platform.os": "linux"})

    out = _preview(root, gpath, capsys)

    header = [line for line in out.splitlines() if _HEADER in line]
    assert len(header) == 1 and "left unset" in header[0]
    assert "written back from this machine" not in out


_WIN_PARTS = ("C:\\Py 3\\python.exe", "C:\\r p\\crew_config_menu.py", "--root",
              "C:\\r p", "restore-repo", "--from",
              "C:\\r p\\.crew\\config.json.bak-X", "--apply")


def test_restore_command_forms():
    posix = ("/usr/bin/python3", "/r p's/m.py", "--root", "/r p's")

    win = menu.command_forms(_WIN_PARTS)
    nix = menu.command_forms(posix)

    assert set(win) == {"sh", "cmd", "powershell"}
    assert nix["sh"] == " ".join(shlex.quote(p) for p in posix)
    assert win["cmd"] == ('"C:/Py 3/python.exe" "C:/r p/crew_config_menu.py" '
                          '"--root" "C:/r p" "restore-repo" "--from" '
                          '"C:/r p/.crew/config.json.bak-X" "--apply"')
    assert "'" not in win["cmd"]
    assert nix["powershell"] == ("& '/usr/bin/python3' '/r p''s/m.py' "
                                 "'--root' '/r p''s'")


def test_restore_lines_warn_about_percent_in_the_cmd_form(tmp_path):
    plain = menu.restore_lines(str(tmp_path / "repo"), str(tmp_path / "b"))
    percent = menu.restore_lines(str(tmp_path / "100% r"), str(tmp_path / "b"))

    assert [ln.split(":", 1)[0] for ln in plain] == [
        "restore (sh)", "restore (cmd)", "restore (PowerShell)"]
    assert any("%" in ln and "warning" in ln for ln in percent)
    assert not any("warning" in ln for ln in plain)


def _restore_form(capsys, name):
    out = capsys.readouterr().out
    return [ln for ln in out.splitlines()
            if ln.startswith(f"restore ({name}): ")][-1].split(": ", 1)[1]


def test_restore_command_runs_in_the_host_shell(tmp_path, capsys):
    root, gpath = _repo(tmp_path / "my repo's", {"tracker": "jira"})
    original = open(_config(root), "rb").read()
    _delete(root, gpath)
    command = _restore_form(capsys, "cmd" if os.name == "nt" else "sh")

    run = subprocess.run(command, shell=True, capture_output=True, text=True,
                         check=False)

    assert run.returncode == 0, run.stderr
    assert open(_config(root), "rb").read() == original


def test_restore_command_runs_in_powershell(tmp_path, capsys):
    pwsh = crew_fixtures.resolve_pwsh()
    if pwsh is None:
        pytest.skip("no pwsh on this machine: the PowerShell form is not run")
    root, gpath = _repo(tmp_path / "my repo's", {"tracker": "jira"})
    original = open(_config(root), "rb").read()
    _delete(root, gpath)
    command = _restore_form(capsys, "PowerShell")

    run = subprocess.run([pwsh, "-NoProfile", "-Command", command],
                         capture_output=True, text=True, check=False)

    assert run.returncode == 0, run.stderr + run.stdout
    assert open(_config(root), "rb").read() == original


def test_delete_prints_all_three_restore_lines(tmp_path, capsys):
    root, gpath = _repo(tmp_path / "my repo's")

    _delete(root, gpath)

    out = capsys.readouterr().out
    cmd = [ln for ln in out.splitlines() if ln.startswith("restore (cmd): ")]
    assert [n for n in ("sh", "cmd", "PowerShell")
            if f"restore ({n}): " in out] == ["sh", "cmd", "PowerShell"]
    # The path holds an apostrophe on purpose: the cmd line double-quotes each
    # part, where POSIX quoting would open with ' and escape it as '"'"'.
    cmd_line = cmd[0].split(": ", 1)[1]
    assert cmd_line.startswith('"') and "'\"'\"'" not in cmd_line


def test_delete_preview_names_what_changes(tmp_path, capsys):
    root, gpath = _repo(tmp_path,
                        {"scope.mode": "block", "guards.forcePush": "block",
                         "guards.roleWrites": "block", "tracker": "jira"},
                        {"guards": {"forcePush": "allow", "roleWrites": "off"}})

    menu.delete_repo_config(root, None, False, now=_now(), global_path=gpath)

    out = capsys.readouterr().out
    assert "scope.mode: \"block\" -> \"off\"  !" in out
    assert "guards.roleWrites: \"block\" -> \"off\"  !" in out
    assert "tracker: \"jira\" -> \"files\"" in out
    # The ratchet, not precedence: an absent repo value is the floor, so
    # deleting a repo `block` under a machine `allow` stays `block` -- named
    # as held, never as a `->` change.
    assert "guards.forcePush: \"block\" ->" not in out
    assert "guards.forcePush: stays \"block\"" in out
    assert "isCrew" in out and "platform-sync" in out


@pytest.mark.parametrize("machine,named", [("allow", True), ("block", False)])
def test_delete_preview_names_a_guard_the_ratchet_holds(tmp_path, capsys,
                                                        machine, named):
    root, gpath = _repo(tmp_path, {"guards.forcePush": "block"},
                        {"guards": {"forcePush": machine}})

    menu.delete_repo_config(root, None, False, now=_now(), global_path=gpath)

    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if "guards.forcePush" in ln]
    assert [("stays" in ln, "!" in ln) for ln in lines] == (
        [(True, False)] if named else [])


def test_delete_really_does_not_widen_a_held_guard(tmp_path):
    root, gpath = _repo(tmp_path, {"guards.forcePush": "block"},
                        {"guards": {"forcePush": "allow"}})

    before = crew_config.resolve_guard(root, "forcePush", gpath)["effective"]
    _delete(root, gpath)
    gap = crew_config.resolve_guard(root, "forcePush", gpath)["effective"]
    crew_platform.heal_config(root)
    after = crew_config.resolve_guard(root, "forcePush", gpath)["effective"]

    assert (before, gap, after) == ("block", "block", "block")


def test_delete_leaves_crew_json(tmp_path):
    root, gpath = _repo(tmp_path)
    crew_json = os.path.join(root, ".crew", "crew.json")
    with open(crew_json, "w", encoding="utf-8") as handle:
        handle.write('{"x": 1}')

    _delete(root, gpath)

    assert open(crew_json, encoding="utf-8").read() == '{"x": 1}'


def test_restore_backs_up_a_healed_default_first(tmp_path):
    root, gpath = _repo(tmp_path, {"tracker": "jira"})
    original = open(_config(root), "rb").read()
    _delete(root, gpath)
    crew_platform.heal_config(root)
    healed = open(_config(root), "rb").read()
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")

    code = menu.restore_repo_config(root, backup, True, now=_now())

    assert (code, open(_config(root), "rb").read()) == (0, original)
    saved = os.path.join(root, ".crew", f"config.json.bak-{_TS}-2")
    assert open(saved, "rb").read() == healed


@pytest.mark.parametrize("where", ["outside", "badname", "notjson", "empty"])
def test_restore_refuses_a_non_backup_path(tmp_path, where):
    root, _ = _repo(tmp_path)
    before = open(_config(root), "rb").read()
    crew_dir = os.path.join(root, ".crew")
    path = {"outside": str(tmp_path / f"config.json.bak-{_TS}"),
            "badname": os.path.join(crew_dir, "verify.json"),
            "notjson": os.path.join(crew_dir, f"config.json.bak-{_TS}"),
            "empty": os.path.join(crew_dir, f"config.json.bak-{_TS}")}[where]
    body = {"outside": '{"tracker": "x"}', "badname": '{"tracker": "x"}',
            "notjson": "{nope", "empty": "{}"}[where]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)

    code = menu.restore_repo_config(root, path, True, now=_now())

    assert (code, open(_config(root), "rb").read()) == (2, before)


def test_repo_name_is_the_checkout_basename(tmp_path):
    root, _ = _repo(tmp_path)

    assert menu.repo_name(root) == "repo"


def test_repo_name_is_the_git_toplevel_basename(tmp_path):
    outer = tmp_path / "outer"
    nested = outer / "tools" / "sub"
    (nested / ".crew").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(outer)], check=True)

    assert menu.repo_name(str(nested)) == "outer"


def test_repo_name_falls_back_without_git(tmp_path, monkeypatch):
    root, _ = _repo(tmp_path)
    monkeypatch.setenv("PATH", "")

    assert menu.repo_name(root) == "repo"


def test_delete_cli_needs_the_typed_name(tmp_path, capsys):
    root, gpath = _repo(tmp_path)

    code = menu.main(["--root", root, "--global-path", gpath, "delete-repo",
                      "--apply"])

    assert code == 2
    assert "--confirm repo" in capsys.readouterr().err
    assert os.path.exists(_config(root))


def test_spec_cli_prints_json(tmp_path, capsys):
    root, gpath = _repo(tmp_path)

    code = menu.main(["--root", root, "--global-path", gpath, "spec",
                      "--layer", "repo", "--area", "guards", "--json"])

    spec = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [a["id"] for a in spec["areas"]] == ["guards"]


def test_script_runs_standalone(tmp_path):
    root, gpath = _repo(tmp_path)
    script = os.path.join(_PLUGIN, "hooks", "scripts", "crew_config_menu.py")

    run = subprocess.run([sys.executable, script, "--root", root,
                          "--global-path", gpath, "spec", "--layer", "machine"],
                         capture_output=True, text=True, check=False)

    assert run.returncode == 0, run.stderr
    assert "pm.authority" in run.stdout


# --- Step 7: the commands and the procedure ---------------------------------


def _read(*parts):
    with open(os.path.join(_PLUGIN, *parts), encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    return " ".join(text.split())


def _frontmatter_tools(text):
    head = text.split("---", 2)[1]
    line = [ln for ln in head.splitlines() if ln.startswith("allowed-tools:")][0]
    return {tool.strip() for tool in line.split(":", 1)[1].split(",")}


@pytest.mark.parametrize("name", ["config.md", "config-setup.md"])
def test_both_commands_follow_the_menu_procedure(name):
    text = _read("commands", name)

    assert "skills/crew-setup/config-menu.md" in text
    assert "AskUserQuestion" in _frontmatter_tools(text)


def test_menu_procedure_names_page_size_and_other_escape():
    text = _flat(_read("skills", "crew-setup", "config-menu.md"))

    assert "3 choices per page plus More" in text
    assert "Other is an escape and is never required" in text


def test_menu_procedure_requires_save_and_typed_delete():
    text = _flat(_read("skills", "crew-setup", "config-menu.md"))

    assert "save --changes" in text
    assert "only after the dry run has been shown" in text
    assert "delete-repo --confirm" in text
    assert text.index("save --changes") < text.index("--apply")
    assert "--expect-machine" in text and "--expect-repo" in text
    assert text.index("digest") < text.index("--expect-repo")
    assert "delete-repo --confirm <name> --apply --expect-repo <digest>" in text


def test_menu_procedure_prints_three_restore_forms():
    text = _flat(_read("skills", "crew-setup", "config-menu.md"))

    assert all(f"restore ({n})" in text for n in ("sh", "cmd", "PowerShell"))
    assert "the one that matches the owner's shell" in text


def test_menu_procedure_names_blocked_rows():
    text = _flat(_read("skills", "crew-setup", "config-menu.md"))

    assert "refusedReason" in text and "--pending" in text
    assert "fix the key it names first" in text


def test_menu_procedure_headless_fallback():
    text = _flat(_read("skills", "crew-setup", "config-menu.md"))

    assert "Headless" in text
    assert "crew_config_menu.py --root . spec" in text
    assert "Nothing is applied from a default" in text


def test_config_md_no_longer_claims_it_never_writes_the_repo_file():
    text = _flat(_read("commands", "config.md"))

    assert "it does not write `.crew/config.json`" not in text
    assert "--set" in text and "--repo" in text


# --- T-0075 successor: digests on Save ---------------------------------------


def test_save_dry_run_prints_both_digests(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "report-only"}})
    digests = (crew_config_files.digest(open(gpath, "rb").read()),
               crew_config_files.digest(open(_config(root), "rb").read()))

    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=False, global_path=gpath)

    out = capsys.readouterr().out
    assert code == 0
    assert f"machine digest: {digests[0]}" in out
    assert f"repo digest: {digests[1]}" in out


def test_save_apply_refuses_when_a_layer_changed_since_the_dry_run(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "report-only"}})
    good = crew_config_files.digest(open(gpath, "rb").read())
    before = (open(gpath, "rb").read(), open(_config(root), "rb").read())

    code = menu.save(root, {"machine": _MACHINE_SET, "repo": _REPO_SET},
                     apply=True, global_path=gpath,
                     expect={"machine": good, "repo": "0" * 64})

    err = capsys.readouterr().err
    assert code == 2
    assert "repo layer" in err and "changed since" in err
    assert (open(gpath, "rb").read(), open(_config(root), "rb").read()) == before


def test_save_apply_without_expect_still_merges_inside_the_lock(tmp_path):
    root, gpath = _repo(tmp_path)
    data = json.loads(open(_config(root), encoding="utf-8").read())
    data["x-other"] = 1
    with open(_config(root), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))

    code = menu.save(root, {"repo": {"tracker": "sdp"}}, apply=True,
                     global_path=gpath)

    written = json.loads(open(_config(root), encoding="utf-8").read())
    assert (code, written["x-other"], written["tracker"]) == (0, 1, "sdp")


def test_save_cli_passes_the_expected_digests(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    code = menu.main(["--root", root, "--global-path", gpath, "save",
                      "--changes", json.dumps({"repo": {"tracker": "sdp"}}),
                      "--apply", "--expect-repo", "f" * 64])

    assert code == 2, capsys.readouterr()
    assert open(_config(root), "rb").read() == before


# --- T-0075 successor: CLI shape validation, never a traceback --------------

_MALFORMED = [
    ("save-machine-1", ["save", "--changes", '{"machine":1}'], "machine"),
    ("save-machine-list", ["save", "--changes", '{"machine":[]}'], "machine"),
    ("save-empty-key", ["save", "--changes", '{"repo":{"":1}}'], "not a dotted path"),
    ("save-a..b", ["save", "--changes", '{"repo":{"a..b":1}}'],
     "not a dotted path"),
    ("save-leading-dot", ["save", "--changes", '{"repo":{".a":1}}'],
     "not a dotted path"),
    ("save-other-layer", ["save", "--changes", '{"other":{}}'], "other"),
    ("save-array", ["save", "--changes", "[]"], "object"),
    ("save-string", ["save", "--changes", '"x"'], "object"),
    ("save-notjson", ["save", "--changes", "{not json"], "JSON"),
    ("spec-pending-1", ["spec", "--layer", "repo", "--pending", '{"repo":1}'],
     "repo"),
    ("spec-pending-array", ["spec", "--layer", "repo", "--pending", "[]"],
     "object"),
    ("save-expect-zz", ["save", "--changes", "{}", "--expect-repo", "zz"],
     "--expect-repo"),
    ("delete-empty-confirm", ["delete-repo", "--confirm", ""], "--confirm"),
    ("restore-empty-from", ["restore-repo", "--from", ""], "--from"),
]


@pytest.mark.parametrize("argv,needle", [(a, n) for _i, a, n in _MALFORMED],
                         ids=[i for i, _a, _n in _MALFORMED])
def test_cli_refuses_malformed_input_with_exit_2(tmp_path, capsys, argv, needle):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    code = menu.main(["--root", root, "--global-path", gpath] + argv)

    assert code == 2
    assert needle in capsys.readouterr().err
    assert open(_config(root), "rb").read() == before


@pytest.mark.parametrize("argv", [
    ["save", "--changes", '{"machine":1}', "--apply"],
    ["spec", "--layer", "machine", "--pending", '{"machine":[1]}'],
    ["delete-repo", "--confirm", "", "--apply"],
    ["restore-repo", "--from", "", "--apply"],
], ids=["save", "spec", "delete-repo", "restore-repo"])
def test_cli_subprocess_prints_no_traceback(tmp_path, argv):
    root, gpath = _repo(tmp_path)
    script = os.path.join(_PLUGIN, "hooks", "scripts", "crew_config_menu.py")

    run = subprocess.run([sys.executable, script, "--root", root,
                          "--global-path", gpath] + argv,
                         capture_output=True, text=True, check=False)

    assert (run.returncode, "Traceback" in run.stderr) == (2, False), run.stderr


# --- Review round 3 (T-0075): bound to what the owner reviewed ---------------


def _digest_line(out, label):
    line = [ln for ln in out.splitlines() if ln.startswith(f"{label} digest: ")]
    return line[-1].split(": ", 1)[1]


def test_repo_only_save_prints_the_machine_digest(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={"guards": {"forcePush": "block"}})

    menu.save(root, {"repo": {"tracker": "sdp"}}, apply=False, global_path=gpath)

    out = capsys.readouterr().out
    assert _digest_line(out, "machine") == crew_config_files.digest(
        open(gpath, "rb").read())


def test_repo_only_save_refuses_when_the_machine_file_changed(tmp_path, capsys):
    root, gpath = _repo(tmp_path, {"guards.forcePush": "block"},
                        {"guards": {"forcePush": "block"}})
    menu.save(root, {"repo": {"guards.forcePush": "allow"}}, apply=False,
              global_path=gpath)
    out = capsys.readouterr().out
    reviewed = {"machine": _digest_line(out, "machine"),
                "repo": _digest_line(out, "repo")}
    with open(gpath, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"guards": {"forcePush": "allow"}}))
    before = open(_config(root), "rb").read()

    code = menu.save(root, {"repo": {"guards.forcePush": "allow"}}, apply=True,
                     global_path=gpath, expect=reviewed)

    assert code == 2
    assert "machine layer" in capsys.readouterr().err
    assert open(_config(root), "rb").read() == before


def test_repo_only_save_passes_the_machine_digest_to_the_writer(tmp_path,
                                                                monkeypatch):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    machine = crew_config_files.digest(open(gpath, "rb").read())
    seen = {}
    real = crew_config.write_repo_config

    def _spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)
    monkeypatch.setattr(menu.crew_config, "write_repo_config", _spy)

    code = menu.save(root, {"repo": {"tracker": "sdp"}}, apply=True,
                     global_path=gpath, expect={"machine": machine})

    assert (code, seen.get("expect_global")) == (0, machine)


def test_two_layer_save_binds_the_repo_write_to_the_machine_it_wrote(tmp_path,
                                                                    capsys):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "report-only"}})
    changes = {"machine": _MACHINE_SET, "repo": _REPO_SET}
    menu.save(root, changes, apply=False, global_path=gpath)
    out = capsys.readouterr().out
    reviewed = {"machine": _digest_line(out, "machine"),
                "repo": _digest_line(out, "repo")}

    code = menu.save(root, changes, apply=True, global_path=gpath,
                     expect=reviewed)

    written = json.loads(open(_config(root), encoding="utf-8").read())
    assert (code, written["tracker"]) == (0, "jira"), capsys.readouterr().err


def test_two_layer_save_judges_the_repo_against_the_saved_machine(tmp_path,
                                                                  capsys):
    root, gpath = _repo(tmp_path, {"guards.forcePush": "ask"},
                        {"guards": {"forcePush": "allow"}})

    menu.save(root, {"machine": {"guards.forcePush": "block"},
                     "repo": {"guards.forcePush": "allow"}},
              apply=False, global_path=gpath)

    repo_part = capsys.readouterr().out.split("repo layer - ", 1)[1]
    assert "held down by the machine-global layer" in repo_part


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_save_dry_run_names_an_absent_machine_file(tmp_path, capsys, layer):
    root, gpath = _repo(tmp_path)
    changes = ({"machine": {"pm.authority": "act"}} if layer == "machine"
               else {"repo": {"tracker": "sdp"}})

    menu.save(root, changes, apply=False, global_path=gpath)

    assert _digest_line(capsys.readouterr().out, "machine") == "absent"


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_save_compares_against_an_absent_machine_file(tmp_path, capsys, layer):
    root, gpath = _repo(tmp_path)
    changes = ({"machine": {"pm.authority": "act"}} if layer == "machine"
               else {"repo": {"tracker": "sdp"}})
    with open(gpath, "w", encoding="utf-8") as handle:
        handle.write('{"x-other": 1}')
    before = (open(gpath, "rb").read(), open(_config(root), "rb").read())

    code = menu.save(root, changes, apply=True, global_path=gpath,
                     expect={"machine": "absent"})

    assert code == 2, capsys.readouterr()
    assert (open(gpath, "rb").read(), open(_config(root), "rb").read()) == before


def test_save_passes_an_absent_expectation_to_the_machine_writer(tmp_path,
                                                                 monkeypatch):
    root, gpath = _repo(tmp_path)
    seen = {}
    real = crew_config.write_global_config

    def _spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)
    monkeypatch.setattr(menu.crew_config, "write_global_config", _spy)

    code = menu.save(root, {"machine": {"pm.authority": "act"}}, apply=True,
                     global_path=gpath, expect={"machine": "absent"})

    assert (code, seen.get("expect")) == (0, "absent")


def test_save_cli_takes_absent_as_an_expectation(tmp_path, capsys):
    root, gpath = _repo(tmp_path)

    code = menu.main(["--root", root, "--global-path", gpath, "save",
                      "--changes", '{"machine": {"pm.authority": "act"}}',
                      "--apply", "--expect-machine", "absent"])

    assert code == 0, capsys.readouterr().err
    assert json.loads(open(gpath, encoding="utf-8").read())["pm"] == {
        "authority": "act"}


def test_delete_preview_prints_both_digests(tmp_path, capsys):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})

    out = _preview(root, gpath, capsys)

    assert (_digest_line(out, "repo"), _digest_line(out, "machine")) == (
        crew_config_files.digest(open(_config(root), "rb").read()),
        crew_config_files.digest(open(gpath, "rb").read()))


@pytest.mark.parametrize("expect", [None, "stale-repo", "stale-machine",
                                    "no-machine"])
def test_delete_apply_is_bound_to_the_preview(tmp_path, capsys, expect):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    plan = menu.plan_delete(root, gpath)
    reviewed = {"repo": plan["digest"], "machine": plan["machine"]}
    if expect == "stale-repo":
        reviewed["repo"] = "0" * 64
    elif expect == "stale-machine":
        reviewed["machine"] = "absent"
    elif expect == "no-machine":
        del reviewed["machine"]
    before = open(_config(root), "rb").read()

    code = menu.delete_repo_config(root, "repo", True, now=_now(),
                                   global_path=gpath,
                                   expect=None if expect is None else reviewed)

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (
        2, before, [])
    assert "preview" in capsys.readouterr().err


def _record_locks(monkeypatch):
    taken = []
    real_enter = crew_config_files.Lock.__enter__

    def _enter(self):
        taken.append(self.path)
        return real_enter(self)
    monkeypatch.setattr(crew_config_files.Lock, "__enter__", _enter)
    return taken


def _bound(plan):
    return {"repo": plan["digest"], "machine": plan["machine"]}


def test_delete_rechecks_the_machine_file_inside_the_locks(tmp_path, capsys,
                                                           monkeypatch):
    root, gpath = _repo(tmp_path, {"guards.forcePush": "block"},
                        global_cfg={"guards": {"forcePush": "block"}})
    plan = menu.plan_delete(root, gpath)
    before = open(_config(root), "rb").read()
    real_unbound = menu._unbound  # pylint: disable=protected-access

    def _unbound_then_a_machine_write(*args):
        got = real_unbound(*args)
        with open(gpath, "w", encoding="utf-8") as handle:
            json.dump({"guards": {"forcePush": "allow"}}, handle)
        return got
    monkeypatch.setattr(menu, "_unbound", _unbound_then_a_machine_write)

    code = menu.apply_delete(root, plan, "repo", now=_now(), expect=_bound(plan))

    err = capsys.readouterr().err
    assert (code, open(_config(root), "rb").read(), _backups(root)) == (
        2, before, [])
    assert "changed since the preview" in err and gpath in err


def test_delete_refuses_while_the_machine_lock_is_held(tmp_path, capsys,
                                                       monkeypatch):
    monkeypatch.setattr(crew_config_files, "LOCK_WAIT_SECONDS", 0.1)
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    before = open(_config(root), "rb").read()
    with open(gpath + ".lock", "w", encoding="utf-8") as handle:
        handle.write("4242")

    code = _delete(root, gpath)

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (
        2, before, [])
    assert gpath + ".lock" in capsys.readouterr().err


def _deny_lock_files(monkeypatch):
    real_open = crew_config_files.os.open

    def _open(path, *args, **kwargs):
        if str(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(crew_config_files.os, "open", _open)


def test_delete_refuses_when_the_machine_lock_cannot_be_created(tmp_path, capsys,
                                                                monkeypatch):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    before = open(_config(root), "rb").read()
    plan = menu.plan_delete(root, gpath)
    _deny_lock_files(monkeypatch)

    code = menu.apply_delete(root, plan, "repo", now=_now(),
                             expect={"repo": plan["digest"], "machine": plan["machine"]})

    assert (code, open(_config(root), "rb").read(), _backups(root)) == (
        2, before, [])
    assert gpath + ".lock" in capsys.readouterr().err


def test_restore_refuses_when_the_lock_cannot_be_created(tmp_path, capsys,
                                                         monkeypatch):
    root, gpath = _repo(tmp_path, {"tracker": "jira"})
    _delete(root, gpath)
    crew_platform.heal_config(root)
    healed = open(_config(root), "rb").read()
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    capsys.readouterr()
    _deny_lock_files(monkeypatch)

    code = menu.restore_repo_config(root, backup, True, now=_now())

    assert (code, open(_config(root), "rb").read()) == (2, healed)
    assert "config.json.lock" in capsys.readouterr().err


def test_save_reports_an_os_failure_without_a_traceback(tmp_path, capsys,
                                                        monkeypatch):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()
    _deny_lock_files(monkeypatch)

    code = menu.save(root, {"repo": {"tracker": "jira"}}, apply=True,
                     global_path=gpath)

    err = capsys.readouterr().err
    assert (code, "repo layer: NOT written" in err, "nothing was written" in err,
            ".json.lock" in err) == (1, True, True, True)
    assert open(_config(root), "rb").read() == before


def test_delete_takes_the_machine_lock_before_the_repo_lock(tmp_path, capsys,
                                                            monkeypatch):
    root, gpath = _repo(tmp_path, global_cfg={"pm": {"authority": "act"}})
    taken = _record_locks(monkeypatch)

    code = _delete(root, gpath)

    capsys.readouterr()
    assert code == 0
    assert taken[:2] == [gpath + ".lock", _config(root) + ".lock"]


def test_delete_takes_the_machine_lock_when_its_directory_is_absent(
        tmp_path, capsys, monkeypatch):
    root, _ = _repo(tmp_path)
    gpath = str(tmp_path / "no-such-dir" / "config.json")
    plan = menu.plan_delete(root, gpath)
    taken = _record_locks(monkeypatch)

    code = menu.apply_delete(root, plan, "repo", now=_now(), expect=_bound(plan))

    capsys.readouterr()
    assert (plan["machine"], code) == ("absent", 0)
    assert gpath + ".lock" in taken
    assert os.path.isdir(os.path.dirname(gpath)) and not os.path.lexists(gpath)
    leftovers = [n for d in (os.path.dirname(gpath), os.path.join(root, ".crew"))
                 for n in os.listdir(d) if n.endswith(".lock")]
    assert leftovers == []


def test_delete_cli_apply_needs_the_preview_digests(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    base = ["--root", root, "--global-path", gpath, "delete-repo",
            "--confirm", "repo"]
    menu.main(base)
    out = capsys.readouterr().out

    unbound = menu.main(base + ["--apply"])
    unbound_err = capsys.readouterr().err
    bound = menu.main(base + ["--apply", "--expect-repo",
                              _digest_line(out, "repo"), "--expect-machine",
                              _digest_line(out, "machine")])

    assert (unbound, bound) == (2, 0)
    assert "--expect-repo" in unbound_err
    assert not os.path.exists(_config(root))


def test_delete_rollback_never_replaces_a_file_saved_in_the_gap(
        tmp_path, capsys, monkeypatch):
    root, gpath = _repo(tmp_path)
    plan = menu.plan_delete(root, gpath)
    changed = b'{"tracker": "sdp"}\n'
    foreign = b'{"tracker": "jira", "saved": "in the gap"}\n'
    _write_config(root, changed)
    real_move = crew_config_files.move_aside

    def _move_then_a_foreign_save(src, dest):
        got = real_move(src, dest)
        with open(src, "wb") as handle:
            handle.write(foreign)
        return got
    monkeypatch.setattr(crew_config_files, "move_aside", _move_then_a_foreign_save)
    monkeypatch.setattr(menu.os.path, "lexists", lambda _p: False)

    code = menu.apply_delete(root, plan, "repo", now=_now(), expect={
        "repo": plan["digest"], "machine": plan["machine"]})

    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    assert (code, open(_config(root), "rb").read(), open(backup, "rb").read()) == (
        1, foreign, changed)
    assert backup in capsys.readouterr().err


def _two_foreign_saves(root, monkeypatch):
    """Wrap `os.link` as crew_config_files calls it: after the link to a
    `.bak-` name another writer saves F1 over the config, and after the link
    that puts F1 back it saves F2 over it (review round 4's BLOCK 2)."""
    path = _config(root)
    real_link = os.link

    def _save(data):
        sibling = path + ".foreign.tmp"
        with open(sibling, "wb") as handle:
            handle.write(data)
        os.replace(sibling, path)

    def _link(src, dst, **kwargs):
        real_link(src, dst, **kwargs)
        if ".bak-" in os.path.basename(dst):
            _save(b'{"F1": 1}\n')
        elif dst == path:
            _save(b'{"F2": 1}\n')
    monkeypatch.setattr(crew_config_files.os, "link", _link)


def _moving(root):
    crew_dir = os.path.join(root, ".crew")
    return [os.path.join(crew_dir, n) for n in os.listdir(crew_dir)
            if n.endswith(".moving")]


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_delete_reports_a_foreign_file_kept_during_the_move(
        tmp_path, capsys, monkeypatch):
    root, gpath = _repo(tmp_path)
    original = open(_config(root), "rb").read()
    plan = menu.plan_delete(root, gpath)
    _two_foreign_saves(root, monkeypatch)

    code = menu.delete_repo_config(root, "repo", True, now=_now(),
                                   global_path=gpath, expect={
                                       "repo": plan["digest"],
                                       "machine": plan["machine"]})

    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    err = capsys.readouterr().err
    kept = _moving(root)
    assert (code, open(backup, "rb").read(), open(_config(root), "rb").read()) == (
        1, original, b'{"F2": 1}\n')
    assert [open(k, "rb").read() for k in kept] == [b'{"F1": 1}\n']
    assert backup in err and kept[0] in err


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_restore_reports_a_foreign_file_kept_during_its_move_aside(
        tmp_path, capsys, monkeypatch):
    root, _ = _repo(tmp_path, {"tracker": "jira"})
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}-old")
    with open(backup, "wb") as handle:
        handle.write(b'{"tracker": "sdp"}\n')
    _two_foreign_saves(root, monkeypatch)

    code = menu.restore_repo_config(root, backup, True, now=_now())

    err = capsys.readouterr().err
    kept = _moving(root)
    assert (code, open(_config(root), "rb").read()) == (1, b'{"F2": 1}\n')
    assert [open(k, "rb").read() for k in kept] == [b'{"F1": 1}\n']
    assert kept[0] in err


@pytest.mark.skipif(os.name == "nt", reason="needs a POSIX symlink")
def test_delete_refuses_a_symlinked_config(tmp_path, capsys):
    root, gpath = _repo(tmp_path)
    real = os.path.join(root, ".crew", "real-config.json")
    os.replace(_config(root), real)
    os.symlink(real, _config(root))

    code = _delete(root, gpath)

    assert (code, os.path.islink(_config(root)), _backups(root)) == (2, True, [])
    assert "not a regular file" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="needs a POSIX symlink")
def test_restore_refuses_a_symlinked_backup(tmp_path, capsys):
    root, _ = _repo(tmp_path)
    before = open(_config(root), "rb").read()
    target = os.path.join(root, ".crew", f"config.json.bak-{_TS}-real")
    with open(target, "wb") as handle:
        handle.write(b'{"tracker": "jira"}\n')
    link = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    os.symlink(target, link)

    code = menu.restore_repo_config(root, link, True, now=_now())

    assert (code, open(_config(root), "rb").read()) == (2, before)
    assert "not a regular file" in capsys.readouterr().err


def test_restore_never_replaces_a_file_that_appears_after_the_move_aside(
        tmp_path, capsys, monkeypatch):
    root, gpath = _repo(tmp_path, {"tracker": "jira"})
    _delete(root, gpath)
    crew_platform.heal_config(root)
    backup = os.path.join(root, ".crew", f"config.json.bak-{_TS}")
    healed_again = b'{"tracker": "files", "healed": "again"}\n'
    real_move = crew_config_files.move_aside

    def _aside_then_heal(src, dest):
        got = real_move(src, dest)
        with open(src, "wb") as handle:
            handle.write(healed_again)
        return got
    monkeypatch.setattr(crew_config_files, "move_aside", _aside_then_heal)
    capsys.readouterr()

    code = menu.restore_repo_config(root, backup, True, now=_now())

    assert (code, open(_config(root), "rb").read()) == (2, healed_again)


@pytest.mark.parametrize("argv,needle", [
    (["spec", "--layer", "repo", "--pending", ""], "--pending"),
    (["spec", "--layer", "repo", "--area", ""], "area"),
    (["delete-repo", "--expect-repo", "zz"], "--expect-repo"),
    (["delete-repo", "--expect-machine", ""], "--expect-machine"),
], ids=["pending-empty", "area-empty", "delete-expect-zz",
        "delete-expect-empty"])
def test_cli_refuses_an_explicitly_empty_value(tmp_path, capsys, argv, needle):
    root, gpath = _repo(tmp_path)
    before = open(_config(root), "rb").read()

    code = menu.main(["--root", root, "--global-path", gpath] + argv)

    assert code == 2
    assert needle in capsys.readouterr().err
    assert open(_config(root), "rb").read() == before


def test_sleep_overrides_offer_the_three_policies_and_unset(tmp_path):
    """T-0053: `autopilot.sleep.approval` / `.questions` are repo-only and
    offer human, self, risk and unset (null, "not overridden")."""
    root, gpath = _repo(tmp_path)
    rows = {r["path"]: r for r in _rows(menu.menu_spec(root, "repo", gpath))}

    for path in ("autopilot.sleep.approval", "autopilot.sleep.questions"):
        assert (rows[path]["writable"],
                sorted(map(repr, (c["value"] for c in rows[path]["choices"])))) == (
            True, sorted(map(repr, ("human", "self", "risk", None)))), path
