"""crew 1.3.71: `guards.git.allow`, the owner's switch that lets git commands past
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
import crew_mass
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


def _receipt(path, value, state="applied", settled=None):
    """An applied (or revoked) confirm-config record for `guards.git.allow`."""
    stamp = time.time() if settled is None else settled
    record = {"change_id": crew_humanonly.new_change_id(), "layer": "machine",
              "target": crew_humanonly.target_key(str(path)), "key": KEY, "value": value,
              "state": state, "created": stamp, "settled": stamp, "confirmations": []}
    crew_humanonly.write_record(crew_humanonly.store_dir(str(path)), record)
    return record


def _arm(machine, value, confirmed=True, extra=None):
    body = {"guards": {"git": {"allow": value}}}
    if extra:
        body["guards"].update(extra)
    machine.write_text(json.dumps(body), encoding="utf-8")
    if confirmed:
        _receipt(machine, value)


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
    (["-C", "/x", "-c", "a=b", "--no-pager", "Commit", "-m", "x"], "commit"),
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
    _receipt(machine, None, state="revoked", settled=time.time() + 5)
    assert _setting(root) == "off"


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
    root = make_repo(tmp_path, mode=None)
    _arm(machine, value)
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


def test_a_crew_write_back_to_off_revokes_the_receipt(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    gpath = str(machine)
    cid = crew_confirm_config.propose("machine", KEY, global_path=gpath, value="all")["change_id"]
    crew_confirm_config.confirm(cid, "user-prompt", "p1", global_path=gpath)
    crew_confirm_config.confirm(cid, "user-prompt", "p2", global_path=gpath)
    crew_config.write_global_config({KEY: "off"}, path=gpath)
    machine.write_text(json.dumps({"guards": {"git": {"allow": "all"}}}), encoding="utf-8")
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


# --- the cloud guard: forcePush and the mass guard's git counts ----------------------

def _evaluate(root, command, tool="Bash", mode="block"):
    mass = crew_mass.settings(str(root))
    return cloud_guard.evaluate(str(root), tool, command.replace("\\", "/"),
                                {"cwd": str(root)}, mode, mass)


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
    ("PowerShell", "git -C C:/x push -f origin main; git status")])
def test_force_push_passes_with_all_in_powershell(tmp_path, machine, tool, command):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    assert _evaluate(root, command, tool)["decision"] == "allow"


def test_an_allowlist_without_push_still_refuses_force_push(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["commit", "status"])
    assert _evaluate(root, "git push --force origin main")["decision"] == "deny"


def test_an_allowlist_with_push_lets_force_push_through(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, ["push"])
    assert _evaluate(root, "git push --force origin main")["decision"] == "allow"


def test_an_unconfirmed_all_still_refuses_force_push(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all", confirmed=False)
    assert _evaluate(root, "git push --force origin main")["decision"] == "deny"


def test_xargs_git_unseen_subcommand_passes_only_under_all(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    command = "echo push | xargs git"
    assert _evaluate(root, command)["decision"] == "deny"
    _arm(machine, ["push"])
    assert _evaluate(root, command)["decision"] == "deny", "an unseen subcommand is not listed"
    _arm(machine, "all")
    assert _evaluate(root, command)["decision"] == "allow"


def test_report_mode_records_the_exemption(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    _arm(machine, "all")
    result = _evaluate(root, "git push --force origin main", mode="report")
    assert result["decision"] is None and not result["note"]
    assert any(r[2] == "report:allow" and r[1].startswith("gitAllow") for r in result["rows"])


def _mass_repo(tmp_path, machine, files=40):
    assert machine
    root = make_repo(tmp_path, mode=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"mass": {"enabled": True}}}), encoding="utf-8")
    folder = root / "gen"
    folder.mkdir()
    for index in range(files):
        (folder / f"f{index}.txt").write_text("x", encoding="utf-8")
    git(root, "add", "-A")
    return root


def test_a_mass_commit_stops_with_the_switch_off(tmp_path, machine):
    root = _mass_repo(tmp_path, machine)
    result = _evaluate(root, "git commit -qm big")
    assert result["decision"] in ("ask", "deny"), result
    assert _rules(result, crew_mass.MASS_CREATE)


def test_a_mass_commit_passes_with_all(tmp_path, machine):
    root = _mass_repo(tmp_path, machine)
    _arm(machine, "all", extra={"mass": {"enabled": True}})
    result = _evaluate(root, "git commit -qm big")
    assert result["decision"] == "allow", result


def test_a_mass_commit_passes_with_commit_listed(tmp_path, machine):
    root = _mass_repo(tmp_path, machine)
    _arm(machine, ["commit"])
    assert _evaluate(root, "git commit -qm big")["decision"] == "allow"


def test_a_mass_commit_stops_when_commit_is_not_listed(tmp_path, machine):
    root = _mass_repo(tmp_path, machine)
    _arm(machine, ["push"])
    assert _evaluate(root, "git commit -qm big")["decision"] in ("ask", "deny")


def test_the_rest_of_the_line_is_still_judged(tmp_path, machine):
    """`all` loosens git findings only: the `rm` beside the commit still stops."""
    root = _mass_repo(tmp_path, machine)
    _arm(machine, "all")
    big = (root / "gen").as_posix()
    result = _evaluate(root, f"git commit -qm big && rm -rf {big}")
    assert result["decision"] in ("ask", "deny"), result
    assert _rules(result, crew_mass.MASS_DELETE)
    assert not _rules(result, crew_mass.MASS_CREATE)


def test_the_mass_tamper_check_is_untouched(tmp_path, machine):
    root = _mass_repo(tmp_path, machine)
    _arm(machine, "all")
    result = _evaluate(root, "git commit -qm x > .git/crew/mass-approvals/abc.json")
    assert result["decision"] == "deny"


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
    ("git commit -F - <<'EOF'\nrun deploy-prod, then cd x\nEOF\n", "bash", "all", True),
    ("git -C /x commit -m \"$(git rev-parse HEAD)\"", "bash", "all", True),
    ("git status && deploy-prod", "bash", "all", False),
    ("git log $(deploy-prod)", "bash", "all", False),
    ("git log `deploy-prod`", "bash", "all", False),
    ("git log \"`git rev-parse HEAD`\"", "bash", "all", True),
    ("GIT_DIR=/x git push", "bash", "all", False),
    ("git commit -m 'x' | tee log", "bash", "all", False),
    ("git commit -m 'unclosed", "bash", "all", False),
    ("git commit -m x", "bash", "off", False),
    ("git commit -m x; git push", "bash", frozenset({"commit"}), False),
    ("git commit -m x; git push", "bash", frozenset({"commit", "push"}), True),
    ("git commit -m @'\nit's deploy-prod\n'@", "powershell", "all", True),
    ("git commit -m \"deploy-prod `\"x`\"\"", "powershell", "all", True),
    ("git fetch origin; git status", "powershell", "all", True),
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
_HEREDOC = {"sh": "git commit --allow-empty -F - <<'EOF'\nnotes: run deploy-prod after cd x\nEOF\n",
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
