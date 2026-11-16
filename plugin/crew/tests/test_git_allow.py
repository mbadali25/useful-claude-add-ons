"""crew 1.3.122: `guards.git.allow`, the owner's switch that lets git commands past
crew's command guards (`crew_gitallow.py`).

CLAUDE.md: a hook change that can block carries must-block and must-allow cases,
sabotage-tested. Every must-allow with the switch ON has a must-block beside it
with the switch OFF (today's behaviour, unchanged), and every new branch has a
mutation in `gitallow_mutations.py` that must turn one of these red. That table
is not wired into `sabotage.py` (review harness, `scripts/check-tooling-pr.py`
`HARNESS`); `test_every_mutation_anchor_is_present_exactly_once` keeps its
anchors honest until it is.

Nothing touches the real machine config: every reader is pointed under
`tmp_path` (in-process by `GLOBAL_CONFIG_PATH`, a spawned gate by HOME and
USERPROFILE), and no case installs anything.
"""
import json
import os
import pathlib
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import cloud_guard
import crew_config
import crew_confirm_config
import crew_fixtures
import crew_gitallow
import crew_humanonly
import crew_state
from review_fixtures import git
from scope_fixtures import make_repo

KEY = crew_gitallow.KEY
_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()


# --- fixtures ------------------------------------------------------------------------

@pytest.fixture(name="machine")
def _machine(tmp_path, monkeypatch):
    """The machine config under tmp_path, for every in-process reader."""
    home = tmp_path / "home"
    path = home / ".claude" / "crew" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("CI", "CREW_UNATTENDED"):
        monkeypatch.delenv(name, raising=False)
    return path


def _confirm(machine, value):
    """Turn the switch on the one way real code can: `propose`, then two
    `confirm`s from two distinct user prompts (what the prompt hook passes).
    Returns the applied record. Never writes a receipt by hand."""
    gpath = str(machine)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, value=value)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", f"p1-{cid}", global_path=gpath)
    record = crew_confirm_config.confirm(cid, "user-prompt", f"p2-{cid}", global_path=gpath)
    assert record["state"] == "applied", record
    return record


def _arm(machine, value, confirmed=True, extra=None):
    """The machine file carrying `extra` guards and `value`: through the
    double confirmation when `confirmed`, else written by hand (what an
    agent's Edit or a hand edit leaves)."""
    body = {"guards": dict(extra or {})}
    if confirmed:
        machine.write_text(json.dumps(body), encoding="utf-8")
        _confirm(machine, value)
        return
    body["guards"]["git"] = {"allow": value}
    machine.write_text(json.dumps(body), encoding="utf-8")


def _store(machine):
    return crew_humanonly.store_dir(str(machine))


def _applied(machine):
    """The newest applied record in the store (the one `settings` reads)."""
    records, problems = crew_humanonly.all_records(_store(machine))
    assert not problems
    return max((r for r in records if r.get("state") == "applied"), key=lambda r: r["settled"])


def _setting(root):
    return crew_gitallow.settings(str(root))["allow"]


# --- the value and the subcommand ----------------------------------------------------

@pytest.mark.parametrize("value,expect", [
    (None, "off"), ("off", "off"), ("all", "all"),
    (["commit", "push"], frozenset({"commit", "push"})),
    ("ALL", None), ("true", None), (True, None), ([], None), (["Commit"], None),
    (["commit", 3], None), ({"commit": True}, None), ("commit", None)])
def test_normalise(value, expect):
    assert crew_gitallow.normalise(value) == expect


@pytest.mark.parametrize("args,sub", [
    (["push", "--force"], "push"),
    (["-C", "/x", "-c", "a=b", "--no-pager", "commit", "-m", "x"], "commit"),
    (["Commit", "-m", "x"], None), (["STATUS"], None),
    (["--git-dir", "/x/.git", "status"], "status"),
    ([], None), (["-C", "/x"], None), (["$SUB"], None)])
def test_subcommand(args, sub):
    assert crew_gitallow.subcommand(args) == sub


def test_allows():
    allowed = frozenset({"commit"})
    assert crew_gitallow.allows("all", None)
    assert crew_gitallow.allows(allowed, "commit")
    assert not crew_gitallow.allows(allowed, "push")
    assert not crew_gitallow.allows(allowed, None)
    assert not crew_gitallow.allows("off", "commit")


# --- what is in force ----------------------------------------------------------------

def test_off_by_default(tmp_path, machine):
    assert machine
    root = make_repo(tmp_path, mode=None)
    assert _setting(root) == "off"


def test_a_confirmed_machine_all_is_in_force(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _setting(root) == "all"


def test_a_confirmed_allowlist_is_in_force(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["commit", "push"])
    assert _setting(root) == frozenset({"commit", "push"})


def test_a_hand_edit_with_no_receipt_is_off(tmp_path, machine):
    """An agent's Edit of the machine file is not the owner's double confirmation."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all", confirmed=False)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "not honoured" in got["why"]


def test_a_receipt_for_another_value_does_not_back_it(tmp_path, machine):
    """Confirming `["status"]` then hand-editing to `"all"` is off."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["status"])
    machine.write_text(json.dumps({"guards": {"git": {"allow": "all"}}}), encoding="utf-8")
    assert _setting(root) == "off"


def test_a_revocation_newer_than_the_receipt_wins(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _setting(root) == "all"
    crew_humanonly.revoke("machine", str(machine), KEY, global_path=str(machine),
                          now=time.time() + 5)
    assert _setting(root) == "off"


# --- review finding 1: a receipt is a WHOLE double confirmation (crew 1.3.75) --------

def _forge(record, how):
    """`record` (a real applied receipt) changed the way a forger would."""
    other = os.path.join(os.path.dirname(record["path"]), "other.json")
    first, second = record["confirmations"]
    changes = {
        "no confirmations": {"confirmations": []},
        "one confirmation": {"confirmations": [first]},
        "one prompt twice": {"confirmations": [first, dict(second, prompt=first["prompt"])]},
        "not a user prompt": {"confirmations": [first, dict(second, via="agent")]},
        "a blank prompt": {"confirmations": [first, dict(second, prompt=" ")]},
        "a confirmation after expiry": {
            "confirmations": [first, dict(second, at=record["expires"] + 1)],
            "settled": record["expires"] + 1},
        "settled before the second": {"settled": first["at"] - 1},
        "a longer window": {"expires": record["created"]
                            + crew_humanonly.PROPOSAL_TTL_SECONDS + 60},
        "another path": {"path": other},
        "another target": {"target": crew_humanonly.target_key(other)},
        "no binding": {"binding": None},
        "a value off": {"value": "off"},
    }[how]
    return dict(record, **changes)


FORGERIES = ["no confirmations", "one confirmation", "one prompt twice", "not a user prompt",
             "a blank prompt", "a confirmation after expiry", "settled before the second",
             "a longer window", "another path", "another target", "no binding", "a value off"]


def test_a_real_double_confirmation_is_whole(tmp_path, machine):
    """Must-allow neighbour of every forgery below: the record `confirm` leaves."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    record = _applied(machine)
    assert crew_gitallow.receipt_problem(record, str(machine)) is None
    assert len(record["confirmations"]) == 2 and record["binding"]
    assert _setting(root) == "all"


@pytest.mark.parametrize("how", FORGERIES)
def test_a_forged_receipt_is_not_honoured(tmp_path, machine, how):
    """The review's case: an `applied` record with no confirmations and another
    `path` turned "all" on. Each forged field alone now reads as off."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    forged = _forge(_applied(machine), how)
    crew_humanonly.write_record(_store(machine), forged)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off", (how, got)
    assert "not whole" in got["why"] or "not honoured" in got["why"], got


def test_a_receipt_tampered_to_another_value_does_not_back_it(tmp_path, machine):
    """A whole receipt bound to this very file, but for a different value."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["status"])
    crew_humanonly.write_record(_store(machine), dict(_applied(machine), value="all"))
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "last confirmed value" in got["why"], got


# --- review finding 2: the receipt is bound to the file it left (crew 1.3.75) -------

def test_a_hand_edit_to_off_and_back_is_off(tmp_path, machine):
    """all (confirmed) -> off by hand -> the confirmed bytes back by hand: off."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    confirmed = machine.read_bytes()
    machine.write_text(json.dumps({"guards": {"git": {"allow": "off"}}}), encoding="utf-8")
    assert _setting(root) == "off"
    time.sleep(0.05)
    machine.write_bytes(confirmed)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "changed since that confirmation" in got["why"], got


def test_touching_the_machine_file_turns_it_off(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    stat = os.stat(machine)
    os.utime(machine, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert _setting(root) == "off"


def test_a_crew_write_of_another_machine_key_keeps_it_on(tmp_path, machine):
    """Must-allow neighbour: crew's own writer re-binds the receipt."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    crew_config.write_global_config({"context.autoClear.enabled": True}, path=str(machine))
    assert json.loads(machine.read_text(encoding="utf-8"))["context"]["autoClear"]["enabled"]
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "all", got
    assert _applied(machine).get("reboundFrom")


def test_a_hand_edit_then_a_crew_write_stays_off(tmp_path, machine):
    """crew's writer re-binds only a receipt that backed the file before it."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["status"])
    body = json.loads(machine.read_text(encoding="utf-8"))
    body["guards"]["git"]["allow"] = "all"
    machine.write_text(json.dumps(body), encoding="utf-8")
    crew_config.write_global_config({"context.autoClear.enabled": True}, path=str(machine))
    assert _setting(root) == "off"


def test_a_machine_humanonly_optout_keeps_it_on(tmp_path, machine):
    """The other double-confirmed machine write re-binds it too."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    gpath = str(machine)
    cid = crew_confirm_config.propose("machine", "humanOnly.approve", global_path=gpath)["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "h1", global_path=gpath)
    assert crew_confirm_config.confirm(cid, "user-prompt", "h2",
                                       global_path=gpath)["state"] == "applied"
    assert _setting(root) == "all"


# --- review finding 3: an unreadable repo file is a veto (crew 1.3.75) ----------------

@pytest.mark.parametrize("content", [
    b"{ not json", b"[]", b"\xff\xfe\x00garbage", b'{"guards": 5}',
    b'{"guards": {"git": "off"}}', b'{"guards": {"git": ["all"]}}'])
def test_an_unreadable_repo_file_is_a_veto(tmp_path, machine, content):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew" / "config.json").write_bytes(content)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "veto" in got["why"], got


def test_a_repo_config_that_cannot_be_opened_is_a_veto(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew" / "config.json").mkdir()
    assert _setting(root) == "off"


@pytest.mark.parametrize("content", [
    None, b"{}", b'{"guards": {}}', b'{"guards": null}', b'{"guards": {"git": null}}',
    b'{"guards": {"git": {}}}', b'{"guards": {"git": {"allow": null}}}'])
def test_an_absent_or_silent_repo_file_is_no_veto(tmp_path, machine, content):
    """Must-allow neighbour: absent, empty or null is not "unreadable"."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    if content is not None:
        (root / ".crew" / "config.json").write_bytes(content)
    assert _setting(root) == "all"


def test_a_repo_off_vetoes(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": "off"}}}), encoding="utf-8")
    assert _setting(root) == "off"


@pytest.mark.parametrize("repo_value", ["ALL", 1, ["Bad Name"]])
def test_a_malformed_repo_value_is_a_veto(tmp_path, machine, repo_value):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": repo_value}}}), encoding="utf-8")
    assert _setting(root) == "off"


def test_a_repo_all_never_arms_it(tmp_path, machine):
    """A cloned repository must not loosen a guard on someone else's machine."""
    assert machine
    root = make_repo(tmp_path, mode=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": "all"}}}), encoding="utf-8")
    assert _setting(root) == "off"


def test_a_repo_null_is_silent(tmp_path, machine):
    """Both templates carry null, so a template-written repo file never vetoes."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": None}}}), encoding="utf-8")
    assert _setting(root) == "all"


@pytest.mark.parametrize("value", ["ALL", "yes", True, [], ["Push"]])
def test_a_malformed_machine_value_is_off(tmp_path, machine, value):
    """`propose` refuses these, so only a hand edit can write one."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, value, confirmed=False)
    assert _setting(root) == "off"


def test_the_templates_carry_null():
    assert crew_config.default_config()["guards"]["git"] == {"allow": None}
    assert crew_config.default_global_config()["guards"]["git"] == {"allow": None}


# --- the writers -----------------------------------------------------------------------

@pytest.mark.parametrize("layer,value,refused", [
    ("machine", "all", True), ("machine", ["commit"], True), ("machine", "off", False),
    ("machine", None, False), ("repo", "all", True), ("repo", ["push"], True),
    ("repo", "off", False), ("repo", None, True)])
def test_the_writers_refuse_turning_it_on(layer, value, refused):
    reason = crew_config.value_allowed(KEY, layer, value)
    assert (reason is not None) is refused, reason


def test_two_confirmations_turn_it_on(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    gpath = str(machine)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, value="all")["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath)
    assert _setting(root) == "off", "one confirmation changes nothing"
    record = crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath)
    assert record["state"] == "applied"
    assert json.loads(machine.read_text(encoding="utf-8"))["guards"]["git"]["allow"] == "all"
    assert _setting(root) == "all"


def test_a_crew_write_back_to_off_revokes_the_receipt(tmp_path, machine, monkeypatch):
    """Even the confirmed bytes AND modification time put back by hand stay
    off once crew's writer turned it off: the revocation is newer. The change
    time is pinned so the binding matches and the revocation alone holds it
    off (a Windows CopyFile restore carries the change time over too)."""
    monkeypatch.setattr(crew_gitallow, "_change_ns", lambda handle, stat: 0)
    root = make_repo(tmp_path, mode=None)
    gpath = str(machine)
    _confirm(machine, "all")
    confirmed, stat = machine.read_bytes(), os.stat(machine)
    crew_config.write_global_config({KEY: "off"}, path=gpath)
    machine.write_bytes(confirmed)
    os.utime(machine, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert crew_gitallow.file_binding(gpath) == _applied(machine)["binding"]
    assert _setting(root) == "off", "the old receipt must not back a later hand edit"


@pytest.mark.parametrize("layer,value", [
    ("repo", "all"), ("machine", "off"), ("machine", None), ("machine", "ALL"),
    ("machine", [])])
def test_propose_refuses_what_it_cannot_confirm(tmp_path, machine, layer, value):
    root = make_repo(tmp_path, mode=None)
    # An existing, untracked repo file: the one a humanOnly repo opt-out may use.
    (root / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.propose(layer, KEY, root=str(root), global_path=str(machine),
                                    value=value)


def test_apply_refuses_a_repo_or_off_value(machine):
    for layer, value in (("repo", "all"), ("machine", "off")):
        with pytest.raises(ValueError):
            crew_config.apply_confirmed_optout(layer, KEY, str(machine), "x",
                                               global_path=str(machine), value=value)


# --- the cloud guard: forcePush ---------------------------------------------------------

def _evaluate(root, command, tool="Bash", mode="block", raw=False):
    """`raw` keeps the backslashes (a continuation, a heredoc delimiter); the
    default turns them into `/` so a Windows path in a command reads as POSIX."""
    return cloud_guard.evaluate(str(root), tool, command if raw else command.replace("\\", "/"),
                                {"cwd": str(root)}, mode)


def _rules(result, rule):
    return [r for r in result["rows"] if r[0] == rule and r[2] != "allow"]


FORCE = ["git push --force origin main", "git push -f origin HEAD", "git push origin +main"]


@pytest.mark.parametrize("command", FORCE)
def test_force_push_is_refused_with_the_switch_off(tmp_path, machine, command):
    assert machine
    root = make_repo(tmp_path, mode=None)
    result = _evaluate(root, command)
    assert result["decision"] == "deny" and _rules(result, "forcePush"), result


@pytest.mark.parametrize("command", FORCE)
def test_force_push_passes_with_all(tmp_path, machine, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command)
    assert result["decision"] == "allow", result
    assert any(r[0] == "forcePush" and r[1].startswith("gitAllow:") for r in result["rows"])


@pytest.mark.parametrize("tool,command", [
    ("PowerShell", "git push --force origin main"),
    ("PowerShell", "git -C {root} push -f origin main")])
def test_force_push_passes_with_all_in_powershell(tmp_path, machine, tool, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    command = command.format(root=root.as_posix())
    assert _evaluate(root, command, tool)["decision"] == "allow"


# --- review finding 4: a git command carrying config or a command is never exempt ---

HELD = [
    "git -c alias.status='!terraform apply' status",
    "git -c core.sshCommand='terraform apply' push --force origin main",
    "git -calias.x=y push --force origin main",
    "git --config-env=core.pager=EVIL log",
    "git --exec-path=/tmp/evil push --force origin main",
    "git rebase --exec 'terraform apply' HEAD~2",
    "git rebase -x 'terraform apply' HEAD~2",
    "git rebase -ix 'terraform apply' HEAD~2",
    "git submodule foreach 'terraform apply'",
    "git bisect run terraform apply",
    "git push --receive-pack='terraform apply' --force origin main",
    "git fetch --upload-pack='terraform apply' origin",
    "git clone -u 'terraform apply' x y",
    "git grep -O'terraform apply' foo",
    "git difftool --extcmd='terraform apply'",
    "git filter-branch --tree-filter 'terraform apply' HEAD"]
NOT_HELD = [
    "git commit -c ORIG_HEAD", "git rebase -i main", "git submodule update --init",
    "git bisect good", "git push --force origin main", "git grep -n foo",
    "git -C /x status", "git --no-pager log -1"]


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", HELD)
def test_a_git_command_with_its_own_config_or_command_is_not_line_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", NOT_HELD)
def test_a_plain_git_command_is_line_exempt(command, shell):
    """Must-allow neighbours: options that merely look alike."""
    assert crew_gitallow.line_exempt(command, shell, "all") is True


def test_the_reviewers_alias_case_is_not_promote_exempt(tmp_path, machine, monkeypatch):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    for shell in ("bash", "powershell"):
        assert crew_gitallow.promote_exempt(
            "git -c alias.status='!deploy-prod' status", shell, str(root)) is False
        assert crew_gitallow.promote_exempt("git status", shell, str(root)) is True


@pytest.mark.parametrize("tool,command", [
    ("Bash", "git -c core.sshCommand='terraform apply' push --force origin main"),
    ("Bash", "GIT_SSH_COMMAND='terraform apply' git push --force origin main"),
    ("Bash", "export GIT_SSH_COMMAND='terraform apply'; git push --force origin main"),
    ("Bash", "git push --force --receive-pack='terraform apply' origin main"),
    ("PowerShell", "$env:GIT_SSH_COMMAND = 'terraform apply'; git push --force origin main"),
    ("PowerShell", "git -c core.sshCommand='terraform apply' push --force origin main")])
def test_force_push_carrying_config_stays_refused_with_all(tmp_path, machine, tool, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command, tool)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


def test_xargs_git_carrying_config_stays_refused_with_all(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _evaluate(root, "echo push | xargs git -c core.sshCommand=x")["decision"] == "deny"


# --- review finding 5: PowerShell's single `&` (crew 1.3.75) ----------------------------

@pytest.mark.parametrize("command,shell", [
    ("git status & terraform apply", "powershell"),
    ("git status &terraform apply", "powershell"),
    ("git status & git push", "powershell"),
    ("& git push", "powershell"),
    ("git status & terraform apply", "bash"),
    ("git status &terraform apply", "bash")])
def test_a_single_ampersand_is_never_line_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("command,shell", [
    ("git commit -m 'a & b'", "powershell"),
    ("git commit -m \"a & b\"", "powershell"),
    ("git commit -m 'a & b'", "bash")])
def test_an_ampersand_that_is_not_a_separator_is_line_exempt(command, shell):
    """Must-allow neighbours: a quoted `&` (round 6: a redirection, `&&` or
    any separator is not exempt at all, see `test_round6_*`)."""
    assert crew_gitallow.line_exempt(command, shell, "all") is True


def test_a_powershell_background_and_is_not_promote_exempt(tmp_path, machine, monkeypatch):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    assert crew_gitallow.promote_exempt("git status & deploy-prod", "powershell",
                                        str(root)) is False


# --- review finding 6: `git -C <dir>` reads the target repo's veto (crew 1.3.75) -----

def _other_repo(tmp_path, veto):
    other = make_repo(tmp_path, mode=None, name="other")
    if veto is not None:
        (other / ".crew" / "config.json").write_text(
            json.dumps({"guards": {"git": {"allow": veto}}}), encoding="utf-8")
    return other


@pytest.mark.parametrize("veto", ["off", "ALL"])
def test_a_target_repo_veto_holds_for_git_dash_c(tmp_path, machine, veto):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    other = _other_repo(tmp_path, veto)
    result = _evaluate(root, f"git -C {other.as_posix()} push --force origin main")
    assert result["decision"] == "deny", result


def test_a_target_repo_veto_holds_for_a_relative_dash_c(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    _other_repo(tmp_path, "off")
    assert _evaluate(root, "git -C ../other push --force origin main")["decision"] == "deny"


@pytest.mark.parametrize("veto", [None, "all"])
def test_a_target_repo_without_a_veto_lets_git_dash_c_through(tmp_path, machine, veto):
    """Must-allow neighbour: another repo that does not veto."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    other = _other_repo(tmp_path, veto)
    result = _evaluate(root, f"git -C {other.as_posix()} push --force origin main")
    assert result["decision"] == "allow", result


@pytest.mark.parametrize("command", [
    "git -C {missing} push --force origin main",
    "git --git-dir={other}/.git push --force origin main",
    "git --work-tree {other} push --force origin main",
    "git -C $HOME/x push --force origin main",
    "cd {other} && git push --force origin main"])
def test_a_target_crew_cannot_tell_is_not_exempt(tmp_path, machine, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    other = _other_repo(tmp_path, None)
    command = command.format(other=other.as_posix(), missing=(tmp_path / "nope").as_posix())
    result = _evaluate(root, command)
    assert result["decision"] == "deny", result


def test_the_project_veto_still_holds_for_git_dash_c_elsewhere(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    other = _other_repo(tmp_path, None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": "off"}}}), encoding="utf-8")
    assert _evaluate(root, f"git -C {other.as_posix()} push --force origin main")[
        "decision"] == "deny"


def test_promote_exempt_reads_the_target_repo_veto(tmp_path, machine, monkeypatch):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    vetoing = _other_repo(tmp_path, "off")
    command = f"git -C {vetoing.as_posix()} commit --allow-empty -m 'deploy-prod'"
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is False
    (vetoing / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is True


def test_an_allowlist_without_push_still_refuses_force_push(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["commit", "status"])
    assert _evaluate(root, "git push --force origin main")["decision"] == "deny"


def test_an_allowlist_with_push_lets_force_push_through(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["push"])
    assert _evaluate(root, "git push --force origin main")["decision"] == "allow"


def test_an_allowlist_covers_the_whole_line_or_nothing(tmp_path, machine):
    """Round 4 / 6: `["push"]` lets a lone push through, not a push on a line
    that also runs another command (round 6: no chain is exempt at all)."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["push"])
    assert _evaluate(root, "git push --force origin main; git status")["decision"] == "deny"
    assert _evaluate(root, "git push --force origin main; git push o t")["decision"] == "deny"
    assert _evaluate(root, "git push --force origin main")["decision"] == "allow"


def test_an_unconfirmed_all_still_refuses_force_push(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all", confirmed=False)
    assert _evaluate(root, "git push --force origin main")["decision"] == "deny"


def test_xargs_git_is_never_exempt(tmp_path, machine):
    """Review round 2: the words xargs appends may carry `--receive-pack` or
    `-c`, so `xargs git` is held under every value, `all` included."""
    root = make_repo(tmp_path, mode=None)
    command = "echo push | xargs git"
    assert _evaluate(root, command)["decision"] == "deny"
    _arm(machine, ["push"])
    assert _evaluate(root, command)["decision"] == "deny", "an unseen subcommand is not listed"
    _arm(machine, "all")
    assert _evaluate(root, command)["decision"] == "deny"


def test_report_mode_records_the_exemption(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, "git push --force origin main", mode="report")
    assert result["decision"] is None and not result["note"]
    assert any(r[2] == "report:allow" and r[1].startswith("gitAllow") for r in result["rows"])


# --- what must stay blocked whatever the switch says ----------------------------------

ADMIN = ["gh pr merge 12 --admin --merge", "gh pr merge --admin 12",
         "git push origin feat && gh pr merge 12 --admin"]
PROTECTION = [
    "gh api -X PUT repos/o/r/branches/main/protection/enforce_admins",
    "gh api -X DELETE repos/o/r/branches/main/protection/enforce_admins",
    "gh api -X PUT repos/o/r/branches/main/protection --input p.json",
    "gh api -X POST repos/o/r/rulesets --input r.json",
    "gh api -X DELETE repos/o/r/rulesets/42"]


@pytest.mark.parametrize("value", ["all", ["push", "merge"]])
@pytest.mark.parametrize("command", ADMIN)
def test_admin_merge_stays_blocked_with_the_switch_on(tmp_path, machine, command, value):
    """`gh ... --admin` is `guards.adminMerge`'s, never git's (owner order: never --admin)."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, value)
    result = _evaluate(root, command)
    assert result["decision"] == "deny", result
    assert _rules(result, "adminMerge")
    assert not any(r[0] == "adminMerge" and r[1].startswith("gitAllow") for r in result["rows"])


@pytest.mark.parametrize("command", PROTECTION + ADMIN)
def test_the_switch_never_covers_gh(tmp_path, machine, command, monkeypatch):
    """Branch protection, rulesets and enforce_admins are `gh`, not git: the switch
    exempts none of them in any guard path (cloud guard rows, promote gate)."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert crew_gitallow.line_exempt(command, "bash", "all") is False
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False
    monkeypatch.chdir(root)
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is False
    result = _evaluate(root, command)
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


# --- whole lines (the promote gate's question) ----------------------------------------

@pytest.mark.parametrize("command,shell,setting,expect", [
    ("git commit -m 'deploy-prod'", "bash", "all", True),
    ("git commit -m 'deploy-prod\nsecond line'", "bash", "all", True),
    # Round 6: a heredoc is never read, so it is not exempt.
    ("git commit -F - <<'EOF'\nrun deploy-prod, then cd x\nEOF\n", "bash", "all", False),
    # A substitution running only git still builds a word at run time
    # (review round 2): `git config` output may be `--receive-pack=...`.
    ("git -C /x commit -m \"$(git rev-parse HEAD)\"", "bash", "all", False),
    ("git status && deploy-prod", "bash", "all", False),
    ("git log $(deploy-prod)", "bash", "all", False),
    ("git log `deploy-prod`", "bash", "all", False),
    # A substitution in a redirection target is in no word `hold` reads.
    ("git status > \"$(deploy-prod)\"", "bash", "all", False),
    ("git status > `deploy-prod`", "bash", "all", False),
    ("git log \"`git rev-parse HEAD`\"", "bash", "all", False),
    ("GIT_DIR=/x git push", "bash", "all", False),
    ("git commit -m 'x' | tee log", "bash", "all", False),
    ("git commit -m 'unclosed", "bash", "all", False),
    ("git commit -m x", "bash", "off", False),
    ("git commit -m x; git push", "bash", frozenset({"commit"}), False),
    ("git push", "bash", frozenset({"commit"}), False),
    ("git commit -m x", "bash", frozenset({"commit"}), True),
    ("git commit -m x; git push", "bash", frozenset({"commit", "push"}), False),
    ("git push", "bash", frozenset({"commit", "push"}), True),
    ("git commit -m @'\nit's deploy-prod\n'@", "powershell", "all", False),
    ("git commit -m \"deploy-prod `\"x`\"\"", "powershell", "all", True),
    ("git fetch origin; git status", "powershell", "all", False),
    ("git fetch origin", "powershell", "all", True),
    ("git log | Select-Object -First 3", "powershell", "all", False),
    ("git log | git status", "powershell", "all", False),
    ("git commit -m \"$(deploy-prod)\"", "powershell", "all", False),
    ("git commit -m @\"\n$(deploy-prod)\n\"@", "powershell", "all", False),
    ("& git push", "powershell", "all", False),
    ("git commit -m 'unclosed", "powershell", "all", False)])
def test_line_exempt(command, shell, setting, expect):
    assert crew_gitallow.line_exempt(command, shell, setting) is expect


# --- the promote gate ------------------------------------------------------------------

_NO_REVIEW = {"requireReview": False, "reviewReason": "fixture"}
_VERIFY = {"environments": {
    "prod": {"deploy": "deploy-prod", "requireHuman": True, "rollback": "none",
             "rollbackReason": "fixture", **_NO_REVIEW},
    "remote": {"deploy": "git push prod-remote main", "requireHuman": True,
               "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW}}}


def _gate_repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "T")
    git(root, "config", "commit.gpgsign", "false")
    (root / ".gitignore").write_text(".crew/*\n!.crew/verify.json\n.work/\n", encoding="utf-8")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(json.dumps(_VERIFY, indent=2) + "\n",
                                                encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")
    return root


def run_gate(flavour, root, home, command):
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}, "cwd": str(root)}
    env = crew_fixtures.isolated_home_env(home)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    if flavour == "sh":
        argv = [_BASH, (_SCRIPTS / "promote-gate.sh").as_posix()]
    else:
        env["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File",
                str(_SCRIPTS / "promote-gate.ps1")]
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          check=False, env=env, cwd=str(root), timeout=180)
    return proc.returncode, proc.stderr


FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")),
    pytest.param("ps1", marks=[pytest.mark.skipif(_PWSH is None, reason="no PowerShell 7"),
                               pytest.mark.slow]),
]
_HEREDOC = {"sh": "git commit --allow-empty -m 'notes: run deploy-prod after cd x'",
            "ps1": "git commit --allow-empty -m 'notes: run deploy-prod after cd x'"}
# Round 6: the heredoc / here-string spellings are no longer read, so they stay gated.
_HEREDOC_BODY = {
    "sh": "git commit --allow-empty -F - <<'EOF'\nnotes: run deploy-prod after cd x\nEOF\n",
    "ps1": "git commit --allow-empty -m @'\nnotes: run deploy-prod after cd x\n'@"}


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_gate_blocks_a_commit_naming_a_deploy_with_the_switch_off(tmp_path, machine, flavour):
    assert machine
    root = _gate_repo(tmp_path)
    code, err = run_gate(flavour, root, tmp_path / "home", _HEREDOC[flavour])
    assert code == 2, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_gate_passes_a_commit_naming_a_deploy_with_all(tmp_path, machine, flavour):
    root = _gate_repo(tmp_path)
    _arm(machine, "all")
    code, err = run_gate(flavour, root, tmp_path / "home", _HEREDOC[flavour])
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_gate_still_gates_a_declared_git_deploy_with_all(tmp_path, machine, flavour):
    root = _gate_repo(tmp_path)
    _arm(machine, "all")
    code, err = run_gate(flavour, root, tmp_path / "home", "git push prod-remote main")
    assert code == 2, err
    assert "remote" in err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_gate_still_gates_a_line_that_is_not_only_git(tmp_path, machine, flavour):
    root = _gate_repo(tmp_path)
    _arm(machine, "all")
    sep = " && " if flavour == "sh" else "; "
    code, err = run_gate(flavour, root, tmp_path / "home", f"git status{sep}deploy-prod")
    assert code == 2, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_gate_still_gates_a_heredoc_message_with_all(tmp_path, machine, flavour):
    """Round 6: a heredoc or here-string is not read, so the switch does not
    cover it; the gate judges it as it did before."""
    root = _gate_repo(tmp_path)
    _arm(machine, "all")
    code, err = run_gate(flavour, root, tmp_path / "home", _HEREDOC_BODY[flavour])
    assert code == 2, err


def test_gate_honours_the_allowlist(tmp_path, machine):
    if _BASH is None:
        pytest.skip("no MSYS/POSIX bash")
    root = _gate_repo(tmp_path)
    _arm(machine, ["status"])
    code, err = run_gate("sh", root, tmp_path / "home", _HEREDOC["sh"])
    assert code == 2, err


def test_gate_python_exemption_in_process(tmp_path, machine, monkeypatch):
    """`promote_exempt` on any host, without a shell: the function both gates call."""
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    command = _HEREDOC["sh"]
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is False
    _arm(machine, "all")
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is True
    assert crew_gitallow.promote_exempt("git push prod-remote main", "bash", str(root)) is False
    assert crew_gitallow.promote_exempt(_HEREDOC["ps1"], "powershell", str(root)) is True
    assert crew_gitallow.promote_exempt(_HEREDOC_BODY["sh"], "bash", str(root)) is False
    assert crew_gitallow.promote_exempt(_HEREDOC_BODY["ps1"], "powershell", str(root)) is False


def test_dispatch_prints_the_allow_record_for_powershell(tmp_path, machine, monkeypatch, capsys):
    """promote-gate.ps1's one python call carries the answer (`allow<TAB>...`)."""
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _promote_dispatch.main(["x", "--shell", "powershell", _HEREDOC["ps1"]])
    assert "allow\t" not in capsys.readouterr().out
    _arm(machine, "all")
    _promote_dispatch.main(["x", "--shell", "powershell", _HEREDOC["ps1"]])
    assert capsys.readouterr().out == "allow\tguards.git.allow\n"
    _promote_dispatch.main(["x", "--shell", "bash", "git commit --allow-empty -m 'deploy-prod'"])
    assert "allow\t" not in capsys.readouterr().out, "the bash gate asks crew_gitallow itself"


# --- review round 2 (Codex gpt-6-sol, crew 1.3.75) ----------------------------------------

# BLOCK 1: git takes any unambiguous prefix of a long option.
ABBREVIATED = [
    "git rebase --exe 'terraform apply' HEAD~1",
    "git rebase -i --ex 'terraform apply' HEAD~1",
    "git push --receive='terraform apply' origin main",
    "git push --receive 'terraform apply' origin main",
    "git fetch --upload='terraform apply' origin",
    "git grep --open 'terraform apply' foo",
    "git difftool --extc='terraform apply'",
    "git clone --temp=/tmp/evil a b",
    "git clone --conf=core.sshCommand=x a b"]
NOT_ABBREVIATED = [
    "git push --force-with-lease origin main", "git push --recurse-submodules=check origin main",
    "git rebase --empty=drop main", "git fetch --unshallow origin", "git grep --or foo"]


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", ABBREVIATED)
def test_an_abbreviated_option_that_runs_a_command_is_held(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", NOT_ABBREVIATED)
def test_a_long_option_that_is_no_prefix_of_a_held_one_is_exempt(command, shell):
    """Must-allow neighbours: not a prefix of any held option."""
    assert crew_gitallow.line_exempt(command, shell, "all") is True


@pytest.mark.parametrize("tool,command", [
    ("Bash", "git push --force --receive=x origin main"),
    ("PowerShell", "git push --force --rec=x origin main"),
    ("Bash", "git push --force \"${PACK:---receive-pack=terraform apply}\" origin main"),
    ("Bash", "git push --force $OPT origin main"),
    ("PowerShell", "git push --force $env:OPT origin main"),
    ("Bash", "echo main | xargs git push --force origin"),
    ("Bash", "echo --receive-pack=x | xargs git push --force origin main"),
    ("Bash", "echo push | xargs git")])
def test_a_force_push_crew_cannot_read_whole_stays_refused_with_all(tmp_path, machine, tool,
                                                                     command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command, tool)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


# BLOCK 2: a word built at run time (or appended by xargs) may become any option.
@pytest.mark.parametrize("command,shell", [
    ("git push \"$OPT\" origin main", "bash"),
    ("git push --force \"${PACK:---receive-pack=terraform apply}\" origin main", "bash"),
    ("git \"$X\" status", "bash"),
    ("git push $env:OPT origin main", "powershell"),
    ("git push \"$x\" origin main", "powershell"),
    ("git push @opts origin main", "powershell")])
def test_a_word_built_at_run_time_is_never_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("shell,expect", [("bash", True), ("powershell", False)])
def test_a_bare_at_sign_is_not_a_splat(shell, expect):
    """Must-allow neighbour in bash: git's `@` (HEAD) is a literal. In
    PowerShell a bare `@` is "Unrecognized token" (measured, pwsh 7; review
    round 5's differential test): the line runs nothing, so it is refused."""
    assert crew_gitallow.line_exempt("git push origin @", shell, "all") is expect


# FIX 3: a repo file that is there but cannot be resolved vetoes.
def _symlink_or_skip(link, target, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


def test_a_dangling_repo_config_link_is_a_veto(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    _symlink_or_skip(root / ".crew" / "config.json", tmp_path / "nowhere.json")
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "veto" in got["why"], got


def test_a_dangling_crew_dir_link_is_a_veto(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew").rmdir()
    _symlink_or_skip(root / ".crew", tmp_path / "nowhere", directory=True)
    assert _setting(root) == "off"


def test_a_crew_path_that_is_a_file_is_a_veto(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew").rmdir()
    (root / ".crew").write_text("not a directory", encoding="utf-8")
    assert _setting(root) == "off"


def test_no_crew_dir_at_all_is_no_veto(tmp_path, machine):
    """Must-allow neighbour: a repo with no `.crew/` is absent, not unreadable."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew").rmdir()
    assert _setting(root) == "all"


# FIX 4: a copy of the confirmed file put back with its bytes AND modification
# time (`cp -p`) still reads as changed: the binding carries the change time.
def test_a_copy_put_back_with_its_mtime_is_off(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    confirmed, stat = machine.read_bytes(), os.stat(machine)
    machine.write_text(json.dumps({"guards": {"git": {"allow": "off"}}}), encoding="utf-8")
    time.sleep(0.05)
    machine.write_bytes(confirmed)
    os.utime(machine, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    now = crew_gitallow.file_binding(str(machine))
    bound = _applied(machine)["binding"]
    assert {k: now[k] for k in ("appliedDigest", "appliedSize", "appliedMtimeNs")} == \
        {k: bound[k] for k in ("appliedDigest", "appliedSize", "appliedMtimeNs")}
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "changed since that confirmation" in got["why"], got


def test_a_binding_without_a_change_time_is_not_whole(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    record = _applied(machine)
    binding = dict(record["binding"])
    binding.pop("appliedChangeNs")
    crew_humanonly.write_record(_store(machine), dict(record, binding=binding,
                                                      settled=record["settled"] + 1))
    assert _setting(root) == "off"


def test_an_unknown_change_time_is_off(tmp_path, machine, monkeypatch):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    monkeypatch.setattr(crew_gitallow, "_change_ns", lambda handle, stat: None)
    assert _setting(root) == "off"


# FIX 5: bash's quote removal, not "drop every quote".
@pytest.mark.parametrize("command,expect", [
    ("\"./g'it\" push --force origin main", False),
    ("'g\"it' status", False),
    ("\"git\" push --force origin main", True),
    ("'git' status", True)])
def test_a_quote_inside_the_program_name_is_not_git(command, expect):
    assert crew_gitallow.line_exempt(command, "bash", "all") is expect


# FIX 6: a git finding's scope is not a terraform scope.
@pytest.mark.parametrize("policy", ["ask", "allow"])
@pytest.mark.parametrize("command", ["git push --force origin main", "echo push | xargs git"])
def test_a_force_push_under_a_looser_policy_does_not_crash(tmp_path, machine, policy, command):
    root = make_repo(tmp_path, mode=None)
    overrides = {"guards": {"overrides": {"forcePush": policy}}}
    machine.write_text(json.dumps(overrides), encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps(overrides), encoding="utf-8")
    result = _evaluate(root, command)
    rows = [r for r in result["rows"] if r[0] == "forcePush"]
    assert rows and not any(r[1].startswith("gitAllow") for r in rows), result


# --- review round 3 (Codex gpt-6-sol, crew 1.3.75) ----------------------------------------

# BLOCK 1: a bash word built by brace expansion, a glob or a tilde is run-time.
EXPANDS = [
    "git push --rece{ive-pack,ive-pack}=x origin topic",
    "git push --{receive-pack=x,} origin topic",
    "git push {--receive-pack=x,--force} origin topic",
    "git push --rece* origin topic",
    "git push --rece?ve-pack=x origin topic",
    "git push --rece[i]ve-pack=x origin topic",
    "git push ~ origin topic",
    "git rebase --{exec,} 'deploy-prod' HEAD~1",
    "git {-c,core.sshCommand=deploy-prod} push o topic",
    "git push --receive-pac{k..k}=x origin topic"]
NOT_EXPANDS = [
    "git commit -m 'why? {a,b} * [x] ~'",
    "git commit -m \"fix: why?\"",
    "git commit -m \\*",
    "git log @{u}..HEAD",
    "git rev-parse HEAD@{1}",
    "git push origin HEAD~1:topic",
    "git commit -m '{a,b}'x"]


@pytest.mark.parametrize("command", EXPANDS)
def test_a_word_bash_expands_is_never_exempt(command):
    assert crew_gitallow.line_exempt(command, "bash", "all") is False


@pytest.mark.parametrize("command", NOT_EXPANDS)
def test_a_quoted_or_inert_brace_or_glob_is_exempt(command):
    """Must-allow neighbours: quoted, escaped, or a brace with no `,`/`..`."""
    assert crew_gitallow.line_exempt(command, "bash", "all") is True


@pytest.mark.parametrize("tool,command", [
    ("Bash", "git push -f --rece{ive-pack,ive-pack}=x origin topic"),
    ("Bash", "git push -f --{receive-pack=x,} origin topic"),
    ("Bash", "git push -f --rece* origin topic"),
    ("Bash", "P=x; git push -f --rece{ive-pack,}=$P origin topic"),
    ("Bash", "P='--rece*'; git push -f $P origin topic"),
    ("PowerShell", "git push --force --rece* origin topic")])
def test_a_force_push_with_a_word_the_shell_expands_stays_refused_with_all(
        tmp_path, machine, tool, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command, tool)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


@pytest.mark.parametrize("command", [
    "git push -f origin 'topic*'", "git push -f origin HEAD@{0}:topic"])
def test_a_force_push_with_a_quoted_glob_passes_with_all(tmp_path, machine, command):
    """Must-allow neighbour: quoted, or a brace with no `,`/`..`."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _evaluate(root, command)["decision"] == "allow"


_GATE_EXPANDS = [
    "git push --rece{ive-pack,ive-pack}='deploy-prod' o topic",
    "git rebase --{exec,} 'deploy-prod' HEAD~1",
    "git {-c,core.sshCommand=deploy-prod} push o topic",
    "git send-pack --receive-pack='deploy-prod' o main",
    "git fetch-pack --exec='deploy-prod' o"]


@pytest.mark.parametrize("command", _GATE_EXPANDS)
def test_gate_still_gates_an_expanded_or_plumbing_program_with_all(tmp_path, machine, command):
    if _BASH is None:
        pytest.skip("no MSYS/POSIX bash")
    root = _gate_repo(tmp_path)
    code, err = run_gate("sh", root, tmp_path / "home", command)
    assert code == 2, err
    _arm(machine, "all")
    code, err = run_gate("sh", root, tmp_path / "home", command)
    assert code == 2, err


# FIX 2: the plumbing under push and fetch takes a program too.
PLUMBING = [
    "git send-pack --receive-pack='terraform apply' o main",
    "git send-pack --exec='terraform apply' o main",
    "git send-pack --rec='terraform apply' o main",
    "git fetch-pack --upload-pack='terraform apply' o",
    "git fetch-pack --exec='terraform apply' o"]


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", PLUMBING)
def test_plumbing_that_runs_a_program_is_held(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", ["git send-pack --dry-run o main",
                                     "git fetch-pack --depth=1 o"])
def test_plain_plumbing_is_exempt(command, shell):
    """Must-allow neighbours."""
    assert crew_gitallow.line_exempt(command, shell, "all") is True


# FIX 3: a name exported after a plain assignment carries that value to git;
# so do the names git reads a program or config from beside GIT_*.
@pytest.mark.parametrize("command", [
    "GIT_SSH_COMMAND=x; export GIT_SSH_COMMAND; git push -f origin topic",
    "GIT_SSH_COMMAND=x; declare -x GIT_SSH_COMMAND; git push -f origin topic",
    "GIT_SSH_COMMAND=x; typeset -rx GIT_SSH_COMMAND; git push -f origin topic",
    "HOME=/tmp/evil git push -f origin topic",
    "XDG_CONFIG_HOME=/tmp/evil git push -f origin topic",
    "export PATH=/tmp/evil; git push -f origin topic"])
def test_a_program_variable_reaching_git_stays_refused_with_all(tmp_path, machine,
                                                               monkeypatch, command):
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


@pytest.mark.parametrize("command", [
    "X=1; export X; git push -f origin main",
    "GIT_SSH_COMMAND=x; declare GIT_SSH_COMMAND; git push -f origin main",
    "GIT_SSH_COMMAND=x; export -n GIT_SSH_COMMAND; git push -f origin main",
    "FOO=1 git push -f origin main"])
def test_an_assignment_on_the_line_is_not_exempt_with_all(tmp_path, machine, monkeypatch,
                                                         command):
    """Round 4 changed this from must-allow to must-block: the allowlist exempts a
    line only when every command on it is a plain git command, so an assignment,
    `export` or `declare` beside it (harmless or not) leaves the guards judging."""
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _evaluate(root, command)["decision"] == "deny"


# FIX 4: a `.crew` that is a file, as each host reports it -- Windows says
# FileNotFoundError (and `_dangles` must call it unreadable), POSIX says
# NotADirectoryError (an OSError that is not FileNotFoundError). Each host
# runs the other's path through a stand-in `open`.
def _open_raising(exc_type, monkeypatch):
    real = open

    def fake(path, *args, **kwargs):
        if str(path).replace("\\", "/").endswith("/.crew/config.json"):
            raise exc_type(2, "stand-in", str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_gitallow, "open", fake, raising=False)


def test_a_crew_file_windows_reports_missing_is_a_veto(tmp_path, machine, monkeypatch):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew").rmdir()
    (root / ".crew").write_text("not a directory", encoding="utf-8")
    _open_raising(FileNotFoundError, monkeypatch)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "veto" in got["why"], got


def test_a_crew_file_posix_reports_as_no_directory_is_a_veto(tmp_path, machine, monkeypatch):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    (root / ".crew").rmdir()
    (root / ".crew").write_text("not a directory", encoding="utf-8")
    _open_raising(NotADirectoryError, monkeypatch)
    got = crew_gitallow.settings(str(root))
    assert got["allow"] == "off" and "veto" in got["why"], got


def test_a_missing_repo_config_under_a_real_crew_dir_is_no_veto(tmp_path, machine,
                                                                monkeypatch):
    """Must-allow neighbour: `.crew/` is a directory, the file just is not there."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    _open_raising(FileNotFoundError, monkeypatch)
    assert _setting(root) == "all"


# FIX 5: PowerShell's `--%` hands git the rest with %NAME% expanded at run time.
PS_RUNTIME = [
    "git --% push %PACK% --force origin main",
    "git push %PACK% --force origin main",
    "git --% push --force origin main",
    "git push --force --rece* origin main",
    "git push --force origin ~"]


@pytest.mark.parametrize("command", PS_RUNTIME)
def test_a_powershell_word_expanded_at_run_time_is_never_exempt(command):
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False


@pytest.mark.parametrize("command", [
    "git log -1 --format=%H", "git commit -m '100% done'", "git push origin HEAD~1:topic"])
def test_a_powershell_percent_that_is_no_variable_is_exempt(command):
    """Must-allow neighbours: one `%`, no `%NAME%` pair, a `~` inside a word."""
    assert crew_gitallow.line_exempt(command, "powershell", "all") is True


def test_a_powershell_stop_parsing_force_push_stays_refused_with_all(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, "git --% push --force %PACK% origin main", "PowerShell")
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


# --- review round 4 (Codex gpt-6-sol, crew 1.3.122): a fail-closed allowlist -------------
#
# The design change: `plain_commands` lists what is plain, and anything else is
# not exempt. One reader serves the cloud guard (`line_plan`) and the promote
# gate (`promote_exempt`); `test_both_paths_read_one_corpus_alike` holds them
# to it.

# BLOCK A: bash ANSI-C quoting (`$'...'`) and `$"..."` hid options from the
# cloud guard's own lexer (it decoded them to inert text).
ANSI_C = [
    "git push -f $'\\x2d\\x2dreceive-pack=x' origin topic",
    "git push -f $'\\055\\055receive-pack=x' origin topic",
    "git push -f --rece$'\\x69've-pack=x origin topic",
    "git push -f origin topic $'\\x2d\\x2dreceive-pack=x'",
    "git push -f $\"--receive-pack=x\" origin topic"]
# BLOCK B: a PowerShell expression as an argument; and two more PowerShell
# forms the old reader took as text (round 4, measured with pwsh 7): a
# `` `u{2d} `` escape is a `-`, and a curly quote ends a string.
PS_EXPR = [
    "git push --force (echo '--receive-pack=deploy-prod') o topic",
    "git push --force $(echo '--receive-pack=deploy-prod') o topic",
    "git push --force @(echo '--receive-pack=deploy-prod') o topic",
    "git push --force \"`u{2d}`u{2d}receive-pack=deploy-prod\" o topic",
    "git push --force 'a\u2019 --receive-pack=deploy-prod \u2018' o topic",
    "git push --force {--receive-pack=deploy-prod} o topic",
    "git push --force [string]'--receive-pack=x' o topic",
    "git push --force (deploy-prod) o topic"]
# FIX C: the program word, and a redefinition of git on the same line.
PROGRAM = [
    "/usr/*/git push -f origin topic",
    "/u?r/bin/git push -f origin topic",
    "~/git push -f origin topic",
    "/usr/bin/git push -f origin topic",
    "./git push -f origin topic",
    "git.exe push -f origin topic",
    "git() { sh -c id; }; git push -f origin topic",
    "function git { sh -c id; }; git push -f origin topic",
    "shopt -s expand_aliases; alias git='sh -c id'; git push -f origin topic",
    "command git push -f origin topic",
    "(git push -f origin topic)",
    "{ git push -f origin topic; }"]
PS_PROGRAM = [
    "function git { sh -c id }; git push -f origin topic",
    "Set-Alias git deploy-prod; git push -f origin topic",
    "C:/Program/git.exe push -f origin topic",
    "& git push -f origin topic"]
# FIX D: `git config` that may set an alias or a program a later git command runs.
CONFIG_WRITES = [
    "git config alias.p '!deploy-prod'; git p",
    "git config core.sshCommand deploy-prod; git push o topic",
    "git config --global core.pager deploy-prod; git log",
    "git config --local core.hooksPath /tmp/deploy-prod; git commit -m x",
    "git config diff.external deploy-prod; git diff",
    "git config credential.helper '!deploy-prod'; git fetch o",
    "git config --add sequence.editor deploy-prod; git rebase -i HEAD~2",
    "git config set gpg.program deploy-prod; git commit -S -m x",
    "git config --replace-all core.fsmonitor deploy-prod; git status",
    "git config --edit",
    "git config --ed",
    "git config --unset core.hooksPath; git commit -m x",
    "git config --file .git/config core.editor deploy-prod",
    "git init --template=/tmp/deploy-prod . ; git commit -m x"]
CONFIG_READS = [
    "git config user.name", "git config --get remote.origin.url", "git config --list",
    "git config -l --show-origin", "git config --global --get-regexp '^alias'",
    "git config get core.editor", "git config --type=bool --get core.bare",
    "git config list --name-only"]

# Further forms the allowlist refuses (each pins one rule for a mutation).
BASH_MORE = [
    "git push -f origin @{a..c}", "git push -f origin @{a,b}",
    "git commit -F - <<EOF\n$X\nEOF\n", "git commit -F - <<< $X", "git config edit",
    "git status; (git log -1)"]
PS_MORE = [
    "git push `n origin topic", "git push --force x'--receive-pack=y' o t",
    "git push 'a'b origin topic"]
ROUND4_BLOCK = ([(c, "bash") for c in ANSI_C + PROGRAM + CONFIG_WRITES + BASH_MORE]
                + [(c, "powershell") for c in PS_EXPR + PS_PROGRAM + CONFIG_WRITES + PS_MORE])

# What stays exempt: plain literal lines of git commands (the broad must-allow).
PLAIN = [
    "git commit -m \"fix: x\"", "git commit -m 'wip: x (y) & z'",
    "git push --force-with-lease origin topic", "git push -f origin topic",
    "git push -u origin HEAD", "git rebase -i HEAD~3", "git rebase origin/main",
    "git -C /c/repos/x status", "git --no-pager log -1", "git log --format=%H",
    "git log --oneline -5", "git status --short", "git diff HEAD~1 -- plugin/crew/CONFIG.md",
    "git checkout -b feat/x",
    "git stash push -m \"msg\"", "git tag -a v1.0 -m \"release 1.0\"", "git branch -D old",
    "git push origin +topic", "git reset --hard origin/main", "git clean -fdx",
    "git commit -m 'subject\n\nbody line'"] + CONFIG_READS
# Round 6: everything the reader no longer follows is "cannot tell", never exempt
# -- a chain, a pipe, a newline between commands, a redirection, a heredoc, a
# here-string, a comment, a subshell.
FALLBACK_BASH = [
    "git add -A && git commit -m 'x' && git push origin topic",
    "git fetch origin && git rebase origin/main", "git status; git log -1",
    "git fetch --all\ngit status", "git status 2>&1", "git log | git status",
    "git commit -F - <<'EOF'\nnotes: deploy-prod $X `y`\nEOF\n",
    "git commit -F - <<EOF\nplain body\nEOF\n", "git status # comment", "git status &",
    "git log -1 > out.txt", "git status >>log 2>&1", "git status 2>/dev/null",
    "git status <<<x", "git status\n\ngit log", "git status \\\n-s",
    "(git status)", "git status;", "git status; ; git log", "git status; >", "> x git status",
    "git commit -m x \\\n --amend", "git status;git log", "git status&&git log",
    "git status|git log", "git status>x", "git status<x", "git status&", "git status\ngit log"]
FALLBACK_PS = [
    "git add -A; git commit -m 'x'", "git fetch origin && git rebase origin/main",
    "git status; git log -1", "git fetch --all\ngit status", "git status 2>&1",
    "git push origin main *>&1", "git log -1 > out.txt", "git status 3>&1",
    "git fetch || git status", "git status # comment", "git status | git log",
    "git commit -m @'\nit's $deploy-prod\n'@", "git status `\n-x", "git status &&\ngit log",
    "git status;", "(git status)", "git status\n\ngit log", "git status;git log",
    "git status>x", "git status\ngit log", "git status|git log"]
BASH_PLAIN = [
    "git log @{u}..HEAD", "git rev-parse HEAD@{1}", "git commit -m \"say \\\"hi\\\"\"",
    "git commit -m \\*", "\"git\" status", "'git' status", "\\git status",
    "git status \n", "\ngit status"]
PS_PLAIN = [
    "git -C C:\\repos\\x status", "git commit -m \"a `\"b`\" c\"", "git commit -m 'it''s'",
    "git push `-f origin topic", "git commit -m 'two\nlines'"]
ROUND4_ALLOW = ([(c, "bash") for c in PLAIN + BASH_PLAIN]
                + [(c, "powershell") for c in PLAIN + PS_PLAIN])


@pytest.mark.parametrize("command,shell", ROUND4_BLOCK)
def test_round4_must_block_is_not_line_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False


@pytest.mark.parametrize("command,shell", [(c, "bash") for c in FALLBACK_BASH]
                         + [(c, "powershell") for c in FALLBACK_PS])
def test_round6_what_the_reader_does_not_follow_is_not_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is False
    assert crew_gitallow.line_git_commands(command, shell) is None


@pytest.mark.parametrize("command", [c.split(";")[0].strip() for c in CONFIG_WRITES]
                         + ["git config --unknown-flag a b", "git config --file x a b",
                            "git config --unknown-flag user.name"])
def test_round6_a_config_or_program_command_alone_is_not_exempt(command):
    """Round 6 refuses every chain, so the `hold` rules are held to each
    command on its own: the chain-free head of every CONFIG_WRITES line."""
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt(command, shell, "all") is False, command


@pytest.mark.parametrize("command,shell", ROUND4_ALLOW)
def test_round4_plain_git_lines_stay_exempt(command, shell):
    assert crew_gitallow.line_exempt(command, shell, "all") is True


@pytest.mark.parametrize("tool,command", [("Bash", c) for c in ANSI_C + PROGRAM]
                         + [("PowerShell", c) for c in PS_EXPR + PS_PROGRAM])
def test_round4_force_push_stays_refused_with_all(tmp_path, machine, tool, command):
    """The reviewer's repros, through the cloud guard (deny off / allow on before)."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, command, tool)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


@pytest.mark.parametrize("command", CONFIG_WRITES[:2])
def test_round4_config_write_is_not_promote_exempt(tmp_path, machine, monkeypatch, command):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    for shell in ("bash", "powershell"):
        assert crew_gitallow.promote_exempt(command, shell, str(root)) is False
    assert crew_gitallow.promote_exempt("git commit -m deploy-prod", "bash", str(root)) is True
    assert crew_gitallow.promote_exempt("git config user.name; git commit -m deploy-prod",
                                        "bash", str(root)) is False


@pytest.mark.parametrize("command", CONFIG_WRITES[:2])
def test_round4_gate_still_gates_a_config_write_with_all(tmp_path, machine, command):
    if _BASH is None:
        pytest.skip("no MSYS/POSIX bash")
    root = _gate_repo(tmp_path)
    _arm(machine, "all")
    code, err = run_gate("sh", root, tmp_path / "home", command)
    assert code == 2, err


# One corpus, both paths: the cloud guard exempts a line's force push exactly
# when the promote gate's reader calls the line exempt.
PARITY = ([(c, "Bash") for c in ANSI_C + PROGRAM[:6] + EXPANDS[:4]
           + ["git push -f origin topic", "git push -f origin topic && git status",
              "git push -f origin 'topic*'", "git push -f origin HEAD@{0}:topic",
              "git push -f \"$OPT\" origin topic", "git push -f origin topic | tee x",
              "git config core.sshCommand x; git push -f origin topic"]]
          + [(c, "PowerShell") for c in PS_EXPR + PS_PROGRAM[2:]
             + ["git push --force origin topic", "git push --force origin topic; git status",
                "git push --force $env:OPT origin topic", "git --% push --force %P% o t"]])


@pytest.mark.parametrize("tool,command", PARITY)
def test_both_paths_read_one_corpus_alike(tmp_path, machine, tool, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    shell = "powershell" if tool == "PowerShell" else "bash"
    line = crew_gitallow.line_exempt(command, shell, "all")
    result = _evaluate(root, command, tool)
    cloud = any(r[0] == "forcePush" and r[1].startswith("gitAllow") for r in result["rows"])
    assert cloud is line, (line, result)


# --- review round 5: redirections ------------------------------------------------------
#
# BLOCK 1: bash reads `>&-` / `<&-` as "close the descriptor" and hands the rest
# of that word (after blanks too) to the command as an argument, so
# `git push >&---receive-pack=deploy-prod origin main` runs git with
# `--receive-pack=deploy-prod` (measured with a shim git under bash 5).
# BLOCK 2: an fd prefix (`2>&1`) between `git` and the subcommand was left in
# the word list, so `-c` / `--exec-path` / `--receive-pack` were never seen.
# The fix: the allowlist accepts a redirection only after the subcommand and
# only in the plain forms `_bash_redirect_problem` lists.

REDIRECT_BLOCK = [
    "git push >&---receive-pack=deploy-prod origin main",
    "git push >& ---receive-pack=deploy-prod origin main",
    "git push <&-\"--receive-pack=deploy-prod\" origin main",
    "git push 2>&---receive-pack=deploy-prod origin main",
    "git push -f >&---receive-pack=deploy-prod origin main",
    "git 2>&1 -c core.sshCommand=x push -f o t",
    "git 2>&1 push --receive-pack=deploy-prod o m",
    "git 2>/dev/null --exec-path=/tmp/x status",
    "git 2>&1 -c alias.p='!printf HIT' p"]
# Each pins one rule of `_bash_redirect_problem` (and the line-end check).
REDIRECT_RULES = {
    "before": "git 2>/dev/null status",
    "var": "git status {v}>out",
    "notarget": "git status >",
    "plain": "git status > \"$OUT\"",
    "dash": "git status > -x",
    "dupfile": "git status >&out",
    "dupascii": "git status 2>&١",
    "op": "git status < in",
    "close": "git status >&-",
    "trailing": "git status &&",
    "leading": "&& git status",
    "empty": "git fetch ||& git log origin",
}
# Round 6: no redirection is read at all, so none of these is exempt now.
REDIRECT_FALLBACK = [
    "git status 2>&1", "git log -1 > out.txt", "git status >>log 2>&1",
    "git status 2>/dev/null", "git status 1>&2", "git -C /x status 2>&1",
    "git push -f origin topic 2>&1", "git commit -F - <<'EOF'\nx\nEOF\n",
    "git status; git log -1 >out", "git fetch &&\ngit status", "git log | git status"]


@pytest.mark.parametrize("command", REDIRECT_BLOCK + list(REDIRECT_RULES.values()))
def test_round5_a_redirection_crew_cannot_read_is_not_exempt(command):
    assert crew_gitallow.line_exempt(command, "bash", "all") is False


@pytest.mark.parametrize("command", REDIRECT_FALLBACK)
def test_round5_a_plain_redirection_is_not_exempt_either_since_round6(command):
    assert crew_gitallow.line_exempt(command, "bash", "all") is False


def test_round5_an_fd_prefix_is_never_read_as_an_argument_or_dropped():
    """Round 6: `git status 2>&1` is not read at all (it was read as
    `status` with the descriptor dropped)."""
    assert crew_gitallow.line_git_commands("git status 2>&1", "bash") is None
    assert crew_gitallow.line_git_commands("git status \"2\">/dev/null", "bash") is None
    assert crew_gitallow.line_git_commands("git status \"2\"", "bash") == [["status", "2"]]


@pytest.mark.parametrize("command", ["git 2>&1 push origin main", "git 2>err.txt status"])
def test_round5_a_powershell_redirection_before_the_subcommand_is_not_exempt(command):
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False
    after = "git push origin main 2>&1"
    assert crew_gitallow.line_exempt(after, "powershell", "all") is False


# Found by the differential test (`test_git_allow_differential.py`): lines the
# reader accepted that real pwsh 7 refuses to parse, so they ran nothing -- an
# over-read, refused now so the reader and PowerShell agree exactly.
PS_PARSE_ERRORS = {
    "quoted": "\"git\" status",
    "single": "'git' status *>&1",
    "dup2": "git status 1>&2",
    "trailing": "git status &&",
    "leading": "&& git status",
    "double": "git status; && git log",
    "at": "git push origin @",
    "herestring": "@'\ngit\n'@ status",
    "joined": "git status`\n-x",
}


@pytest.mark.parametrize("command", list(PS_PARSE_ERRORS.values()))
def test_round5_a_powershell_line_pwsh_cannot_parse_is_not_exempt(command):
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False


@pytest.mark.parametrize("command", [
    "git status 3>&1", "git status &&\ngit log -1", "git fetch || git status", "git status `\n-x",
    "git status; git log -1"])
def test_round5_a_powershell_neighbour_that_parses_is_not_exempt_since_round6(command):
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False


def _split(text):
    import crew_guards  # pylint: disable=import-outside-toplevel
    return crew_guards._CommandSplitter(text).split()[0]  # pylint: disable=protected-access


def _gate_read(text):
    import crew_guards  # pylint: disable=import-outside-toplevel
    cmds = []
    crew_guards._GateReader(text, 0, cmds).read()  # pylint: disable=protected-access
    return cmds


@pytest.mark.parametrize("text,expect", [
    ("git push >&---receive-pack=x origin main",
     [["git", "push", "--receive-pack=x", "origin", "main"]]),
    ("git push >& -y z", [["git", "push", "y", "z"]]),
    ("a x <&-\"q\" z", [["a", "x", "\"q\"", "z"]]),
    ("a x >&2y z", [["a", "x", "z"]]),
    ("a x 2>&1 z", [["a", "x", "z"]]),
    ("a x \"2\">f z", [["a", "x", "\"2\"", "z"]]),
    ("git status >\ngit log", [["git", "status"], ["git", "log"]]),
])
def test_round5_the_splitter_reads_redirections_as_bash_does(text, expect):
    """Measured with bash 5: `>&-` takes the `-` (after blanks too) and the
    rest of that word is an argument; `"2">` is an argument, `2>` is not."""
    assert _split(text) == expect


@pytest.mark.parametrize("text,expect", [
    ("echo \"2\">f", [["echo", "2"]]),
    ("echo \"\"2>f", [["echo", "2"]]),
    ("echo ٢>f", [["echo", "٢"]]),
    ("echo 2>f", [["echo"]]),
])
def test_round5_the_gate_reader_strips_an_fd_prefix_as_the_splitter_does(text, expect):
    assert _gate_read(text) == expect


def test_round5_force_push_with_a_closed_descriptor_stays_refused_with_all(tmp_path, machine):
    """The reviewer's cloud-guard repro: deny off -> allow on, before."""
    root = make_repo(tmp_path, mode=None)
    command = "git push -f >&---receive-pack=deploy-prod origin main"
    assert _evaluate(root, command)["decision"] == "deny"
    _arm(machine, "all")
    result = _evaluate(root, command)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


@pytest.mark.parametrize("command", [
    "git push >&---receive-pack=deploy-prod origin main",
    "git 2>&1 push --receive-pack=deploy-prod o m"])
def test_round5_gate_still_gates_a_redirection_repro_with_all(tmp_path, machine, command):
    if _BASH is None:
        pytest.skip("no MSYS/POSIX bash")
    root = _gate_repo(tmp_path)
    code, err = run_gate("sh", root, tmp_path / "home", command)
    assert code == 2, err
    _arm(machine, "all")
    code, err = run_gate("sh", root, tmp_path / "home", command)
    assert code == 2, err


# --- review round 6 (Codex gpt-6-sol, crew 1.3.122): ONE plain command ------------------
#
# BLOCK 1: a WORD-LESS command (only redirects) skipped every redirect check:
# `git status 'a[$(touch x)]'; > $((_))` ran the substitution through `$_`.
# BLOCK 2: a heredoc delimiter holding backslash-newline or backslash-space.
# BLOCK 3: a line continuation splitting an fd prefix: `git 2\<NL>>&1 push ...`.
# BLOCK 4: PowerShell backtick before `*` `?` `[`: `` git push `* origin main ``.
# The fix: the reader follows none of those shapes. A line is exempt only as
# ONE simple command with plain literal words (`FALLBACK_*` above holds the
# convenience forms that fell back); these are the reviewer's repros.

_BS, _NL = "\\", "\n"
R6_BASH = [
    "git status 'a[$(touch /tmp/pwn6c)]'; > $((_))",
    "git status; > $((X))", "git status; > ${X@P}", "git status; <<<$((X))",
    "git status; <<EOF\n$((X))\nEOF\n", "git status; (> $((X)))", "git status; > *",
    "git status; > ~", "git status; > -x", "git status; {v}>x", "git status; >$X",
    "> $((X))", ">$X", "git status\n> $((X))",
    f"git status <<E{_BS}{_NL}OF{_NL}EOF{_NL}deploy-prod{_NL}exit{_NL}E{_BS}{_NL}",
    f"git status <<E{_BS} OF{_NL}EOF{_NL}deploy-prod{_NL}E{_BS} OF{_NL}",
    f"git 2{_BS}{_NL}>&1 push --receive-pack=deploy-prod origin main",
    f"git 1{_BS}{_NL}>&2 push --force o m",
    f"git status{_BS}{_NL}", f"git{_BS}{_NL} status",
    "git status; >", "git status; ; git log"]
R6_PS = [
    "git push `* origin main", "git push `? origin main", "git push `[a] origin main",
    "git push `n origin main", "git push `0 origin main", "git status; > $((_))",
    "git status; >$x", "> $x", "git status\n> $x", "git push \"a`*\" origin main",
    "git status; ; git log", "git status; >"]


@pytest.mark.parametrize("text", [
    "git 2\\\n>&1 push --receive-pack=deploy-prod origin main",
    "git 1\\\n>&2 push --force o m", "echo 2\\\n<in", "echo {v}\\\n>x"])
def test_round6_the_splitters_refuse_a_continuation_inside_an_fd_prefix(text):
    """BLOCK 3: bash joins `2\\<NL>>&1` into `2>&1`; the readers took `2` for
    an argument. Both shared readers now say "cannot tell"."""
    import crew_guards  # pylint: disable=import-outside-toplevel
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        _split(text)
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        _gate_read(text)
    assert _split("echo 2 \\\n>f") == [["echo", "2"]], "a blank before the continuation is fine"


@pytest.mark.parametrize("text", [
    f"git status <<E{_BS}{_NL}OF{_NL}EOF{_NL}deploy-prod{_NL}exit{_NL}E{_BS}{_NL}",
    f"git status <<E{_BS} OF{_NL}EOF{_NL}deploy-prod{_NL}E{_BS} OF{_NL}",
    f"cat <<E{_BS};x{_NL}body{_NL}E;x{_NL}"])
def test_round6_the_splitters_refuse_a_heredoc_delimiter_with_a_dangling_backslash(text):
    """BLOCK 2: bash reads `<<E\\<NL>OF` as the delimiter `EOF` and `<<E\\ OF`
    as `E OF`, so the lines the readers took for the body ran as commands."""
    import crew_guards  # pylint: disable=import-outside-toplevel
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        _split(text)
    with pytest.raises(crew_guards._Unsure):  # pylint: disable=protected-access
        _gate_read(text)
    paired = f"cat <<E{_BS}{_BS}{_NL}body{_NL}E{_BS}{_NL}"
    assert _split(paired)[0] == ["cat"], "an escaped backslash is a whole delimiter"


@pytest.mark.parametrize("command", R6_BASH)
def test_round6_bash_blocks_are_not_exempt(command):
    assert crew_gitallow.line_exempt(command, "bash", "all") is False
    assert crew_gitallow.line_git_commands(command, "bash") is None


@pytest.mark.parametrize("command", R6_PS)
def test_round6_powershell_blocks_are_not_exempt(command):
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False
    assert crew_gitallow.line_git_commands(command, "powershell") is None


@pytest.mark.parametrize("tool,command", [("Bash", c) for c in [
    "git push --force o m; > $((_))",
    f"git push -f origin main <<E{_BS}{_NL}OF{_NL}EOF{_NL}deploy-prod{_NL}E{_BS}{_NL}",
    f"git 2{_BS}{_NL}>&1 push -f --receive-pack=deploy-prod origin main",
    f"git 1{_BS}{_NL}>&2 push --force o m"]]
    + [("PowerShell", "git push --force `* origin main"),
       ("PowerShell", "git push --force o m; > $x")])
def test_round6_force_push_stays_refused_with_all(tmp_path, machine, tool, command):
    """The reviewer's repros through the cloud guard: deny with the switch off
    and still deny, with no gitAllow row, with it on."""
    root = make_repo(tmp_path, mode=None)
    assert _evaluate(root, command, tool, raw=True)["decision"] == "deny"
    _arm(machine, "all")
    result = _evaluate(root, command, tool, raw=True)
    assert result["decision"] == "deny", result
    assert not any(r[1].startswith("gitAllow") for r in result["rows"]), result


@pytest.mark.parametrize("shell,command", [
    ("bash", "git status"), ("bash", "git push --force-with-lease origin topic"),
    ("bash", "git commit -m 'a\nb'"), ("bash", "git log HEAD@{1}"),
    ("powershell", "git status"), ("powershell", "git push `-f origin topic"),
    ("powershell", "git commit -m 'a\nb'")])
def test_round6_one_plain_command_is_still_exempt(shell, command):
    assert crew_gitallow.line_exempt(command, shell, "all") is True


def test_round6_one_plain_force_push_passes_with_all(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    for tool in ("Bash", "PowerShell"):
        assert _evaluate(root, "git push --force origin main", tool)["decision"] == "allow"


# --- review round 8 (Codex gpt-6-sol): edge blanks, ls-remote --exec, --attr-source ----

@pytest.mark.parametrize("command", [
    "git status\r", "git status\r\n", "git push --force origin main\x0c",
    "git push --force\x1f", "git status ", "\x0cgit status", "git status\x0b",
    "git status ", "git status\u0085", " git status"])
def test_round8_a_bash_line_with_a_stray_edge_character_is_not_read(command):
    """`str.strip()` ate these, so crew read `git status` while bash ran git
    with the word `status<CR>` (or a command named `<FF>git`)."""
    assert crew_gitallow.plain_commands(command, "bash") is None
    assert crew_gitallow.line_exempt(command, "bash", "all") is False


@pytest.mark.parametrize("command", [
    "git status\r", "git status\r\n", "git status\x1f", "\x1cgit status",
    "git commit -m 'a\r\nb'", "git status "])
def test_round8_a_powershell_line_with_a_stray_character_is_not_read(command):
    assert crew_gitallow.plain_commands(command, "powershell") is None
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_round8_plain_edge_blanks_are_still_trimmed(shell):
    assert crew_gitallow.plain_commands("  git status \t\n", shell) == [["git", "status"]]


@pytest.mark.parametrize("args", [
    ["ls-remote", "--exec=deploy-prod", "/tmp/x"], ["ls-remote", "--exe=deploy-prod", "x"],
    ["ls-remote", "--exec", "deploy-prod", "x"], ["ls-remote", "--upload", "deploy-prod", "x"]])
def test_round8_ls_remote_exec_is_a_program_option(args):
    assert crew_gitallow.hold(args)


def test_round8_attr_source_takes_a_value():
    args = ["--attr-source", "commit", "push", "--force", "origin", "main"]
    assert crew_gitallow.subcommand(args) == "push"


# --- review round 9 (Codex gpt-6-sol): CR, for-each-repo, case, -C .., %X Y% ---------------

def _dispatch(command, monkeypatch, capsys, root):
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _promote_dispatch.main(["x", "--shell", "powershell", command])
    return capsys.readouterr().out


@pytest.mark.parametrize("command", [
    "git status\rgh workflow run prod", "git status\r\rgh workflow run prod",
    "git status\r\ngh workflow run prod", "git status\r"])
def test_round9_a_carriage_return_is_refused_not_stripped_on_the_git_allow_path(
        tmp_path, machine, monkeypatch, capsys, command):
    """The dispatcher stripped every CR before asking `_git_allowed`, so
    `git status<CR>gh workflow run prod` read as one `git statusgh ...`."""
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert "guards.git.allow" not in _dispatch(command, monkeypatch, capsys, root)


@pytest.mark.parametrize("command", ["git status", "git status\n", "git status\r\n"])
def test_round9_a_final_line_terminator_is_still_allowed(
        tmp_path, machine, monkeypatch, capsys, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _dispatch(command, monkeypatch, capsys, root) == "allow\tguards.git.allow\n"


@pytest.mark.parametrize("args", [
    ["for-each-repo", "--config=x.repos", "--", "-c", "alias.x=!deploy-prod", "x"],
    ["for-each-repo", "--config", "x.repos", "status"], ["for-each-repo"],
    ["-C", ".", "for-each-repo", "--config=x", "status"], ["web--browse", "x"]])
def test_round9_subcommands_that_run_a_git_or_a_program_are_held(args):
    assert crew_gitallow.hold(args)
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt("git " + " ".join(args), shell, "all") is False


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("command", ["git STATUS", "git Status", "git PUSH --force origin main"])
def test_round9_git_is_case_sensitive_so_an_allowlist_does_not_match_another_case(
        shell, command):
    assert crew_gitallow.subcommand(command.split()[1:]) is crew_gitallow.UNSEEN
    assert crew_gitallow.line_exempt(command, shell, frozenset({"status", "push"})) is False
    assert crew_gitallow.line_exempt("git status", shell, frozenset({"status"})) is True


def test_round9_a_chained_dot_dot_through_a_symlink_is_not_a_target(tmp_path):
    """`git -C link -C ..` changes into the link, then `..`: a POSIX git lands in the
    link TARGET's parent, a lexical reading in the link's parent. Crew cannot tell
    which, so it does not tell: the target is UNSEEN and the line is off."""
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "base" / "sub").mkdir(parents=True)
    try:
        os.symlink(tmp_path / "a" / "b" / "c", tmp_path / "base" / "link",
                   target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    base = str(tmp_path / "base")
    assert crew_gitallow.resolve_target(base, ["link", ".."]) is crew_gitallow.UNSEEN
    assert crew_gitallow.resolve_target(base, ["link/.."]) is crew_gitallow.UNSEEN
    assert crew_gitallow.line_targets([["-C", "link", "-C", "..", "status"]], base) is None
    assert crew_gitallow.resolve_target(base, ["sub", ".."]) == os.path.normpath(base)
    assert crew_gitallow.resolve_target(base, ["link"]) == os.path.normpath(
        os.path.join(base, "link"))


@pytest.mark.parametrize("command", [
    "git log '%X Y%'", "git log --format='%a b%'", "git log %X%", "git log '%X Y%' --oneline"])
def test_round9_a_powershell_percent_variable_with_a_space_is_not_read(command):
    assert crew_gitallow.plain_commands(command, "powershell") is None
    assert crew_gitallow.plain_commands("git log --format=%H", "powershell") == [
        ["git", "log", "--format=%H"]]


# --- review round 10 (Codex gpt-6-sol): %..% across words, helper options, abbreviated force ---

@pytest.mark.parametrize("command", [
    "git status %X Y%", "git log --format=%h --format=%an", "git log %A %B%",
    "git log 'a %X' 'Y%'"])
def test_round10_a_powershell_percent_pair_across_words_is_not_read(command):
    """`%X Y%` is one cmd.exe variable named `X Y`; split over two words the
    per-word `%[^%]+%` match saw neither half."""
    assert crew_gitallow.plain_commands(command, "powershell") is None
    assert crew_gitallow.line_exempt(command, "powershell", "all") is False


@pytest.mark.parametrize("command", ["git log --format=%H", "git status 100%", "git log -p"])
def test_round10_one_percent_or_none_is_still_read(command):
    assert crew_gitallow.plain_commands(command, "powershell") is not None
    assert crew_gitallow.line_exempt(command, "powershell", "all") is True


HELPERS = [
    ["status", "--help"], ["log", "--ext-diff"], ["diff", "--ext-diff"], ["show", "--ext-diff"],
    ["diff", "--textconv"], ["blame", "--textconv", "f"], ["cat-file", "--textconv", "HEAD:f"],
    ["log", "--paginate"], ["status", "--hel"], ["log", "--ext"], ["-p", "status"],
    ["--paginate", "log"], ["--help", "status"], ["-C", ".", "-p", "diff"], ["help", "status"],
    ["log", "--open-files-in-pager"]]


@pytest.mark.parametrize("args", HELPERS)
def test_round10_an_option_that_launches_a_helper_program_is_held(args):
    assert crew_gitallow.hold(args)
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt("git " + " ".join(args), shell, "all") is False


@pytest.mark.parametrize("args", [
    ["log", "-p"], ["diff", "--stat"], ["log", "--no-ext-diff"], ["diff", "--no-textconv"],
    ["log", "--pretty=oneline", "--oneline"], ["show", "-p", "HEAD"], ["status", "-h"],
    ["log", "--", "--help"]])
def test_round10_an_ordinary_option_is_not_a_helper(args):
    assert crew_gitallow.hold(args) is None
    assert crew_gitallow.line_exempt("git " + " ".join(args), "bash", "all") is True


ABBREVIATED_FORCE = [
    "git push --force-with-leas origin main", "git push --force-with-lease=main origin main",
    "git push --mirror", "git push --mirr origin", "git push --delete origin topic",
    "git push --delet origin topic", "git push --forc origin main", "git push origin +main"]


@pytest.mark.parametrize("command", ABBREVIATED_FORCE)
def test_round10_the_cloud_guard_reads_an_abbreviated_force_push(tmp_path, command):
    """git takes any unambiguous prefix of a long option, so `--force-with-leas`
    is `--force-with-lease`; `--mirror` and `--delete` overwrite or remove refs."""
    assert cloud_guard._git_force_push(command.split()[1:])  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert _rules(_evaluate(root, command), "forcePush"), command


@pytest.mark.parametrize("command", [
    "git push origin main", "git push -u origin topic", "git push --follow-tags",
    "git push --dry-run origin main", "git push --no-verify origin main",
    "git push --tags", "git push --set-upstream origin topic"])
def test_round10_an_ordinary_push_is_still_no_force_push(tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


# --- review round 11 (Codex gpt-6-sol): remote deletion by other spellings, helper launchers ---

DELETING_PUSH = [
    "git push origin :b", "git push :b", "git push origin main :b", "git push -d origin b",
    "git push -vd origin b", "git push --prune origin", "git push --all --prune",
    "git push --all --prune origin", "git push --prun origin", "git --attr-source x push -f",
    "git --attr-source x push origin :b", "git --super-prefix x push --delete origin b"]


@pytest.mark.parametrize("command", DELETING_PUSH)
def test_round11_the_cloud_guard_reads_a_push_that_deletes_a_remote_ref(tmp_path, command):
    """Measured with git 2.56 against a throwaway bare remote: `:b`, `origin :c`,
    `-d`, `--prune <refspec>` and `--all --prune` each deleted a remote branch."""
    assert cloud_guard._git_force_push(command.split()[1:])  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert _rules(_evaluate(root, command), "forcePush"), command


@pytest.mark.parametrize("command", [
    "git push HEAD", "git push origin HEAD", "git push origin main", "git push origin main:main",
    "git push --tags", "git push --follow-tags", "git push -u origin topic",
    "git push --dry-run origin main", "git push -n origin main", "git push -v origin main",
    "git push --porcelain origin main", "git --attr-source x push origin main",
    "git push origin refs/heads/a:refs/heads/b"])
def test_round11_an_ordinary_push_is_still_no_force_push(tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


def test_round11_the_two_global_value_option_sets_match():
    assert cloud_guard._GIT_VALUE_OPTS == crew_gitallow._GIT_VALUE_OPTS  # pylint: disable=protected-access


LAUNCHERS = [
    ["difftool"], ["difftool", "-y"], ["mergetool"], ["mergetool", "-y"],
    ["credential", "fill"], ["credential", "approve"],
    ["merge", "-s", "zzz", "o"], ["merge", "-szzz", "o"], ["merge", "-ns", "zzz", "o"],
    ["merge", "--strategy", "zzz", "o"], ["merge", "--strategy=zzz", "o"],
    ["merge", "--strat", "zzz", "o"], ["pull", "-s", "zzz"], ["pull", "--strategy=zzz", "o"],
    ["rebase", "-s", "zzz", "main"], ["rebase", "--strategy", "zzz", "main"],
    ["-C", ".", "merge", "-s", "zzz", "o"], ["cat-file", "--filters", ":h.txt"],
    ["cat-file", "--filter", ":h.txt"]]


@pytest.mark.parametrize("args", LAUNCHERS)
def test_round11_a_helper_launcher_is_held(args):
    """Measured: with a `git-merge-zzz` on PATH, `merge|pull -s zzz` ran it;
    `difftool`, `mergetool` and `credential fill` run the configured program."""
    assert crew_gitallow.hold(args)
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt("git " + " ".join(args), shell, "all") is False


@pytest.mark.parametrize("args", [
    ["merge", "o"], ["merge", "-X", "theirs", "o"], ["merge", "-Xours", "o"],
    ["merge", "--strategy-option=ours", "o"], ["merge", "--squash", "o"], ["merge", "--stat", "o"],
    ["merge", "--no-ff", "o"], ["merge", "-m", "msg", "o"], ["pull", "--ff-only"],
    ["pull", "--rebase"], ["rebase", "main"], ["rebase", "-X", "ours", "main"],
    ["rebase", "--abort"], ["status", "-s"], ["log", "-s"], ["diff", "--stat"],
    ["show", "-s", "HEAD"], ["log", "--", "-s"], ["cat-file", "blob", ":h.txt"],
    ["cat-file", "-p", "HEAD"], ["cat-file", "-t", "HEAD"]])
def test_round11_an_ordinary_merge_or_read_is_not_a_launcher(args):
    assert crew_gitallow.hold(args) is None
    assert crew_gitallow.line_exempt("git " + " ".join(args), "bash", "all") is True


# --- review round 12 (Codex gpt-6-sol): trailing space, malformed deploy, unknown subs ------

def test_round12_toplevel_strips_only_the_line_terminator(monkeypatch, tmp_path):
    """`git -C 'dir '` printed the path ending in a space then a newline; `strip()`
    read the veto from the directory without the space."""
    spaced = str(tmp_path / "dir ").replace("\\", "/")

    class Done:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = (spaced + "\n").encode()

    monkeypatch.setattr(crew_gitallow.crew_common, "resolve_tool", lambda name: "git")
    monkeypatch.setattr(crew_gitallow.subprocess, "run", lambda *a, **k: Done())
    assert crew_gitallow._toplevel("x") == os.path.realpath(spaced)  # pylint: disable=protected-access
    if os.name == "nt":  # a Windows name cannot end in CR, so CRLF is a line terminator there
        Done.stdout = (spaced + "\r\n").encode()
        assert crew_gitallow._toplevel("x") == os.path.realpath(spaced)  # pylint: disable=protected-access


@pytest.mark.parametrize("environments", [
    {"prod": {"deploy": None}}, {"prod": {"deploy": 5}}, {"prod": {"deploy": ["a", 3]}},
    {"prod": {"deploy": {"x": "y"}}}, {"prod": "not-an-object"}])
def test_round12_a_malformed_deploy_is_not_promote_exempt(
        tmp_path, machine, monkeypatch, environments):
    """The gate's `_promote_match.matching` refuses such a map (Unreadable); the
    exemption used to skip the bad value and answer True for `git push prod main`."""
    import _promote_match  # pylint: disable=import-outside-toplevel
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    command = "git push prod main"
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is True
    (root / ".crew" / "verify.json").write_text(
        json.dumps({"environments": environments}), encoding="utf-8")
    with pytest.raises(_promote_match.Unreadable):
        _promote_match.matching(environments, True, command)
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is False
    assert crew_gitallow.promote_exempt("git status", "powershell", str(root)) is False


UNKNOWN_SUBS = [
    ["zzz"], ["svn", "dcommit"], ["p4", "submit"], ["gui"], ["citool"], ["Status"],
    ["-C", ".", "zzz"], ["-c", "x=y", "zzz"], ["co", "main"], ["flow", "init"]]


@pytest.mark.parametrize("args", UNKNOWN_SUBS)
def test_round12_an_unknown_subcommand_is_held(args):
    """Measured: a `git-zzz` on PATH ran for `git zzz`; an alias runs whatever it names."""
    assert crew_gitallow.hold(args)
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt("git " + " ".join(args), shell, "all") is False


@pytest.mark.parametrize("args", [
    ["status"], ["--version"], ["push", "origin", "main"], ["log", "--oneline"],
    ["-C", ".", "commit", "-m", "x"], ["diff", "--stat"], ["cherry-pick", "x"],
    ["rev-parse", "HEAD"], ["worktree", "list"], ["ls-remote", "origin"], ["switch", "-c", "b"]])
def test_round12_a_git_builtin_is_not_held_as_unknown(args):
    assert crew_gitallow.hold(args) is None
    assert crew_gitallow.line_exempt("git " + " ".join(args), "bash", "all") is True


@pytest.mark.parametrize("command", ["git push origin b:+b", "git push origin main:+main"])
def test_round12_a_plus_in_the_destination_is_not_a_force_push(tmp_path, command):
    """Measured with git 2.56 against a throwaway bare remote: `main:+b` created a branch
    named `+b` and `main:+main` was rejected as a non-fast-forward of the branch `+main`;
    only a leading `+` on the refspec forces. The cloud guard reads it the same way."""
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


# --- review round 13 (Codex gpt-6-sol, crew 1.3.116 re-review) ----------------------------

HELPER_URLS = [
    ["ls-remote", "ext::echo deploy-prod"], ["clone", "ext::sh -c id"], ["fetch", "fd::3"],
    ["fetch", "foo::bar"], ["fetch", "--", "ext::x"], ["clone", "--upload-pack=a", "ext::x"],
    ["ls-remote", "--repo=ext::x"], ["push", "origin", "ext::x"]]


@pytest.mark.parametrize("args", HELPER_URLS)
def test_round13_a_remote_helper_url_is_held(args):
    """Measured with GIT_ALLOW_PROTOCOL=ext on git 2.56: `git ls-remote 'ext::echo x'` ran
    echo. `fd::` and any `<helper>::` (git-remote-<helper> from PATH) run a program too."""
    assert crew_gitallow.hold(args)
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_exempt("git " + " ".join(f"'{a}'" for a in args),
                                         shell, "all") is False


@pytest.mark.parametrize("args", [
    ["ls-remote", "origin"], ["clone", "https://example.invalid/x.git"], ["log", "a:b"],
    ["fetch", "git@example.invalid:x/y.git"], ["push", "origin", "main:main"]])
def test_round13_an_ordinary_remote_is_not_a_helper_url(args):
    assert crew_gitallow.hold(args) is None


def test_round13_toplevel_reads_bytes_and_keeps_a_carriage_return(monkeypatch, tmp_path):
    """Text mode turned a lone CR into LF before the strip, so `repo<CR>` resolved to its
    sibling `repo` and that repo's `allow: off` was missed."""
    seen = {}

    class Done:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = b""

    def fake_run(*_args, **kwargs):
        seen.update(kwargs)
        return Done()

    monkeypatch.setattr(crew_gitallow.crew_common, "resolve_tool", lambda name: "git")
    monkeypatch.setattr(crew_gitallow.subprocess, "run", fake_run)
    base = str(tmp_path / "repo").replace("\\", "/")
    Done.stdout = base.encode() + b"\n"
    assert crew_gitallow._toplevel("x") == os.path.realpath(base)  # pylint: disable=protected-access
    assert not seen.get("text") and not seen.get("universal_newlines")
    # A POSIX host, whatever this one is: the CR before the LF is part of the name.
    monkeypatch.setattr(crew_gitallow.os, "name", "posix")
    Done.stdout = base.encode() + b"\r\n"
    assert crew_gitallow._toplevel("x") == os.path.realpath(base + "\r")  # pylint: disable=protected-access


def test_round13_a_duplicate_deploy_key_is_not_promote_exempt(tmp_path, machine, monkeypatch):
    """Plain json keeps the LAST duplicate: `deploy` read as `echo deploy-prod` while the
    strict reader the gate uses refuses the map (CaseTwins)."""
    import _promote_match  # pylint: disable=import-outside-toplevel
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    command = "git push prod main"
    text = ('{"environments": {"prod": {"deploy": "git push prod main", '
            '"deploy": "echo deploy-prod", "requireHuman": true, "rollback": "none", '
            '"rollbackReason": "x", "requireReview": false, "reviewReason": "x"}}}')
    (root / ".crew" / "verify.json").write_text(text, encoding="utf-8")
    with pytest.raises(_promote_match.CaseTwins):
        json.loads(text, object_pairs_hook=_promote_match.no_case_twins)
    assert crew_gitallow.promote_exempt(command, "bash", str(root)) is False


def test_round13_the_dispatch_reader_is_strict(tmp_path, monkeypatch):
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    import _promote_match  # pylint: disable=import-outside-toplevel
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".crew").mkdir()
    (tmp_path / ".crew" / "verify.json").write_text(
        '{"environments": {"p": {"deploy": "a", "deploy": "b"}}}', encoding="utf-8")
    with pytest.raises(_promote_match.CaseTwins):
        _promote_dispatch.working_envs()


def test_round13_a_duplicate_key_in_the_machine_file_is_unreadable(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"guards": {"git": {"allow": "off"}}, "guards": {"git": {"allow": "all"}}}',
                    encoding="utf-8")
    state, _value, _binding = crew_gitallow.read_layer(str(path))
    assert state == crew_gitallow.UNREADABLE


def test_round13_a_duplicate_key_in_the_repo_config_is_a_problem(tmp_path):
    root = make_repo(tmp_path, mode=None)
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / "config.json").write_text(
        '{"environments": {"nonProd": ["dev"], "nonProd": ["*"]}}', encoding="utf-8")
    assert "does not parse" in cloud_guard.environments_config(str(root))["problem"]


@pytest.mark.parametrize("command", [
    "git push --force-if-includes origin main", "git push --force-if origin main",
    "git push -o +ticket=123 origin main", "git push --push-option +x origin main",
    "git push -od x origin main", "git push origin -- -f", "git push -uo +x origin main",
    "git push -o x origin main"])
def test_round13_an_inert_option_or_an_option_value_is_no_force_push(tmp_path, command):
    """git 2.56: `--force-if-includes` alone left a non-fast-forward push rejected (inert
    without a lease); `-o`'s value is a push option, not a refspec."""
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


@pytest.mark.parametrize("command", [
    "git push --force-if-includes --force-with-lease origin main", "git push -o x origin +main",
    "git push -fo x origin main", "git push -o x -d origin b", "git push -- +main",
    "git push origin -- :b"])
def test_round13_a_force_after_an_option_value_is_still_a_force_push(tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:])  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert _rules(_evaluate(root, command), "forcePush"), command


def test_round13_a_value_taking_global_value_is_not_a_pager_option():
    assert crew_gitallow.hold(["-C", "-p", "status"]) is None
    assert crew_gitallow.hold(["-p", "status"])
    assert crew_gitallow.hold(["-C", "x", "-p", "status"])
    assert crew_gitallow.line_exempt("git -C -p status", "bash", "all") is True


def test_round13_a_tilde_inside_a_C_value_is_a_name_not_an_expansion():
    for value in ("foo~bar", "PROGRA~1"):
        commands = crew_gitallow.line_git_commands(f"git -C {value} status", "bash")
        assert crew_gitallow.line_targets(commands, ".") is not None
    assert crew_gitallow.line_targets([["-C", "~x", "status"]], ".") is not None  # round 14


def test_round13_a_newer_builtin_is_held_when_the_installed_git_lacks_it(monkeypatch):
    """git 2.53 lacks `format-rev`, `history`, `survey`, `url-parse`: they would run a
    `git-<name>` found on PATH."""
    monkeypatch.setattr(crew_gitallow, "_PROBED", {"set": frozenset(("status",))})
    assert crew_gitallow.hold(["history", "x"])
    monkeypatch.setattr(crew_gitallow, "_PROBED", {"set": frozenset(("history",))})
    assert crew_gitallow.hold(["history", "x"]) is None
    assert crew_gitallow.hold(["status"]) is None


def test_round13_a_duplicate_key_in_the_pins_block_is_a_problem(tmp_path):
    root = make_repo(tmp_path, mode=None)
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / "config.json").write_text(
        '{"cloud": {"aws": ["1"]}, "cloud": {"aws": ["*"]}}', encoding="utf-8")
    assert "does not parse" in cloud_guard.cloud_pins(str(root))[1]


def test_round13_a_duplicate_key_in_a_plan_summary_is_unknown(tmp_path):
    import hashlib  # pylint: disable=import-outside-toplevel
    data = b"saved plan bytes"
    (tmp_path / ".crew" / "tfplan").mkdir(parents=True)
    (tmp_path / "p.tfplan").write_bytes(data)
    text = ('{"plan": "p.tfplan", "workspace": "qa", "environment": null, '
            '"deletes": ["a.b"], "deletes": []}')
    (tmp_path / ".crew" / "tfplan" / (hashlib.sha256(data).hexdigest() + ".json")).write_text(
        text, encoding="utf-8")
    ctx = {"cd": False, "switch": False, "engaged": True}
    found = [f for f in cloud_guard.scan("bash", "terraform apply p.tfplan", ctx=ctx) if f.scope]
    got = cloud_guard._tf_destroy(found[-1].scope, str(tmp_path), str(tmp_path), ctx)  # pylint: disable=protected-access
    assert got[0] == "unknown", got


def test_round13_a_duplicate_deploy_key_is_not_promote_exempt_committed(
        tmp_path, machine, monkeypatch):
    """The same duplicate key in the COMMITTED map (read from a blob while the working map
    is dirty) must be refused by the strict reader too."""
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    import _promote_match  # pylint: disable=import-outside-toplevel
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    text = '{"environments": {"p": {"deploy": "git push prod main", "deploy": "echo x"}}}'
    (root / "dup.json").write_text(text, encoding="utf-8")
    blob = git(root, "hash-object", "-w", "dup.json")
    monkeypatch.setenv("CREW_HEAD_MAP", blob)
    monkeypatch.setenv("CREW_MAP_DIRTY", "1")
    with pytest.raises(_promote_match.CaseTwins):
        _promote_dispatch.committed_envs()
    _arm(machine, "all")
    assert crew_gitallow.promote_exempt("git push prod main", "bash", str(root)) is False


# --- review round 14 (Codex gpt-6-sol re-review of crew 1.3.122) -------------------------

def test_round14_the_cwd_repo_veto_is_read(tmp_path, machine):
    """BLOCK 1: a command with no `-C` runs in the directory the line runs in, and
    that repo's veto is read; a cwd crew cannot read as a work tree is off."""
    project = make_repo(tmp_path, mode=None)
    cwd_repo = make_repo(tmp_path, mode=None, name="cwdrepo")
    _arm(machine, "all")
    line = "git push -f origin main"
    assert crew_gitallow.line_plan(line, "bash", str(project), str(cwd_repo))["allow"] == "all"
    (cwd_repo / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"git": {"allow": "off"}}}), encoding="utf-8")
    plan = crew_gitallow.line_plan(line, "bash", str(project), str(cwd_repo))
    assert plan["allow"] == "off" and not plan["subs"]
    # the same veto through the cloud guard: the hook's cwd is the vetoing repo
    result = cloud_guard.evaluate(str(project), "Bash", line, {"cwd": str(cwd_repo)}, "block")
    assert result["decision"] == "deny", result
    # a veto in the cwd does not touch a command that acts elsewhere with -C
    assert crew_gitallow.line_plan(f"git -C {project.as_posix()} status", "bash",
                                   str(project), str(cwd_repo))["allow"] == "all"
    # a cwd that is not a work tree (or does not exist) is "could not tell": off
    plain = tmp_path / "plain"
    plain.mkdir()
    for base in (plain, tmp_path / "nope"):
        assert crew_gitallow.line_plan(line, "bash", str(project), str(base))["allow"] == "off"
    assert crew_gitallow.line_plan(line, "bash", str(project), "")["allow"] == "off"
    assert crew_gitallow.line_targets([["status"]], "") is None


def test_round14_a_cwd_inside_the_project_is_not_a_second_repo(tmp_path, machine):
    project = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    sub = project / "src"
    assert crew_gitallow.line_plan("git status", "bash", str(project), str(sub))["allow"] == "all"


@pytest.mark.parametrize("deploy,shell", [
    (r"g\it push prod main", "bash"), ('"g"it push prod main', "bash"),
    ("'g'it push prod main", "bash"), ("g`it push prod main", "powershell")])
def test_round14_an_escaped_git_deploy_is_not_promote_exempt(
        tmp_path, machine, monkeypatch, deploy, shell):
    """BLOCK 2: the shell reads the escaped deploy as `git`, so the declared-deploy
    check must too (it fails closed on an escape or quote that hides `git`)."""
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    verify = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))
    verify["environments"]["remote"]["deploy"] = deploy
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    for command in ("git push prod main", deploy):
        assert crew_gitallow.promote_exempt(command, shell, str(root)) is False, command
    # a deploy that is not git at all, escaped or not, leaves the exemption alone
    verify["environments"]["remote"]["deploy"] = r"d\eploy-prod --x"
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
    assert crew_gitallow.promote_exempt("git status", shell, str(root)) is True


def test_round14_a_config_value_after_C_is_not_config_injection():
    assert crew_gitallow.hold(["-C", "-c", "status"]) is None
    assert crew_gitallow.hold(["-C", "x", "-c", "a=b", "status"])
    assert crew_gitallow.hold(["-c", "a=b", "status"])
    assert crew_gitallow.hold(["--git-dir", "-c", "status"]) is None
    assert crew_gitallow.hold(["-C", "x", "--exec-path=y", "status"])


@pytest.mark.parametrize("args", [
    ["push", "-o", "--receive-pack=x", "origin", "main"],
    ["push", "-o", "ext::echo", "origin", "main"],
    ["push", "--push-option", "--receive-pack=x", "origin", "main"],
    ["push", "--push-option=ext::echo", "origin", "main"],
    ["push", "-oext::echo", "origin", "main"],
    ["push", "-fo", "--receive-pack=x", "origin", "main"]])
def test_round14_a_push_option_value_is_not_an_option_or_a_url(args):
    assert crew_gitallow.hold(args) is None, args


@pytest.mark.parametrize("args", [
    ["push", "--receive-pack=x", "origin", "main"],
    ["push", "-o", "x", "--receive-pack=y", "origin", "main"],
    ["push", "-o", "x", "ext::echo", "main"],
    ["push", "-o", "x", "--", "ext::echo", "main"],
    ["push", "--", "-o", "ext::echo"], ["push", "-ofoo", "--receive-pack=x", "origin"],
    ["fetch", "-o", "--upload-pack=x", "origin"]])
def test_round14_a_real_option_or_url_beside_a_push_option_is_still_held(args):
    assert crew_gitallow.hold(args), args


@pytest.mark.parametrize("command", [
    "git push -ofoo origin main", "git push -ouf origin main", "git push -uofoo origin main",
    "git push -ofd origin main"])
def test_round14_an_attached_push_option_value_is_no_force_push(tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


@pytest.mark.parametrize("command", [
    "git push -fofoo origin main", "git push -dofoo origin main", "git push -ufofoo origin main",
    "git push -of -f origin main"])
def test_round14_a_force_before_an_attached_push_option_value_is_still_a_force_push(
        tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:])  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert _rules(_evaluate(root, command), "forcePush"), command


def test_round14_a_quoted_tilde_in_a_C_value_is_a_literal_name():
    """The readers refuse an UNQUOTED leading `~` (it expands), so one that reaches
    `target_dirs` was quoted or escaped and is a plain directory name."""
    for command, shell in (("git -C '~repo' status", "bash"), ('git -C "~repo" status', "bash"),
                           (r"git -C \~repo status", "bash"), ("git -C '~repo' status", "powershell")):
        commands = crew_gitallow.line_git_commands(command, shell)
        assert crew_gitallow.line_targets(commands, ".") is not None, command
        assert crew_gitallow.target_dirs(commands[0]) == ("~repo",), command
    for shell in ("bash", "powershell"):
        assert crew_gitallow.line_git_commands("git -C ~repo status", shell) is None


# --- review round 15 (Codex gpt-6-sol re-review of crew 1.3.122, head 67ea035f1) -----------

def _declare(root, deploy):
    verify = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))
    verify["environments"]["remote"]["deploy"] = deploy
    (root / ".crew" / "verify.json").write_text(json.dumps(verify), encoding="utf-8")


@pytest.mark.parametrize("deploy,shell", [
    ('"git" push prod main', "bash"), ("$'git' push prod main", "bash"),
    ("${x}it push prod main", "bash"), (r"\git push prod main", "bash"),
    ("g$@it push prod main", "bash"), ("$(echo git) push prod main", "bash"),
    ("`echo git` push prod main", "bash"), ("sudo ${x}it push prod main", "bash"),
    ("FOO=1 $X push prod main", "bash"), ("cd x && ${x}it push prod main", "bash"),
    ("git push prod main && echo \"done\"", "bash"),
    ('"git" push prod main', "powershell"), ("& ${x}it push prod main", "powershell")])
def test_round15_a_declared_git_deploy_hidden_by_any_spelling_exempts_nothing(
        tmp_path, machine, monkeypatch, deploy, shell):
    """BLOCK 1: the round 14 fail-closed branch was an `elif`, taken only when the pattern
    did NOT match, so `"git"` and `$'git'` (which match) reached the containment test,
    failed it and were exempted. The test no longer depends on the match."""
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    _declare(root, deploy)
    assert crew_gitallow.promote_exempt("git push prod main", shell, str(root)) is False, deploy
    assert crew_gitallow.promote_exempt("git status", shell, str(root)) is False, deploy


@pytest.mark.parametrize("deploy", [
    "deploy-prod --x", "./deploy.sh prod", r"d\eploy-prod --x", "deploy-prod --tag $VERSION",
    "make -C \"infra dir\" deploy", "FOO=1 deploy-prod", "echo 'git is nice' > /dev/null"])
def test_round15_a_declared_deploy_that_is_not_git_leaves_the_exemption_alone(
        tmp_path, machine, monkeypatch, deploy):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    _declare(root, deploy)
    assert crew_gitallow.promote_exempt("git status", "bash", str(root)) is (
        "git is nice" not in deploy), deploy


def test_round15_a_plain_declared_git_deploy_still_exempts_what_it_does_not_contain(
        tmp_path, machine, monkeypatch):
    root = _gate_repo(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CREW_HEAD_MAP", "")
    monkeypatch.setenv("CREW_MAP_DIRTY", "")
    _arm(machine, "all")
    _declare(root, "git push prod main")
    assert crew_gitallow.promote_exempt("git status", "bash", str(root)) is True
    assert crew_gitallow.promote_exempt("git push prod main", "bash", str(root)) is False


@pytest.mark.parametrize("name", ["GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR",
                                  "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE", "GIT_NAMESPACE"])
def test_round15_a_repo_redirecting_variable_in_the_hooks_env_reads_as_off(
        tmp_path, machine, monkeypatch, name):
    """BLOCK 2: a plain `git push -f` the hook runs inherits GIT_DIR and its kin, so git
    acts on the repo they name while `_toplevel` (which strips them) reads the cwd's.
    Crew cannot tell whose veto applies: the line reads as off (fail closed)."""
    project = make_repo(tmp_path, mode=None)
    cwd_repo = make_repo(tmp_path, mode=None, name="cwdrepo")
    _arm(machine, "all")
    line = "git push -f origin main"
    assert crew_gitallow.line_plan(line, "bash", str(project), str(cwd_repo))["allow"] == "all"
    monkeypatch.setenv(name, str(tmp_path / "vetoed" / ".git"))
    plan = crew_gitallow.line_plan(line, "bash", str(project), str(cwd_repo))
    assert plan["allow"] == "off" and not plan["subs"], name
    assert crew_gitallow.line_targets([["push"]], str(cwd_repo)) is None
    result = cloud_guard.evaluate(str(project), "Bash", line, {"cwd": str(cwd_repo)}, "block")
    assert result["decision"] == "deny", result
    # an empty value does not redirect git (an empty GIT_OBJECT_DIRECTORY makes git itself
    # fail with "gitfile does not point to a valid repository", so that one reads as off anyway)
    monkeypatch.setenv(name, "")
    want = "off" if name == "GIT_OBJECT_DIRECTORY" else "all"
    assert crew_gitallow.line_plan(line, "bash", str(project), str(cwd_repo))["allow"] == want


@pytest.mark.parametrize("command", [
    "git push -4f origin main", "git push -f4 origin main", "git push -6f origin main",
    "git push -46f origin main", "git push -u4f origin main", "git push origin main -4f"])
def test_round15_a_short_bundle_with_a_digit_is_still_a_force_push(tmp_path, command):
    """BLOCK 3 (pre-existing on main): `-4` and `-6` are real push flags, so `-4f` forces
    the push; the bundle pattern read letters only."""
    assert cloud_guard._git_force_push(command.split()[1:])  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert _rules(_evaluate(root, command), "forcePush"), command


@pytest.mark.parametrize("command", [
    "git push -4 origin main", "git push -46 origin main", "git push -u4 origin main",
    "git push -4u origin main", "git push origin main"])
def test_round15_a_short_bundle_with_a_digit_and_no_f_is_no_force_push(tmp_path, command):
    assert cloud_guard._git_force_push(command.split()[1:]) is None  # pylint: disable=protected-access
    root = make_repo(tmp_path, mode=None)
    assert not _rules(_evaluate(root, command), "forcePush"), command


def test_round15_a_letters_only_bundle_is_still_read_by_the_original_pattern():
    """The digit pattern needs a digit, so `-uf` is caught only by the harness-anchored line."""
    assert cloud_guard._git_force_push(["push", "-uf", "origin"])  # pylint: disable=protected-access
    assert cloud_guard._git_force_push(["push", "-fu", "origin"])  # pylint: disable=protected-access


@pytest.mark.parametrize("args", [
    ["-c", "remote.origin.mirror=true", "push", "origin"],
    ["-c", "remote.origin.push=+HEAD:refs/heads/main", "push", "origin"]])
def test_round15_a_config_that_forces_a_push_is_no_force_finding_but_is_held(args):
    """FIX 4 (pre-existing residual, documented in CONFIG.md): the force is in config the
    guard does not read, so there is no force finding; `hold` refuses any `-c`, so the
    switch never exempts such a line."""
    assert cloud_guard._git_force_push(args) is None  # pylint: disable=protected-access
    assert crew_gitallow.hold(args)


# --- the mutation table ----------------------------------------------------------------

def test_every_mutation_anchor_is_present_exactly_once():
    import gitallow_mutations  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in gitallow_mutations.GITALLOW_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as fh:
            text = fh.read().replace("\r\n", "\n")
        assert text.count(find) == 1, label
        assert test.startswith("tests/test_git_allow.py::"), label
        name = test.split("::", 1)[1].split("[", 1)[0]
        assert name in globals(), label


def test_the_switch_is_documented_in_config_md():
    text = (pathlib.Path(__file__).resolve().parents[1] / "CONFIG.md").read_text(encoding="utf-8")
    assert f"`{KEY}`" in text
    assert os.path.isfile(_SCRIPTS / "crew_gitallow.py")
