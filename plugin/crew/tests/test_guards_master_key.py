"""`guards.enabled`, the guards master switch's key (crew 1.3.95): declared, validated, written only through the
owner's double confirmation, and judged by every planner that writes a whole file.

The hook half (`crew_hook.guards_switched_off`, the receipt it requires, context-watch standing down, the duplicate
key and redirected-HOME rules, the scope guard's protection of the machine file) is held by `test_guards_master.py`.
This file holds the key/writer half:

* both default layers carry the key, and the machine writer takes only the JSON booleans;
* `false` is never a plain write: the writers refuse it at both layers and `crew_confirm_config` proposes it
  (machine layer only), the owner types `/crew:confirm-config` twice, and only then does a `false` count;
* the whole-file planners (`--rebuild`, `--restore`, `/crew:migrate`) judge the key themselves, with a bad-value
  list that includes `None`, because they take their content from a profile, a backup or the file, not from one
  validated `--set`;
* `--explain` and `--inert` report any repo copy but the default `true` (a `null` included) as ignored, and say
  so as JSON (`false`, not Python's `False`);
* `/crew:status` says unconfirmed, ignored and DISABLED correctly.

`guards_master_key_mutations.py` holds one mutation per rule; `test_every_mutation_anchor_is_present_exactly_once`
keeps its anchors honest until a harness-only PR wires it into `sabotage.py`.
"""
import json
import os
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_backup
import crew_config
import crew_confirm_config
import crew_humanonly
import crew_keys
import crew_migrate
import crew_state
import crew_status

KEY = "guards.enabled"
# Everything a repo file may NOT carry at the key: only `true` (the template's own value) or absent is allowed.
REPO_BAD = [False, None, "false", "true", "off", 0, 1, [], {}]
# Everything the machine file may not carry through a whole-file replacement: not a boolean, or a `false` nobody
# confirmed. (`False` alone is judged against the file being replaced.)
MACHINE_BAD = [None, "false", "true", "off", 0, 1, [], {}]


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    """A scratch machine: HOME, the machine config path and the backup store all under `tmp_path`."""
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    path = home / ".claude" / "crew" / "config.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    return home


def _gpath(home):
    return str(home / ".claude" / "crew" / "config.json")


def _repo(tmp_path, cfg, name="repo"):
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(root)


def _machine(home, cfg):
    path = _gpath(home)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(cfg))
    return path


def _receipt(path, state="applied", value=False, settled=None):
    """The record `crew_confirm_config.confirm` leaves behind (crew 1.3.95): two typed-prompt confirmations and
    `appliedDigest`, the canonical digest of the file as applied."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    record = {"change_id": crew_humanonly.new_change_id(), "layer": "machine",
              "target": crew_humanonly.target_key(path), "key": KEY, "value": value, "state": state,
              "created": time.time(), "settled": time.time() if settled is None else settled,
              "confirmations": [{"at": 1, "via": "user-prompt", "prompt": f"p{n}", "session": None}
                                for n in (1, 2)],
              "appliedDigest": crew_hook.canonical_digest(path), "reason": "test"}
    crew_humanonly.write_record(crew_humanonly.store_dir(path), record)


def _confirm_twice(gpath, now=0):
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=now)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=now + 1)
    return crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=now + 2)


def _stamp_of(path, content):
    """A backup stamp of `path` holding `content` (any JSON), the file left as `{}`."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(content))
    stamp = crew_backup.backup(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{}")
    return stamp


# --- the key and its values ----------------------------------------------------------------------------------

def test_the_key_is_declared_true_in_both_default_layers():
    assert crew_config.default_config()["guards"]["enabled"] is True
    assert crew_config.default_global_config()["guards"]["enabled"] is True
    assert crew_config.is_global_path(KEY)
    assert crew_keys.KEY_META[KEY]["values"] == (True, False)


def test_the_key_is_machine_only_in_the_key_table():
    assert crew_keys.layer_of(KEY) == "machine-only"


def test_the_hook_and_the_writer_name_the_same_key():
    """`crew_hook.MASTER_KEY` and `approval_hook.MASTER_KEY` are spelled in the harness files; they must not drift."""
    import approval_hook  # pylint: disable=import-outside-toplevel
    import crew_hook  # pylint: disable=import-outside-toplevel
    assert crew_hook.MASTER_KEY == approval_hook.MASTER_KEY == crew_humanonly.MASTER_KEY == KEY
    assert KEY in crew_humanonly.CONFIRMED_PATHS and not crew_humanonly.is_path(KEY)


def test_the_machine_writer_takes_true_and_refuses_false_and_the_rest():
    assert crew_config.value_allowed(KEY, "machine", True) is None
    refused = crew_config.value_allowed(KEY, "machine", False)
    assert refused is not None and "double confirmation" in refused
    for bad in ("false", "off", 0, 1, None, [], {}):
        assert crew_config.value_allowed(KEY, "machine", bad) is not None, bad


@pytest.mark.parametrize("value", [True, False, None, "false"])
def test_the_repo_writer_refuses_the_key(value):
    """Owner decision 2026-11-13: only the machine layer counts, so a repo file may not hold the key."""
    reason = crew_config.value_allowed(KEY, "repo", value)
    assert reason is not None and ("machine" in reason or "double confirmation" in reason), value


def test_removing_the_key_at_the_machine_layer_is_a_plain_write():
    """`--unset` puts the guards back to their default (on), so it needs no confirmation."""
    assert crew_config.unset_allowed(KEY, "machine") is None


def test_write_global_config_refuses_false_and_leaves_the_file(home):
    path = _machine(home, {"guards": {"profile": "off"}})
    before = open(path, encoding="utf-8").read()
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config({KEY: False}, path=path)
    assert open(path, encoding="utf-8").read() == before


# --- the owner's double confirmation ---------------------------------------------------------------------------

def test_two_confirmations_apply_the_machine_switch_and_only_then_does_it_count(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {})
    path = _machine(home, {})
    assert crew_hook.guards_switched_off(root, str(home)) is None
    cid = crew_confirm_config.propose("machine", KEY, global_path=path, now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=path, now=1)
    assert json.load(open(path, encoding="utf-8")).get("guards", {}).get("enabled") is not False
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=path, now=2)
    assert record["state"] == "applied"
    assert json.load(open(path, encoding="utf-8"))["guards"]["enabled"] is False
    assert crew_hook.guards_switched_off(root, str(home)) == "machine"


def test_a_hand_edited_false_does_not_count(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {})
    _machine(home, {"guards": {"enabled": False}})
    assert crew_hook.guards_switched_off(root, str(home)) is None
    assert crew_hook.machine_switch_unconfirmed(root, str(home)) is True


def test_propose_refuses_the_repo_layer_and_a_key_that_needs_none(home, tmp_path):
    root = _repo(tmp_path, {})
    with pytest.raises(crew_confirm_config.Refused) as caught:
        crew_confirm_config.propose("repo", KEY, root=root, global_path=_gpath(home), tracker=lambda _p: "untracked")
    assert "machine" in str(caught.value)
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.propose("machine", "scope.mode", global_path=_gpath(home))


def test_the_proposal_prints_a_warning_the_agent_relays(home, capsys):
    path = _machine(home, {})
    assert crew_confirm_config.main(["propose", "--layer", "machine", "--key", KEY, "--global-path", path]) == 0
    out = capsys.readouterr().out
    assert "Relay the next three lines" in out
    assert "WARNING: guards.enabled: false turns EVERY guard off" in out
    assert "/crew:confirm-config" in out


def test_apply_confirmed_optout_takes_the_machine_switch_only(home):
    path = _machine(home, {})
    with pytest.raises(ValueError):
        crew_config.apply_confirmed_optout("repo", KEY, path, crew_confirm_config.crew_config_files.ABSENT)
    with pytest.raises(ValueError):
        crew_config.apply_confirmed_optout("machine", "scope.mode", path, crew_confirm_config.crew_config_files.ABSENT)


def test_a_crew_write_back_to_true_revokes_the_receipt(home, tmp_path):
    """After a confirmed `false`, a crew write of `true` must retire the receipt: a `false` that reappears by a
    hand edit is not backed by the old confirmation."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {})
    path = _machine(home, {})
    assert _confirm_twice(path)["state"] == "applied"
    assert crew_hook.guards_switched_off(root, str(home)) == "machine"
    crew_config.write_global_config({KEY: True}, path=path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"guards": {"enabled": False}}))
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_removing_the_key_revokes_the_receipt_too(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {})
    path = _machine(home, {})
    _confirm_twice(path)
    crew_config.write_global_config({KEY: crew_config.UNSET}, path=path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"guards": {"enabled": False}}))
    assert crew_hook.guards_switched_off(root, str(home)) is None


# --- the whole-file planners: --rebuild, --restore, /crew:migrate -------------------------------------------

def _write_profile(home, repos=None, global_values=None):
    body = {"schema": 1, "saved_at": "2026-10-01T00:00:00Z",
            "global": {"saved_at": "2026-10-01T00:00:00Z", "values": global_values or {}},
            "repos": repos or {}}
    with open(home / ".claude" / "crew" / "profile.json", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(body))


@pytest.mark.parametrize("value", REPO_BAD)
def test_rebuild_refuses_a_saved_repo_profile_carrying_a_bad_switch(value, home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    _write_profile(home, repos={crew_config.profile_key(root): {
        "saved_at": "2026-10-01T00:00:00Z", "path": root, "values": {KEY: value}}})
    with pytest.raises(crew_config.RebuildRefused) as caught:
        crew_config.plan_rebuild(root, "repo", global_path=_gpath(home))
    assert KEY in str(caught.value)


@pytest.mark.parametrize("value", MACHINE_BAD + [False])
def test_rebuild_refuses_a_saved_machine_profile_carrying_a_bad_switch(value, home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    _machine(home, {})
    _write_profile(home, global_values={KEY: value})
    with pytest.raises(crew_config.RebuildRefused) as caught:
        crew_config.plan_rebuild(root, "machine", global_path=_gpath(home))
    assert KEY in str(caught.value)


def test_rebuild_keeps_a_false_the_machine_file_already_holds(home, tmp_path):
    """A rebuild never INTRODUCES a `false`; one the file already carries (the owner's) is not judged afresh."""
    root = _repo(tmp_path, crew_config.template_config())
    _machine(home, {"guards": {"enabled": False}})
    _write_profile(home, global_values={KEY: False})
    text, _changes, _notes = crew_config.plan_rebuild(root, "machine", global_path=_gpath(home))
    assert json.loads(text)["guards"]["enabled"] is False


def test_rebuild_accepts_the_default_true(home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    _write_profile(home, repos={crew_config.profile_key(root): {
        "saved_at": "x", "path": root, "values": {"tracker": "jira"}}})
    text, _changes, _notes = crew_config.plan_rebuild(root, "repo", global_path=_gpath(home))
    assert json.loads(text)["guards"]["enabled"] is True


@pytest.mark.parametrize("value", REPO_BAD)
def test_restore_refuses_a_repo_backup_carrying_a_bad_switch(value, home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    path = os.path.join(root, ".crew", "config.json")
    stamp = _stamp_of(path, {"guards": {"enabled": value}})
    for force in (False, True):
        with pytest.raises(crew_config.RebuildRefused) as caught:
            crew_config.plan_restore(root, "repo", stamp, global_path=_gpath(home), force_invalid=force)
        assert KEY in str(caught.value)
    with pytest.raises(crew_config.RebuildRefused):
        crew_config.apply_restore(root, "repo", stamp, global_path=_gpath(home))
    assert json.load(open(path, encoding="utf-8")) == {}


@pytest.mark.parametrize("value", MACHINE_BAD + [False])
def test_restore_refuses_a_machine_backup_carrying_a_bad_switch(value, home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    path = _machine(home, {})
    stamp = _stamp_of(path, {"guards": {"enabled": value}})
    with pytest.raises(crew_config.RebuildRefused) as caught:
        crew_config.plan_restore(root, "machine", stamp, global_path=path)
    assert KEY in str(caught.value)


def test_restore_accepts_a_backup_whose_switch_is_true_or_absent(home, tmp_path):
    root = _repo(tmp_path, crew_config.template_config())
    path = _machine(home, {})
    for content in ({"guards": {"enabled": True}}, {"guards": {"profile": "off"}}):
        stamp = _stamp_of(path, content)
        data, changes = crew_config.plan_restore(root, "machine", stamp, global_path=path)
        assert json.loads(data) == content and changes is not None


@pytest.mark.parametrize("value", MACHINE_BAD)
def test_migrate_refuses_to_carry_a_bad_switch_through(value, home):
    path = _machine(home, {"guards": {"enabled": value}})
    plan = crew_migrate.build_global_plan(path)
    assert plan["writes"] == []
    assert any(KEY in conflict for conflict in plan["conflicts"]), plan["conflicts"]


@pytest.mark.parametrize("value", MACHINE_BAD)
def test_migrate_refuses_even_when_it_would_rewrite_the_file_for_another_reason(value, home):
    path = _machine(home, {"cloudGuard": "block", "guards": {"enabled": value}})
    plan = crew_migrate.build_global_plan(path)
    assert plan["writes"] == []
    assert any(KEY in conflict for conflict in plan["conflicts"]), plan


def test_migrate_leaves_a_boolean_switch_alone(home):
    for value in (True, False):
        path = _machine(home, {"guards": {"enabled": value}})
        plan = crew_migrate.build_global_plan(path)
        assert not any(KEY in conflict for conflict in plan["conflicts"]), (value, plan["conflicts"])


# --- --explain and --inert ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [False, None, "false", 0, "off", [], 1])
def test_inert_and_explain_report_every_repo_value_but_the_default(value, home, tmp_path):
    root = _repo(tmp_path, {"guards": {"enabled": value}})
    entry = next(e for e in crew_config.inert_settings(root) if e["key"] == KEY)
    assert entry["kind"] == "repo-ignored" and "no guard down" in entry["effect"]
    rows = {row["path"]: row for row in crew_config.explain_config(root, all_keys=True)}
    assert "repoIgnored" in rows[KEY] and rows[KEY]["repoIgnored"] == value
    assert rows[KEY]["value"] is True, "the machine layer's value is the one in force"


@pytest.mark.parametrize("cfg", [{"guards": {"enabled": True}}, {"guards": {}}, {}])
def test_a_default_or_absent_repo_value_is_quiet(cfg, home, tmp_path):
    root = _repo(tmp_path, cfg)
    assert not [e for e in crew_config.inert_settings(root) if e["key"] == KEY]
    rows = {row["path"]: row for row in crew_config.explain_config(root, all_keys=True)}
    assert "repoIgnored" not in rows[KEY]


def test_explain_prints_the_ignored_repo_value_as_json(home, tmp_path, capsys):
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    assert crew_config.main(["--explain", "--root", root, "--global-path", _gpath(home), "--all"]) == 0
    out = capsys.readouterr().out
    assert "repo asks `false`" in out and "False" not in out.split("repo asks")[1].split("\n")[0]
    assert "cannot stand a guard down" in out
    assert "auto-clear" not in out.split("repo asks")[1]


def test_explain_says_an_unconfirmed_machine_false_is_not_in_effect(home, tmp_path, capsys):
    root = _repo(tmp_path, {})
    path = _machine(home, {"guards": {"enabled": False}})
    rows = {row["path"]: row for row in crew_config.explain_config(root, path=path, all_keys=True)}
    assert rows[KEY]["unconfirmed"] is True
    _receipt(path)
    rows = {row["path"]: row for row in crew_config.explain_config(root, path=path, all_keys=True)}
    assert "unconfirmed" not in rows[KEY]


# --- /crew:status -----------------------------------------------------------------------------------------------

def test_status_says_unconfirmed_not_disabled_for_a_machine_false_nobody_confirmed(home, tmp_path):
    root = _repo(tmp_path, {})
    _machine(home, {"guards": {"enabled": False}})
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "DISABLED" not in line
    assert "NOT in effect" in line and "double confirmation" in line and "every guard still runs" in line


def test_status_says_disabled_only_for_a_confirmed_machine_false(home, tmp_path):
    root = _repo(tmp_path, {})
    path = _machine(home, {"guards": {"enabled": False}})
    _receipt(path)
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert line.startswith("guards   DISABLED - guards.enabled is false in the machine layer and the owner "
                           "confirmed it")
    assert "context-watch" in line


def test_status_says_a_repo_false_is_ignored(home, tmp_path):
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "DISABLED" not in line
    assert "ignored" in line and "only the machine layer counts" in line and "every guard still runs" in line


def test_status_says_nothing_extra_while_the_guards_are_on(home, tmp_path):
    root = _repo(tmp_path, {"guards": {"enabled": True}})
    assert "DISABLED" not in (crew_status._guards_line(root) or "")  # pylint: disable=protected-access
    assert crew_status._guards_line(_repo(tmp_path, {}, name="bare")) is None  # pylint: disable=protected-access


def test_every_mutation_anchor_is_present_exactly_once():
    """`guards_master_key_mutations.py` is not wired into `sabotage.py` (that is a harness file, so a feature PR
    may not edit it): this keeps its anchors honest so a drifted one cannot read as a pass."""
    import guards_master_key_mutations  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in guards_master_key_mutations.MASTER_KEY_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            text = handle.read().replace("\r\n", "\n")
        assert text.count(find) == 1, label
        assert test.startswith("tests/test_guards_master_key.py::"), label


def test_explain_reports_a_repo_null_even_when_the_machine_file_holds_the_key(home, tmp_path):
    """`without_null_shadows` drops a repo `null` the machine layer has a value for (it means "inherit"), so
    `--explain` must ask the file as loaded to report it."""
    root = _repo(tmp_path, {"guards": {"enabled": None}})
    path = _machine(home, {"guards": {"enabled": True}})
    rows = {row["path"]: row for row in crew_config.explain_config(root, path=path, all_keys=True)}
    assert "repoIgnored" in rows[KEY] and rows[KEY]["repoIgnored"] is None


# --- the receipt is bound to the file, and every route that replaces the file retires it (crew 1.3.95) --------------

def _confirmed(home, tmp_path, cfg=None):
    """A repo, and a machine file the owner switched off by the real propose / confirm / confirm route."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {})
    path = _machine(home, cfg or {})
    assert _confirm_twice(path)["state"] == "applied"
    assert crew_hook.guards_switched_off(root, str(home)) == "machine"
    return root, path


def test_confirm_records_the_two_confirmations_and_the_digest_of_the_file_it_applied(home):
    import crew_hook  # pylint: disable=import-outside-toplevel
    path = _machine(home, {})
    record = _confirm_twice(path)
    assert record["appliedDigest"] == crew_hook.canonical_digest(path)
    assert {c["prompt"] for c in record["confirmations"]} == {"p1", "p2"}
    stored = crew_humanonly.read_record(crew_humanonly.store_dir(path), record["change_id"])
    assert stored["appliedDigest"] == record["appliedDigest"]


def test_a_hand_written_false_after_a_set_back_to_true_does_not_count(home, tmp_path):
    """The finding: the receipt survived the key being set back, and a later hand-written `false` counted again."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    crew_config.write_global_config({KEY: True}, path=path)
    assert crew_hook.guards_switched_off(root, str(home)) is None
    _machine(home, {"guards": {"enabled": False}})
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_an_unrelated_set_keeps_a_confirmed_switch_in_force(home, tmp_path):
    """The receipt is bound to the file, so a write by crew itself must rebind it, or the guards come back on
    silently the first time the owner changes anything else."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    crew_config.write_global_config({"guards.profile": "standard"}, path=path)
    assert json.load(open(path, encoding="utf-8"))["guards"]["profile"] == "standard"
    assert crew_hook.guards_switched_off(root, str(home)) == "machine"


def test_a_hand_edit_after_a_set_still_leaves_the_guards_on(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    crew_config.write_global_config({"guards.profile": "standard"}, path=path)
    cfg = json.load(open(path, encoding="utf-8"))
    cfg["tier"] = "hand-edited"
    _machine(home, cfg)
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_another_keys_confirmation_keeps_a_confirmed_switch_in_force(home, tmp_path):
    """`/crew:confirm-config` of `humanOnly.approve` rewrites the same machine file."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    cid = crew_confirm_config.propose("machine", "humanOnly.approve", global_path=path, now=10)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "q1", global_path=path, now=11)
    record = crew_confirm_config.confirm(cid, "user-prompt", "q2", global_path=path, now=12)
    assert record["state"] == "applied"
    assert crew_hook.guards_switched_off(root, str(home)) == "machine"


def test_restoring_a_backup_retires_the_receipt_even_when_the_content_is_the_same(home, tmp_path):
    """The digest alone would let a restore of identical bytes keep the receipt: the explicit revocation does not."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    with open(path, encoding="utf-8") as handle:
        confirmed_text = handle.read()
    stamp = crew_backup.backup(path)
    crew_config.apply_restore(root, "machine", stamp, global_path=path)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == confirmed_text
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_rebuilding_the_file_retires_the_receipt(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    with open(path, encoding="utf-8") as handle:
        confirmed_text = handle.read()
    crew_config.apply_rebuild(root, "machine", use_profile=False, global_path=path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(confirmed_text)
    assert crew_hook.guards_switched_off(root, str(home)) is None, "the confirmed bytes written back by hand"


def test_migrating_the_machine_file_retires_the_receipt(home, tmp_path):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path, {"guards": {"forcePush": "block"}})
    plan = crew_migrate.build_global_plan(path)
    assert plan["writes"], plan
    with open(path, encoding="utf-8") as handle:
        confirmed_text = handle.read()
    crew_migrate.apply_plan(plan)
    assert json.load(open(path, encoding="utf-8"))["guards"]["enabled"] is False
    assert crew_hook.guards_switched_off(root, str(home)) is None
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(confirmed_text)
    assert crew_hook.guards_switched_off(root, str(home)) is None, "the confirmed bytes written back by hand"


def test_revoke_all_names_what_it_retired(home):
    path = _machine(home, {})
    _confirm_twice(path)
    assert crew_humanonly.revoke_all("machine", path, global_path=path) == [KEY]
    assert crew_humanonly.revoke_all("machine", path, global_path=path) == [], "nothing left to retire"
    assert crew_humanonly.revoke_all("repo", path, global_path=path) == []


# --- a repo copy is never carried into a rewritten repo file (crew 1.3.95) ----------------------------------------

@pytest.mark.parametrize("value", [False, None, "false", 0])
def test_an_upgrade_does_not_carry_a_repo_copy_of_the_switch_through(value):
    crew_upgrade = crew_migrate._upgrade_module()  # pylint: disable=protected-access
    for cfg in ({"schema": 8, "guards": {"profile": "standard", "overrides": {}, "enabled": value}},
                {"schema": 1, "guards": {"scope": "block", "enabled": value}}):
        out, notes = crew_upgrade.upgrade_config(json.loads(json.dumps(cfg)), ())
        assert "enabled" not in out["guards"], cfg
        assert notes["repoSwitchRemoved"] == [json.dumps(value)]
        assert any("guards.enabled" in line for line in crew_upgrade.schema8_lines(notes))


def test_an_upgrade_leaves_the_default_true_and_the_machine_file_alone():
    crew_upgrade = crew_migrate._upgrade_module()  # pylint: disable=protected-access
    out, notes = crew_upgrade.upgrade_config({"schema": 8, "guards": {"profile": "standard", "enabled": True}}, ())
    assert out["guards"]["enabled"] is True and notes["repoSwitchRemoved"] == []
    machine, mnotes = crew_upgrade.upgrade_global({"guards": {"enabled": False}}, ())
    assert machine["guards"]["enabled"] is False and not mnotes.get("repoSwitchRemoved")


# --- the reports say the right thing (crew 1.3.95) ----------------------------------------------------------------

def test_status_does_not_claim_the_guards_still_run_when_the_machine_false_is_confirmed(home, tmp_path):
    """The finding: with a confirmed machine false AND a repo false, status said DISABLED and then 'so every guard
    still runs'."""
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    path = _machine(home, {})
    _confirm_twice(path)
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert line.startswith("guards   DISABLED")
    assert "ignored" in line and "only the machine layer counts" in line
    assert "every guard still runs" not in line, line


def test_status_reports_a_repo_null_like_inert_does(home, tmp_path):
    root = _repo(tmp_path, {"guards": {"enabled": None}})
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "guards.enabled is null" in line and "every guard still runs" in line, line


def test_explain_says_so_when_the_machine_false_is_unconfirmed_and_a_repo_false_is_there_too(home, tmp_path, capsys):
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    path = _machine(home, {"guards": {"enabled": False}})
    crew_config._print_explain(  # pylint: disable=protected-access
        crew_config.explain_config(root, path=path, all_keys=True), root, True)
    out = capsys.readouterr().out
    assert "NOT confirmed" in out and "every guard still runs" in out, out
    assert "`false` is in force" not in out, out


def test_explain_keeps_the_in_force_wording_for_a_confirmed_machine_false(home, tmp_path, capsys):
    root = _repo(tmp_path, {"guards": {"enabled": False}})
    path = _machine(home, {})
    _confirm_twice(path)
    crew_config._print_explain(  # pylint: disable=protected-access
        crew_config.explain_config(root, path=path, all_keys=True), root, True)
    out = capsys.readouterr().out
    assert "`false` is in force" in out and "NOT confirmed" not in out, out


def test_a_crew_write_does_not_launder_a_hand_edit_into_a_confirmed_switch(home, tmp_path):
    """The rebinding applies only when the receipt backed the file BEFORE the write; a hand edit in between means
    it did not, so the next `--set` must not bless the edited file."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    cfg = json.load(open(path, encoding="utf-8"))
    cfg["tier"] = "hand-edited"
    _machine(home, cfg)
    assert crew_hook.guards_switched_off(root, str(home)) is None
    crew_config.write_global_config({"guards.profile": "standard"}, path=path)
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_explain_and_status_agree_with_the_hook_about_a_bare_record(home, tmp_path):
    """A record without the confirmations and the digest backs nothing for the hook, so the reports must not call
    it confirmed."""
    root = _repo(tmp_path, {})
    path = _machine(home, {"guards": {"enabled": False}})
    record = {"change_id": crew_humanonly.new_change_id(), "layer": "machine",
              "target": crew_humanonly.target_key(path), "key": KEY, "value": False, "state": "applied",
              "created": time.time(), "settled": time.time(), "confirmations": [], "reason": "forged"}
    crew_humanonly.write_record(crew_humanonly.store_dir(path), record)
    rows = {row["path"]: row for row in crew_config.explain_config(root, path=path, all_keys=True)}
    assert rows[KEY]["unconfirmed"] is True
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert "DISABLED" not in line and "NOT in effect" in line


# --- round 3: report in every machine state, race windows, revocations that fail ----------------------------------

@pytest.mark.parametrize("machine", [None, {}, {"guards": {"enabled": True}}, {"guards": {"enabled": False}}])
@pytest.mark.parametrize("repo_value", [None, False])
def test_inert_and_status_report_a_repo_copy_of_the_switch_in_every_machine_state(machine, repo_value, home, tmp_path):
    """The finding: with the machine file holding an explicit `true` (the shipped global template) a repo `null`
    was shadowed away and `--inert` and `/crew:status` said nothing."""
    root = _repo(tmp_path, {"guards": {"enabled": repo_value}})
    path = _gpath(home)
    if machine is not None:
        _machine(home, machine)
    entries = [e for e in crew_config.inert_settings(root, path) if e["key"] == KEY]
    assert [(e["kind"], e["value"]) for e in entries] == [("repo-ignored", repo_value)], machine
    line = crew_status._guards_line(root)  # pylint: disable=protected-access
    assert line and "ignored" in line and "guards.enabled" in line, (machine, line)


def test_explain_value_column_says_an_unconfirmed_false_is_not_in_effect(home, tmp_path, capsys):
    root = _repo(tmp_path, {})
    path = _machine(home, {"guards": {"enabled": False}})

    def row_line():
        rows = crew_config.explain_config(root, path=path, all_keys=True)
        crew_config._print_explain(rows, root, all_keys=True)  # pylint: disable=protected-access
        return next(line for line in capsys.readouterr().out.splitlines() if line.startswith(KEY))

    unconfirmed = row_line()
    assert "NOT in effect" in unconfirmed and unconfirmed.split()[2] == "false", unconfirmed
    _receipt(path)
    assert "NOT in effect" not in row_line()


def test_a_hand_edit_between_the_check_and_the_lock_is_not_laundered_by_the_restamp(home, tmp_path, monkeypatch):
    """N1, simulated: the old code judged `backed` before the lock, so a hand edit that landed after that check
    and before the write rode along under the restamp. `backed` is judged under the lock now."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    real = crew_config.crew_config_files.update_json

    def edit_then_write(target, mutate, **kwargs):
        cfg = json.load(open(target, encoding="utf-8"))
        cfg["hand"] = "edit"
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(cfg))
        return real(target, mutate, **kwargs)

    monkeypatch.setattr(crew_config.crew_config_files, "update_json", edit_then_write)
    crew_config.write_global_config({"guards.profile": "standard"}, path=path)
    assert json.load(open(path, encoding="utf-8"))["hand"] == "edit"
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_the_receipt_is_rebound_and_the_confirmed_digest_taken_inside_the_lock(home, tmp_path, monkeypatch):
    """The post-write window: the digest a receipt is bound to is read inside the file's lock, right after the
    replace. (A hand edit that never takes the lock can still land anywhere; this narrows it, it does not close
    it, and CONFIG.md says so.)"""
    held = []
    real_digest, real_restamp = crew_humanonly.applied_digest, crew_humanonly.restamp

    def digest(path):
        held.append(("digest", os.path.exists(path + ".lock")))
        return real_digest(path)

    def restamp(*args, **kwargs):
        held.append(("restamp", os.path.exists(args[1] + ".lock")))
        return real_restamp(*args, **kwargs)

    monkeypatch.setattr(crew_humanonly, "applied_digest", digest)
    monkeypatch.setattr(crew_humanonly, "restamp", restamp)
    path = _machine(home, {})
    _confirm_twice(path)
    assert held and all(inside for _, inside in held), held
    held.clear()
    crew_config.write_global_config({"guards.profile": "standard"}, path=path)
    assert ("restamp", True) in held and all(inside for _, inside in held), held


def _fail_revocations(monkeypatch):
    real = crew_humanonly.write_record

    def refuse(store, record):
        if record.get("state") == "revoked":
            raise OSError("simulated: the confirmation store is read-only")
        return real(store, record)

    monkeypatch.setattr(crew_humanonly, "write_record", refuse)


def test_a_revocation_that_cannot_be_written_is_reported_and_the_receipt_still_backs_nothing(
        home, tmp_path, monkeypatch, capsys):
    """N3: `revoke` swallowed the OSError and `retire_receipts`' callers dropped the answer."""
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    stamp = crew_backup.backup(path)
    _fail_revocations(monkeypatch)
    capsys.readouterr()
    crew_config.apply_restore(root, "machine", stamp, global_path=path)
    err = capsys.readouterr().err
    assert "could not record the revocation of guards.enabled" in err, err
    assert crew_hook.guards_switched_off(root, str(home)) is None, "fail closed: the receipt backs nothing"


def test_apply_rebuild_surfaces_a_failed_revocation(home, tmp_path, monkeypatch, capsys):
    root, path = _confirmed(home, tmp_path)
    _fail_revocations(monkeypatch)
    capsys.readouterr()
    crew_config.apply_rebuild(root, "machine", use_profile=False, global_path=path)
    assert "could not record the revocation" in capsys.readouterr().err


def test_migrate_apply_surfaces_a_failed_revocation(home, tmp_path, monkeypatch, capsys):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path, {"guards": {"forcePush": "block"}})
    plan = crew_migrate.build_global_plan(path)
    _fail_revocations(monkeypatch)
    capsys.readouterr()
    crew_migrate.apply_plan(plan)
    assert "could not record the revocation" in capsys.readouterr().err
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_a_set_back_to_true_surfaces_a_failed_revocation(home, tmp_path, monkeypatch, capsys):
    import crew_hook  # pylint: disable=import-outside-toplevel
    root, path = _confirmed(home, tmp_path)
    _fail_revocations(monkeypatch)
    capsys.readouterr()
    crew_config.write_global_config({KEY: True}, path=path)
    assert "could not record the revocation of guards.enabled" in capsys.readouterr().err
    _machine(home, {"guards": {"enabled": False}})
    assert crew_hook.guards_switched_off(root, str(home)) is None


def test_retire_returns_what_failed_and_revoke_all_stays_quiet(home, monkeypatch, capsys):
    path = _machine(home, {})
    _confirm_twice(path)
    _fail_revocations(monkeypatch)
    capsys.readouterr()
    assert crew_humanonly.retire("machine", path, global_path=path) == ([], [KEY])
    assert "could not record the revocation" in capsys.readouterr().err
    assert crew_humanonly.revoke_all("machine", path, global_path=path) == []
    assert capsys.readouterr().err == ""


def test_migrating_a_repo_file_retires_its_human_only_receipts_like_rebuild_and_restore_do(home, tmp_path, capsys):
    """L: `--rebuild` and `--restore` retire a repo file's `humanOnly` receipts; `/crew:migrate` rewriting the same
    file now does too (the owner confirmed the content that was there, not what replaced it)."""
    import subprocess  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, {"schema": crew_migrate.LEGACY_SCHEMA_MAX, "guards": {"forcePush": "block"},
                            "humanOnly": {"approve": False}})
    subprocess.run(["git", "init", "-q", root], check=True)
    config = os.path.join(root, ".crew", "config.json")
    record = {"change_id": crew_humanonly.new_change_id(), "layer": "repo", "target": crew_humanonly.target_key(config),
              "key": "humanOnly.approve", "value": False, "state": "applied", "created": 1.0, "settled": 100.0,
              "confirmations": []}
    store = crew_humanonly.store_dir(_gpath(home))
    crew_humanonly.write_record(store, record)
    plan = crew_migrate.build_plan(root)
    assert [w["path"] for w in plan["writes"] if w.get("replaces")] == [".crew/config.json"], plan["writes"]
    crew_migrate.apply_plan(plan)
    newest = crew_humanonly._newest_settled(store, "repo", config, "humanOnly.approve")  # pylint: disable=protected-access
    assert newest["state"] == "revoked", newest
