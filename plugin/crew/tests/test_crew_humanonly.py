"""crew 1.3.9: the human-only opt-out (`humanOnly.approve`,
`humanOnly.promoteMarker`) and the double confirmation behind it.

Must-block cases: every way a `false` must NOT take effect, and every write
the config writers must refuse. Must-allow cases: the opt-out the owner asked
for does take effect when, and only when, every rule holds. Each rule has a
mutation in `humanonly_mutations.py` that must turn one of these red.

Nothing here touches a real config: every machine file is under `tmp_path`,
and its confirmation store sits beside it.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_config_files
import crew_confirm_config
import crew_humanonly

KEY = "humanOnly.approve"



def _slurp(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()

def _machine(tmp_path, value=None, present=True):
    path = tmp_path / "home" / "crew" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if present:
        body = {} if value is None else {"humanOnly": {"approve": value}}
        path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def _repo(tmp_path, value=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    body = {"schema": 8} if value is None else {"schema": 8, "humanOnly": {"approve": value}}
    (root / ".crew" / "config.json").write_text(json.dumps(body), encoding="utf-8")
    return str(root)


def _tracker(state):
    return lambda _path: state


def _applied(gpath, layer, path, value=False, settled=100.0, state="applied"):
    record = {"change_id": crew_humanonly.new_change_id(), "layer": layer,
              "target": crew_humanonly.target_key(path), "key": KEY, "value": value,
              "state": state, "created": settled, "settled": settled,
              "confirmations": []}
    crew_humanonly.write_record(crew_humanonly.store_dir(gpath), record)
    return record


def _resolve(root, gpath, tracker=crew_humanonly.UNTRACKED):
    return crew_humanonly.resolve(root, "approve", global_path=gpath,
                                  tracker=_tracker(tracker))


def _repo_cfg(root):
    return os.path.join(root, ".crew", "config.json")


# --- must-block: the opt-out does not take effect ---------------------------------

def test_the_default_is_human_only(tmp_path):
    got = _resolve(_repo(tmp_path), _machine(tmp_path, present=False))
    assert got["humanOnly"] is True
    assert "default" in got["reason"]


def test_a_machine_false_with_no_receipt_is_human_only(tmp_path):
    got = _resolve(_repo(tmp_path), _machine(tmp_path, False))
    assert got["humanOnly"] is True
    assert "no double-confirmed change" in got["reason"]


def test_a_repo_true_vetoes_a_confirmed_machine_false(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", gpath)
    got = _resolve(_repo(tmp_path, True), gpath)
    assert got["humanOnly"] is True
    assert "repo: true" in got["reason"]


def test_a_machine_true_vetoes_a_confirmed_repo_false(tmp_path):
    gpath = _machine(tmp_path, True)
    root = _repo(tmp_path, False)
    _applied(gpath, "repo", _repo_cfg(root))
    assert _resolve(root, gpath)["humanOnly"] is True


@pytest.mark.parametrize("state", [crew_humanonly.TRACKED, crew_humanonly.UNKNOWN])
def test_a_tracked_or_unknown_repo_file_never_opts_out(tmp_path, state):
    gpath = _machine(tmp_path, present=False)
    root = _repo(tmp_path, False)
    _applied(gpath, "repo", _repo_cfg(root))
    got = _resolve(root, gpath, tracker=state)
    assert got["humanOnly"] is True
    assert got["layers"]["repo"]["tracking"] == state


@pytest.mark.parametrize("value", ["false", 0, [], {"x": 1}])
def test_a_malformed_value_reads_as_human_only(tmp_path, value):
    gpath = _machine(tmp_path, value)
    _applied(gpath, "machine", gpath)
    got = _resolve(_repo(tmp_path), gpath)
    assert got["humanOnly"] is True
    assert "not null, true or false" in got["reason"]


def test_a_revocation_newer_than_the_receipt_wins(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", gpath, settled=100.0)
    _applied(gpath, "machine", gpath, value=None, settled=200.0, state="revoked")
    assert _resolve(_repo(tmp_path), gpath)["humanOnly"] is True


def test_a_pending_proposal_is_not_a_receipt(tmp_path):
    gpath = _machine(tmp_path, False)
    record = _applied(gpath, "machine", gpath)
    record["state"], record["settled"] = "pending", None
    crew_humanonly.write_record(crew_humanonly.store_dir(gpath), record)
    assert _resolve(_repo(tmp_path), gpath)["humanOnly"] is True


def test_a_receipt_for_another_file_does_not_count(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", str(tmp_path / "elsewhere.json"))
    assert _resolve(_repo(tmp_path), gpath)["humanOnly"] is True


def test_an_unreadable_receipt_is_could_not_tell_and_human_only(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", gpath)
    store = crew_humanonly.store_dir(gpath)
    with open(os.path.join(store, "cc-00000000.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    got = _resolve(_repo(tmp_path), gpath)
    assert got["humanOnly"] is True
    assert "could not be read" in got["reason"]


@pytest.mark.parametrize("layer, value", [
    ("machine", False), ("repo", False), ("repo", None)])
def test_the_writers_refuse_a_change_that_lifts_a_human_step(layer, value):
    reason = crew_config.value_allowed(KEY, layer, value)
    assert reason is not None and KEY in reason


def test_the_repo_writer_refuses_removing_a_veto():
    assert crew_config.unset_allowed(KEY, "repo") is not None


def test_a_non_boolean_value_is_refused_by_its_values():
    reason = crew_config.value_allowed(KEY, "machine", "no")
    assert "is not one of its values" in reason


def test_write_global_config_refuses_false(tmp_path):
    gpath = _machine(tmp_path)
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.write_global_config({KEY: False}, path=gpath)
    assert json.loads(_slurp(gpath)) == {}


def test_confirm_refuses_anything_but_a_user_prompt(tmp_path):
    gpath = _machine(tmp_path, present=False)
    record = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)
    for via in ("cli", "autopilot", "", None):
        with pytest.raises(crew_confirm_config.Refused):
            crew_confirm_config.confirm(record["change_id"], via, "p1", global_path=gpath, now=1)
    stored = crew_humanonly.read_record(crew_humanonly.store_dir(gpath), record["change_id"])
    assert stored["confirmations"] == []


def test_one_prompt_confirms_once(tmp_path):
    gpath = _machine(tmp_path)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=2)
    assert json.loads(_slurp(gpath)) == {}


def test_a_single_confirmation_writes_nothing(tmp_path):
    gpath = _machine(tmp_path)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    record = crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    assert record["state"] == "pending"
    assert json.loads(_slurp(gpath)) == {}


def test_an_expired_proposal_cannot_be_confirmed(tmp_path):
    gpath = _machine(tmp_path)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    late = crew_humanonly.PROPOSAL_TTL_SECONDS + 1
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=late)
    stored = crew_humanonly.read_record(crew_humanonly.store_dir(gpath), cid)
    assert stored["state"] == "expired"
    assert json.loads(_slurp(gpath)) == {}


def test_a_cancelled_proposal_cannot_be_confirmed(tmp_path):
    gpath = _machine(tmp_path, present=False)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    crew_confirm_config.cancel(cid, global_path=gpath, now=1)
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=2)


@pytest.mark.parametrize("state", [crew_humanonly.TRACKED, crew_humanonly.UNKNOWN])
def test_propose_refuses_a_tracked_or_unknown_repo_file(tmp_path, state):
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.propose("repo", KEY, root=_repo(tmp_path),
                                    global_path=_machine(tmp_path), tracker=_tracker(state))


def test_propose_refuses_a_key_that_is_not_human_only(tmp_path):
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.propose("machine", "scope.mode", global_path=_machine(tmp_path))


def test_a_repo_file_tracked_before_the_second_confirmation_is_refused(tmp_path):
    gpath, root = _machine(tmp_path), _repo(tmp_path)
    cid = crew_confirm_config.propose("repo", KEY, root=root, global_path=gpath, now=0,
                                      tracker=_tracker(crew_humanonly.UNTRACKED))["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=2,
                                         tracker=_tracker(crew_humanonly.TRACKED))
    assert record["state"] == "refused"
    assert "humanOnly" not in json.loads(_slurp(_repo_cfg(root)))


def test_a_file_changed_since_the_proposal_is_stale(tmp_path):
    gpath = _machine(tmp_path)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    with open(gpath, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"qa": {"provider": "claude"}}))
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=2)
    assert record["state"] == "stale"
    assert json.loads(_slurp(gpath)) == {"qa": {"provider": "claude"}}


def test_the_cli_has_no_confirm_subcommand(capsys):
    with pytest.raises(SystemExit):
        crew_confirm_config.main(["confirm", "cc-00000000"])
    capsys.readouterr()


def test_the_command_file_is_user_only():
    path = os.path.join(context._ROOT, "commands", "confirm-config.md")  # pylint: disable=protected-access
    head = _slurp(path).split("---")[1]
    assert "disable-model-invocation: true" in head


# --- must-allow: the opt-out takes effect when every rule holds -----------------

def test_a_confirmed_machine_false_opts_out(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", gpath)
    got = _resolve(_repo(tmp_path), gpath)
    assert got["humanOnly"] is False
    assert "machine" in got["reason"]


def test_a_confirmed_untracked_repo_false_opts_out(tmp_path):
    gpath = _machine(tmp_path, present=False)
    root = _repo(tmp_path, False)
    _applied(gpath, "repo", _repo_cfg(root))
    assert _resolve(root, gpath)["humanOnly"] is False


def test_the_other_key_is_independent(tmp_path):
    gpath = _machine(tmp_path, False)
    _applied(gpath, "machine", gpath)
    got = crew_humanonly.resolve(_repo(tmp_path), "promoteMarker", global_path=gpath,
                                 tracker=_tracker(crew_humanonly.UNTRACKED))
    assert got["humanOnly"] is True


@pytest.mark.parametrize("layer, value", [
    ("machine", True), ("machine", None), ("repo", True)])
def test_the_writers_allow_a_change_that_keeps_the_human_step(layer, value):
    assert crew_config.value_allowed(KEY, layer, value) is None


def test_the_machine_writer_allows_removing_its_own_value():
    assert crew_config.unset_allowed(KEY, "machine") is None


def test_two_confirmations_apply_a_machine_opt_out(tmp_path):
    gpath = _machine(tmp_path, present=False)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=2)
    assert record["state"] == "applied"
    assert json.loads(_slurp(gpath)) == {"humanOnly": {"approve": False}}
    assert _resolve(_repo(tmp_path), gpath)["humanOnly"] is False


def test_a_crew_write_back_to_true_revokes_the_receipt(tmp_path):
    gpath = _machine(tmp_path, present=False)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=2)
    crew_config.write_global_config({KEY: True}, path=gpath)
    # A `false` put back by hand is no longer backed by the old receipt.
    with open(gpath, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"humanOnly": {"approve": False}}))
    assert _resolve(_repo(tmp_path), gpath)["humanOnly"] is True


# --- the tracked probe, against real git -------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_tracking_reads_git(tmp_path):
    root = tmp_path / "g"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    cfg = root / ".crew" / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    assert crew_humanonly.tracking(str(cfg)) == crew_humanonly.UNTRACKED
    _git(root, "add", ".crew/config.json")
    assert crew_humanonly.tracking(str(cfg)) == crew_humanonly.TRACKED


def test_tracking_outside_a_repository_is_could_not_tell(tmp_path):
    outside = tmp_path / "plain"
    outside.mkdir()
    env_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
    os.environ["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    try:
        assert crew_humanonly.tracking(str(outside / "config.json")) == crew_humanonly.UNKNOWN
    finally:
        if env_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = env_ceiling


def test_tracking_with_no_git_is_could_not_tell(tmp_path):
    def missing(*_a, **_k):
        raise FileNotFoundError("git")
    assert crew_humanonly.tracking(str(tmp_path / "c.json"), runner=missing) == crew_humanonly.UNKNOWN


def test_a_real_untracked_repo_file_opts_out_end_to_end(tmp_path):
    root = tmp_path / "g"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    cfg = root / ".crew" / "config.json"
    cfg.write_text(json.dumps({"schema": 8}), encoding="utf-8")
    gpath = _machine(tmp_path, present=False)
    cid = crew_confirm_config.propose("repo", KEY, root=str(root), global_path=gpath,
                                      now=0)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath, now=1)
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath, now=2)
    assert record["state"] == "applied", record.get("reason")
    got = crew_humanonly.resolve(str(root), "approve", global_path=gpath)
    assert got["humanOnly"] is False
    _git(root, "add", ".crew/config.json")
    assert crew_humanonly.resolve(str(root), "approve", global_path=gpath)["humanOnly"] is True


def test_resolve_cli_says_nothing_acts_on_it_yet(tmp_path, capsys):
    gpath = _machine(tmp_path, present=False)
    assert crew_confirm_config.main(["resolve", "--root", _repo(tmp_path),
                                     "--global-path", gpath]) == 0
    out = capsys.readouterr().out
    assert "humanOnly.approve: human-only" in out
    assert "no hook reads humanOnly.promoteMarker" in out


def test_store_writes_leave_no_temp_files(tmp_path):
    gpath = _machine(tmp_path, present=False)
    crew_confirm_config.propose("machine", KEY, global_path=gpath, now=0)
    names = os.listdir(crew_humanonly.store_dir(gpath))
    assert all(n.startswith("cc-") and n.endswith(".json") for n in names)


def test_apply_bypasses_only_humanonly_keys(tmp_path):
    gpath = _machine(tmp_path, present=False)
    with pytest.raises(ValueError):
        crew_config.apply_confirmed_optout("machine", "scope.mode", gpath,
                                           crew_config_files.ABSENT)


def test_every_mutation_anchor_is_present_exactly_once():
    """Until PR 2 wires `humanonly_mutations.py` into `sabotage.py`, this keeps
    its anchors honest: an anchor that drifts would make that run go
    `ANCHOR LOST` instead of proving anything."""
    import humanonly_mutations  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in humanonly_mutations.HUMANONLY_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as fh:
            text = fh.read().replace("\r\n", "\n")
        assert text.count(find) == 1, label
        assert test.startswith(
            ("tests/test_crew_humanonly.py::", "tests/test_humanonly_live.py::")), label
