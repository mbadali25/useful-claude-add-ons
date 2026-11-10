"""crew 1.3.35: the mass delete / create / change stop (`crew_mass.py`).

CLAUDE.md: a hook that can block carries a committed must-block / must-allow
suite, sabotage-tested. Every must-block here has a must-allow beside it (the
count one below the limit, the regenerable directory, the filtered SQL), and
each guard branch has a mutation in `mass_mutations.py` that must turn one of
these red.

The cases run the real parser and the real file system and `git`: `evaluate`
with a throwaway repo under `tmp_path`. Terraform, which is not installed, goes
through an injected runner. Nothing touches the real machine config:
`crew_state.GLOBAL_CONFIG_PATH` and `crew_config.GLOBAL_CONFIG_PATH` point
under `tmp_path`, and no case installs anything.
"""
import json
import os
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import cloud_guard
import crew_config
import crew_mass
import crew_state
from review_fixtures import git
from scope_fixtures import make_repo


@pytest.fixture(name="machine")
def _machine(tmp_path, monkeypatch):
    """A machine config location under tmp_path, for every reader."""
    path = tmp_path / "home" / ".claude" / "crew" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    for name in ("CI", "CREW_UNATTENDED"):
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture(name="repo")
def _repo(tmp_path, machine):
    assert machine
    root = make_repo(tmp_path, mode=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"mass": {"enabled": True}}}), encoding="utf-8")
    return root


def _fill(folder, count, prefix="f", text="x"):
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (folder / f"{prefix}{index}.txt").write_text(text, encoding="utf-8")
    return folder


def _run(repo, command, tool="Bash", data=None, **extra):
    command = command.replace("\\", "/")  # a Windows path in a bash line
    payload = dict({"cwd": str(repo)}, **(data or {}))
    mass = crew_mass.settings(str(repo))
    return cloud_guard.evaluate(str(repo), tool, command, payload, "block", mass, **extra)


def _mass_rows(result):
    return sorted(r[0] for r in result["rows"] if r[0] in crew_mass.RULES)


def _stops(repo, command, rule=None, tool="Bash", data=None):
    result = _run(repo, command, tool, data)
    rows = _mass_rows(result)
    assert rows, f"not stopped: {command!r} -> {result}"
    assert result["decision"] in ("ask", "deny"), result
    if rule:
        assert rule in rows, (rule, rows)
    return result


def _passes(repo, command, tool="Bash", data=None):
    result = _run(repo, command, tool, data)
    assert not _mass_rows(result), f"stopped: {command!r} -> {result}"
    assert result["decision"] == "allow", result
    return result


def _commit_all(repo, message="more"):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


def _on_branch(repo, name="feat"):
    """origin/main = the current commit; `repo` moves to branch `name`."""
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-qb", name)


# --- the switch ------------------------------------------------------------------

def test_off_by_default_nothing_is_judged(tmp_path, machine):
    assert machine
    root = make_repo(tmp_path, mode=None)
    folder = _fill(root / "big", 40).as_posix()
    mass = crew_mass.settings(str(root))
    assert mass["armed"] is False
    result = cloud_guard.evaluate(str(root), "Bash", f"rm -rf {folder}", {"cwd": str(root)},
                                  "block", mass)
    assert result["decision"] == "allow" and not _mass_rows(result)


def test_the_machine_switch_arms_it(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    machine.write_text(json.dumps({"guards": {"mass": {"enabled": True}}}), encoding="utf-8")
    assert crew_mass.settings(str(root))["armed"] is True
    _stops(root, f"rm -rf {_fill(root / 'big', 12)}", crew_mass.MASS_DELETE)


@pytest.mark.parametrize("value", ["yes", 1, None, "true", [True]])
def test_a_switch_that_is_not_exactly_true_is_off(tmp_path, machine, value):
    root = make_repo(tmp_path, mode=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"mass": {"enabled": value}}}), encoding="utf-8")
    assert crew_mass.settings(str(root))["armed"] is False


def test_an_unreadable_config_leaves_it_off_and_never_raises(tmp_path, machine):
    root = make_repo(tmp_path, mode=None)
    machine.write_text("{not json", encoding="utf-8")
    (root / ".crew" / "config.json").write_text("[1, 2", encoding="utf-8")
    mass = crew_mass.settings(str(root))
    assert mass["armed"] is False
    assert mass["limits"]["files"] == crew_mass.DEFAULT_LIMITS


def test_the_cloud_guard_off_still_lets_mass_stop_a_delete(repo, tmp_path):
    folder = _fill(tmp_path / "w", 12).as_posix()
    result = cloud_guard.evaluate(str(repo), "Bash", f"rm -rf {folder}", {"cwd": str(repo)},
                                  "block", crew_mass.settings(str(repo)), only_mass=True)
    assert "massDelete" in _mass_rows(result) and result["decision"] == "ask"


# --- the defaults ----------------------------------------------------------------

def test_the_measured_defaults(repo):
    limits = crew_mass.settings(str(repo))["limits"]
    assert limits["files"] == {"deleteCount": 10, "createCount": 20, "changeCount": 30}
    assert limits["git"] == limits["files"]
    assert limits["terraform"] == {"deleteCount": 3, "createCount": 10, "changeCount": 10}


def test_the_repo_can_lower_a_limit_but_not_raise_the_machines(repo, machine):
    (repo / ".crew" / "config.json").write_text(json.dumps({"guards": {"mass": {
        "enabled": True, "deleteCount": 5, "createCount": 500}}}), encoding="utf-8")
    limits = crew_mass.settings(str(repo))["limits"]["files"]
    assert limits["deleteCount"] == 5 and limits["createCount"] == 20
    machine.write_text(json.dumps({"guards": {"mass": {"createCount": 50}}}), encoding="utf-8")
    assert crew_mass.settings(str(repo))["limits"]["files"]["createCount"] == 50


@pytest.mark.parametrize("bad", [0, -3, True, "10", 2.5, None, [4]])
def test_a_limit_that_is_not_a_positive_integer_reads_as_the_default(repo, bad):
    (repo / ".crew" / "config.json").write_text(json.dumps({"guards": {"mass": {
        "enabled": True, "deleteCount": bad, "overrides": {"files": {"createCount": bad}}}}}),
        encoding="utf-8")
    limits = crew_mass.settings(str(repo))["limits"]["files"]
    assert limits["deleteCount"] == 10 and limits["createCount"] == 20


def test_a_per_kind_override_applies_to_that_kind_only(repo, machine):
    machine.write_text(json.dumps({"guards": {"mass": {"overrides": {
        "files": {"deleteCount": 3}}}}}), encoding="utf-8")
    limits = crew_mass.settings(str(repo))["limits"]
    assert limits["files"]["deleteCount"] == 3 and limits["git"]["deleteCount"] == 10
    _stops(repo, f"rm -rf {_fill(repo / 'few', 3)}", crew_mass.MASS_DELETE)


# --- delete ----------------------------------------------------------------------

def test_rm_at_the_limit_stops_and_one_below_passes(repo):
    _passes(repo, f"rm -rf {_fill(repo / 'nine', 9)}")
    _stops(repo, f"rm -rf {_fill(repo / 'ten', 10)}", crew_mass.MASS_DELETE)


def test_a_glob_is_counted_after_expansion(repo):
    _fill(repo / "g", 10, prefix="a")
    _fill(repo / "g", 5, prefix="b")
    _stops(repo, f"rm {repo / 'g' / 'a*.txt'}", crew_mass.MASS_DELETE)
    _passes(repo, f"rm {repo / 'g' / 'b*.txt'}")


def test_a_directory_without_r_deletes_nothing(repo):
    _passes(repo, f"rm {_fill(repo / 'd', 30)}")


def test_powershell_remove_item_recurse(repo):
    folder = _fill(repo / "ps", 12)
    _stops(repo, f"Remove-Item -Recurse -Force {folder}", crew_mass.MASS_DELETE, tool="PowerShell")
    _passes(repo, f"Remove-Item {folder / 'f1.txt'}", tool="PowerShell")


def test_git_clean_counts_what_it_would_remove(repo):
    _fill(repo / "junk", 11, prefix="u")
    _stops(repo, "git clean -fdx junk", crew_mass.MASS_DELETE)
    _passes(repo, "git clean -n -fd junk")


def test_git_rm_counts_tracked_files(repo):
    _fill(repo / "t", 12)
    _commit_all(repo)
    _stops(repo, "git rm -r t", crew_mass.MASS_DELETE)
    _passes(repo, "git rm --cached -r t")


@pytest.mark.parametrize("command", [
    "find . -name '*.log' -delete",
    "find /tmp/x -type f -exec rm {} +",
    "rsync -a --delete src/ dest/",
    "ls | xargs rm",
    "rm -rf $TARGET/*",
    "rm -rf $(cat list.txt)",
    "cd sub && rm -rf stuff",
])
def test_a_count_that_cannot_be_taken_stops(repo, command):
    _stops(repo, command, crew_mass.MASS_DELETE)


@pytest.mark.parametrize("name", ["node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
                                  ".mypy_cache", ".ruff_cache", ".tox", ".cache", "build", "dist",
                                  ".work", "pkg.egg-info"])
def test_a_regenerable_directory_never_counts(repo, name):
    folder = _fill(repo / name, 40)
    _passes(repo, f"rm -rf {folder}")


def test_a_regenerable_directory_nested_in_a_tree_is_skipped_not_the_tree(repo):
    _fill(repo / "pkg" / "node_modules", 40)
    _passes(repo, f"rm -rf {repo / 'pkg'}")
    _fill(repo / "pkg", 10)
    _stops(repo, f"rm -rf {repo / 'pkg'}", crew_mass.MASS_DELETE)


def test_a_worktree_directory_is_exempt_by_path(repo, tmp_path):
    folder = _fill(tmp_path / ".claude" / "crew" / "worktrees" / "proj" / "wt", 40)
    _passes(repo, f"rm -rf {folder}")


def test_a_repo_that_lives_under_a_worktrees_or_build_path_is_still_guarded(tmp_path, machine):
    assert machine
    root = make_repo(tmp_path / "build" / "worktrees", mode=None)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"mass": {"enabled": True}}}), encoding="utf-8")
    _stops(root, f"rm -rf {_fill(root / 'src2', 12)}", crew_mass.MASS_DELETE)


def test_the_machine_exempt_globs_apply_and_the_repos_do_not(repo, machine):
    _fill(repo / "gen", 40)
    (repo / ".crew" / "config.json").write_text(json.dumps({"guards": {"mass": {
        "enabled": True, "exempt": ["gen/*"]}}}), encoding="utf-8")
    _stops(repo, f"rm -rf {repo / 'gen'}", crew_mass.MASS_DELETE)
    machine.write_text(json.dumps({"guards": {"mass": {"exempt": ["gen/*"]}}}), encoding="utf-8")
    _passes(repo, f"rm -rf {repo / 'gen'}")


# --- create ----------------------------------------------------------------------

def test_touch_counts_new_files_only(repo):
    names = " ".join(str(repo / "n" / f"{i}.txt") for i in range(20))
    _stops(repo, f"touch {names}", crew_mass.MASS_CREATE)
    _passes(repo, "touch " + " ".join(str(repo / "n" / f"{i}.txt") for i in range(19)))
    _fill(repo / "n", 20, prefix="")
    _passes(repo, f"touch {names}")


def test_cp_r_into_a_new_place_creates_the_whole_tree(repo):
    source = _fill(repo / "src3", 20)
    _stops(repo, f"cp -r {source} {repo / 'copy'}", crew_mass.MASS_CREATE)
    _passes(repo, f"cp -r {_fill(repo / 'src4', 19)} {repo / 'copy2'}")


def test_cp_n_never_overwrites_and_a_single_file_is_one(repo):
    _passes(repo, f"cp {repo / 'src' / 'app.py'} {repo / 'x.py'}")
    _passes(repo, f"cp -n -r {_fill(repo / 'src5', 40)} {repo / 'src5_2'}")


def test_copying_into_a_regenerable_directory_does_not_count(repo):
    source = _fill(repo / "src6", 40)
    _passes(repo, f"cp -r {source} {repo / 'node_modules' / 'x'}")


# --- change ----------------------------------------------------------------------

def test_cp_over_existing_files_is_a_change(repo):
    source = _fill(repo / "a", 30, text="new")
    target = _fill(repo / "b", 30, text="old")
    _stops(repo, f"cp -r {source}/. {target}", crew_mass.MASS_CHANGE)


def test_cp_over_twenty_nine_existing_files_passes(repo):
    source = _fill(repo / "a", 29, text="new")
    target = _fill(repo / "b", 29, text="old")
    _passes(repo, f"cp -r {source}/. {target}")


def test_sed_in_place_over_many_files(repo):
    folder = _fill(repo / "s", 30)
    _stops(repo, f"sed -i s/x/y/ {folder / '*.txt'}", crew_mass.MASS_CHANGE)
    _passes(repo, f"sed -i s/x/y/ {folder / 'f1.txt'}")
    _passes(repo, f"sed s/x/y/ {folder / '*.txt'}")


def test_git_reset_hard_counts_the_files_that_differ(repo):
    _fill(repo / "w", 30, text="one")
    _commit_all(repo)
    for index in range(30):
        (repo / "w" / f"f{index}.txt").write_text("two", encoding="utf-8")
    _stops(repo, "git reset --hard", crew_mass.MASS_CHANGE)
    git(repo, "checkout", "--", "w")
    _passes(repo, "git reset --hard")


def test_git_checkout_paths_and_restore(repo):
    _fill(repo / "w", 31, text="one")
    _commit_all(repo)
    for index in range(31):
        (repo / "w" / f"f{index}.txt").write_text("two", encoding="utf-8")
    _stops(repo, "git checkout -- w", crew_mass.MASS_CHANGE)
    _stops(repo, "git restore w", crew_mass.MASS_CHANGE)
    _passes(repo, "git restore --staged w")
    _passes(repo, "git checkout main")


# --- git: the commit and the branch ----------------------------------------------

def test_commit_counts_staged_adds_deletes_and_changes(repo):
    _fill(repo / "c", 20)
    git(repo, "add", "-A")
    _stops(repo, "git commit -m x", crew_mass.MASS_CREATE)
    git(repo, "reset", "-q")
    _fill(repo / "c", 19)
    (repo / "c" / "f19.txt").unlink(missing_ok=True)
    git(repo, "add", "-A")
    _passes(repo, "git commit -m x")


def test_commit_a_flag_counts_tracked_changes_not_staged_ones(repo):
    _fill(repo / "d", 31, text="one")
    _commit_all(repo)
    for index in range(31):
        (repo / "d" / f"f{index}.txt").write_text("two", encoding="utf-8")
    _passes(repo, "git commit -m x")  # nothing staged
    _stops(repo, "git commit -am x", crew_mass.MASS_CHANGE)


def test_commit_counts_deletes(repo):
    _fill(repo / "e", 10)
    _commit_all(repo)
    for item in (repo / "e").iterdir():
        item.unlink()
    git(repo, "add", "-A")
    _stops(repo, "git commit -m x", crew_mass.MASS_DELETE)


def test_commit_exempts_generated_files_by_the_machine_globs(repo, machine):
    _fill(repo / "graphify-out", 30)
    git(repo, "add", "-A")
    _stops(repo, "git commit -m x", crew_mass.MASS_CREATE)
    machine.write_text(json.dumps({"guards": {"mass": {"exempt": ["graphify-out/*"]}}}),
                       encoding="utf-8")
    _passes(repo, "git commit -m x")


def test_push_counts_the_whole_branch_against_its_base(repo):
    _on_branch(repo)
    for index in range(3):
        _fill(repo / f"p{index}", 7)
        _commit_all(repo, f"c{index}")
    _stops(repo, "git push origin feat", crew_mass.MASS_CREATE)
    _stops(repo, "gh pr create --fill", crew_mass.MASS_CREATE)
    # forcePush's to judge, not ours
    assert not _mass_rows(_run(repo, "git push --force-with-lease origin feat"))


def test_push_a_small_branch_passes(repo):
    _on_branch(repo)
    _fill(repo / "q", 5)
    _commit_all(repo)
    _passes(repo, "git push origin feat")
    _passes(repo, "gh pr view 3")


def test_push_without_a_base_it_can_find_is_unknown_and_stops(repo):
    _fill(repo / "q", 5)
    _commit_all(repo)
    _stops(repo, "git push origin HEAD", crew_mass.MASS_DELETE)


# --- terraform and sql ------------------------------------------------------------

def _plan_runner(actions):
    """A stand-in for `terraform show -json`: one resource change per action."""
    def run(argv, **_kwargs):
        class Done:  # pylint: disable=too-few-public-methods
            returncode = 0
            stdout = json.dumps({"resource_changes": [
                {"change": {"actions": a}} for a in actions]})
        assert argv[:3] == ["terraform", "show", "-json"]
        return Done()
    return run


def _tf_verdicts(repo, command, actions, **config):
    mass = dict(crew_mass.settings(str(repo)), **config)
    ctx = {"cd": False, "switch": False, "engaged": False, "dispatch": {}}
    out = []
    for finding in cloud_guard.scan("bash", command, ctx=ctx):
        if finding.rule in crew_mass.RULES:
            verdict = crew_mass.judge(finding.scope["mass"], finding.text, str(repo), False,
                                      False, mass, runner=_plan_runner(actions),
                                      repo=(str(repo), str(repo / ".git" / "crew")))
            if verdict:
                out.append((finding.rule, verdict[0]))
    return out


@pytest.mark.parametrize("actions,rule", [
    ([["delete"]] * 3, "massDelete"),
    ([["create"]] * 10, "massCreate"),
    ([["update"]] * 10, "massChange"),
    ([["delete", "create"]] * 3, "massDelete"),
])
def test_terraform_apply_of_a_plan_uses_the_terraform_limits(repo, actions, rule):
    assert (rule, "ask") in _tf_verdicts(repo, "terraform apply tfplan", actions)


@pytest.mark.parametrize("actions", [
    [["delete"]] * 2 + [["create"]] * 9 + [["update"]] * 9,
    [["no-op"]] * 300,
    [["read"]] * 50,
])
def test_terraform_apply_below_the_limits_passes(repo, actions):
    assert not _tf_verdicts(repo, "terraform apply tfplan", actions)


def test_terraform_without_a_plan_to_read_stops(repo):
    assert _tf_verdicts(repo, "terraform destroy", []) == [("massDelete", "ask")]
    assert _tf_verdicts(repo, "terraform apply -auto-approve", []) == [("massChange", "ask")]
    assert not _tf_verdicts(repo, "terraform apply", [])  # interactive: it shows its plan
    assert not _tf_verdicts(repo, "terraform plan", [])


def test_a_plan_that_cannot_be_read_stops(repo):
    mass = crew_mass.settings(str(repo))

    def broken(*_a, **_k):
        raise OSError("no terraform")
    ctx = {"cd": False, "switch": False, "engaged": False, "dispatch": {}}
    found = [f for f in cloud_guard.scan("bash", "terraform apply tfplan", ctx=ctx)
             if f.rule in crew_mass.RULES]
    assert found
    for finding in found:
        verdict = crew_mass.judge(finding.scope["mass"], finding.text, str(repo), False, False,
                                  mass, runner=broken, repo=(str(repo), str(repo)))
        assert verdict and verdict[0] == "ask" and "could not be counted" in verdict[1]


@pytest.mark.parametrize("sql", [
    "DELETE FROM users",
    "delete from orders;",
    "UPDATE users SET active = 0",
    "update t set a=1 where 1=1",
    "DELETE FROM t WHERE true",
    "SELECT 1; DELETE FROM t",
])
def test_an_unfiltered_sql_delete_or_update_stops(repo, sql):
    _stops(repo, f'psql -d app -c "{sql}"')
    _stops(repo, f"echo hi | mysql -e '{sql}'")


@pytest.mark.parametrize("sql", [
    "DELETE FROM users WHERE id = 7",
    "UPDATE users SET active = 0 WHERE id IN (1, 2)",
    "SELECT * FROM users",
    "INSERT INTO t VALUES (1)",
    "delete from t where created < now() - interval '1 day'",
])
def test_a_filtered_or_read_only_statement_passes(repo, sql):
    _passes(repo, f'psql -d app -c "{sql}"')


def test_a_heredoc_sql_text_is_read(repo):
    _stops(repo, "psql -d app <<'SQL'\nDELETE FROM users;\nSQL")
    _passes(repo, "psql -d app <<'SQL'\nDELETE FROM users WHERE id = 1;\nSQL")


# --- the verdict and the approval -------------------------------------------------

def test_attended_is_an_ask_unattended_is_a_deny(repo, monkeypatch):
    command = f"rm -rf {_fill(repo / 'z', 12)}"
    assert _stops(repo, command)["decision"] == "ask"
    monkeypatch.setenv("CREW_UNATTENDED", "1")
    result = _stops(repo, command)
    assert result["decision"] == "deny" and "nobody is attending" in result["reason"]


def test_the_stop_names_its_id_and_the_limit(repo):
    result = _stops(repo, f"rm -rf {_fill(repo / 'z', 12)}")
    assert "/crew:approve-mass " in result["reason"] and "guards.mass.deleteCount" in result["reason"]


def _approve(repo, command, **fields):
    command = command.replace("\\", "/")
    top = os.path.realpath(str(repo))
    mass_id = crew_mass.approval_id(command, top)
    folder = repo / ".git" / "crew" / crew_mass.APPROVAL_DIR
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()
    record = {"id": mass_id, "approved_at": now, "expires": now + 900,
              "approved_via": "user-prompt"}
    record.update(fields)
    (folder / f"{mass_id}.json").write_text(json.dumps(record), encoding="utf-8")
    return mass_id


def test_the_owners_typed_yes_lets_that_command_through_once_and_only_that_command(repo):
    folder = _fill(repo / "z", 12)
    command = f"rm -rf {folder}"
    _approve(repo, command)
    result = _run(repo, command)
    assert result["decision"] == "allow"
    assert any(r[1].endswith(":approved") for r in result["rows"])
    _stops(repo, f"rm -fr {folder}")  # another command line: another id
    _stops(repo, f"rm -rf {_fill(repo / 'other', 12)}")


@pytest.mark.parametrize("fields", [
    {"approved_via": "cli"},
    {"approved_via": None},
    {"expires": 1.0},
    {"approved_at": time.time() + 3600, "expires": time.time() + 7200},
    {"approved_at": "now"},
    {"id": "000000000000"},
    {"expires": True},
])
def test_a_forged_expired_or_future_approval_is_not_an_approval(repo, fields):
    command = f"rm -rf {_fill(repo / 'z', 12)}"
    _approve(repo, command, **fields)
    _stops(repo, command)


def test_an_approval_older_than_the_ttl_is_not_an_approval(repo):
    command = f"rm -rf {_fill(repo / 'z', 12)}"
    stale = time.time() - 2 * crew_mass.MASS_APPROVAL_TTL
    _approve(repo, command, approved_at=stale, expires=time.time() + 9999)
    _stops(repo, command)


def test_one_id_covers_every_rule_the_command_trips(repo):
    source = _fill(repo / "src7", 31, text="new")
    target = _fill(repo / "dst7", 31, text="old")
    _fill(source, 20, prefix="extra")
    command = f"cp -r {source}/. {target}"
    result = _stops(repo, command)
    assert {"massCreate", "massChange"} <= set(_mass_rows(result))
    _approve(repo, command)
    assert _run(repo, command)["decision"] == "allow"


def test_a_command_writing_the_approvals_directory_is_refused(repo):
    target = repo / ".git" / "crew" / crew_mass.APPROVAL_DIR / "abcdef012345.json"
    result = _run(repo, f"echo '{{}}' > {target}")
    assert result["decision"] == "deny" and "massApprovals" in str(result["rows"])
    assert _run(repo, f"ls {target.parent}")["decision"] == "allow"


def test_armed_by_a_humanonly_opt_out_without_the_switch(tmp_path, machine, monkeypatch):
    root = make_repo(tmp_path, mode=None)
    monkeypatch.setattr(crew_mass, "opted_out", lambda *_a, **_k: True)
    mass = crew_mass.settings(str(root))
    assert mass["armed"] is True and mass["why"] == "humanOnly opt-out"
    monkeypatch.setattr(crew_mass, "opted_out", lambda *_a, **_k: False)
    assert crew_mass.settings(str(root))["armed"] is False
    assert machine


def test_a_resolver_that_raises_is_no_opt_out(tmp_path, machine, monkeypatch):
    import crew_humanonly  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path, mode=None)
    machine.write_text(json.dumps({"humanOnly": {"approve": False}}), encoding="utf-8")

    def boom(*_a, **_k):
        raise RuntimeError("x")
    monkeypatch.setattr(crew_humanonly, "resolve", boom)
    assert crew_mass.opted_out(str(root)) is False
    assert crew_mass.settings(str(root))["armed"] is False


def test_report_mode_enforces_nothing_but_logs_the_stop(repo):
    command = f"rm -rf {_fill(repo / 'z', 12).as_posix()}"
    result = cloud_guard.evaluate(str(repo), "Bash", command, {"cwd": str(repo)}, "report",
                                  crew_mass.settings(str(repo)))
    assert result["decision"] is None
    assert any(row[2] == "report:ask" for row in result["rows"])
