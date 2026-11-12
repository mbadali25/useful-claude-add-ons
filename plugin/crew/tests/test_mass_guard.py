"""crew 1.3.36: the mass delete / create / change stop (`crew_mass.py`).

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
import subprocess
import sys
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


# --- git: a linked worktree, fileMode / CRLF, no upstream, a leading cd ------------
# The tss-ai report (crew 1.3.42): a plain `git commit` / `git push` in a linked
# worktree on a slash-named branch was refused as "could not be counted" with 2
# files staged. Verified cause: the command was `cd <worktree> && git commit`,
# and any cd made the count unknowable. A first literal cd is now followed.

def _worktree(repo, tmp_path, branch="docs/tss-ai-records"):
    """A LINKED worktree of `repo` on a slash-named branch (its .git is a file),
    with origin/main = the commit it branched from."""
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    wt = tmp_path / "wt-records"
    git(repo, "worktree", "add", "-q", "-b", branch, str(wt))
    assert (wt / ".git").is_file()
    return wt


def _in(repo, cwd, command):
    """`evaluate` for `command` run with the Bash tool's cwd at `cwd`."""
    command = command.replace("\\", "/")
    mass = crew_mass.settings(str(repo))
    return cloud_guard.evaluate(str(repo), "Bash", command, {"cwd": str(cwd)}, "block", mass)


def _stopped_in(repo, cwd, command, rule):
    result = _in(repo, cwd, command)
    assert rule in _mass_rows(result) and result["decision"] in ("ask", "deny"), result
    return result


def _clean_in(repo, cwd, command):
    result = _in(repo, cwd, command)
    assert not _mass_rows(result) and result["decision"] == "allow", result


@pytest.mark.parametrize("config", [(), (("core.fileMode", "false"),), (("core.autocrlf", "true"),),
                                    (("core.fileMode", "false"), ("core.autocrlf", "true"))])
def test_a_linked_worktree_counts_two_staged_files_as_two(repo, tmp_path, config):
    for key, value in config:
        git(repo, "config", key, value)
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    _clean_in(repo, wt, "git commit -m x")
    _clean_in(repo, wt, "git commit -am x")
    _clean_in(repo, wt, "git push origin docs/tss-ai-records")
    _clean_in(repo, wt, "gh pr create --fill")


def test_a_linked_worktree_still_stops_a_real_mass_delete_create_and_change(repo, tmp_path):
    _fill(repo / "e", 11, text="one")
    _commit_all(repo)
    wt = _worktree(repo, tmp_path)
    for item in (wt / "e").iterdir():
        item.unlink()
    git(wt, "add", "-A")
    _stopped_in(repo, wt, "git commit -m x", crew_mass.MASS_DELETE)
    git(wt, "reset", "-q", "--hard")
    _fill(wt / "n", 20)
    git(wt, "add", "-A")
    _stopped_in(repo, wt, "git commit -m x", crew_mass.MASS_CREATE)


def test_a_branch_with_no_upstream_is_counted_against_the_base(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    assert not git(wt, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    _fill(wt / "q", 3)
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "small")
    _clean_in(repo, wt, "git push origin HEAD")
    _fill(wt / "r", 25)
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "big")
    _stopped_in(repo, wt, "git push origin HEAD", crew_mass.MASS_CREATE)


def test_a_leading_cd_into_a_worktree_is_followed(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    for form in (f"cd {wt} && git commit -m x", f"cd {wt} && git push origin HEAD"):
        _clean_in(repo, repo, form)
    git(wt, "reset", "-q")
    _fill(wt / "docs", 22)
    git(wt, "add", "-A")
    _stopped_in(repo, repo, f"cd {wt} && git commit -m x", crew_mass.MASS_CREATE)


def _big_wt(repo, tmp_path, count=22):
    """A linked worktree with `count` files staged; `repo` itself has nothing staged."""
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", count)
    git(wt, "add", "-A")
    return wt


# The narrow design (crew 1.3.50, round 4). A cd is followed ONLY when the WHOLE command is
# one plain line: bash `cd <plain path> && git <plain args>`; PowerShell `Set-Location|cd|sl
# <plain ABSOLUTE path> && git <plain args>` (round 12: never `;`, which runs git where the
# shell already was when the cd fails). Plain: ASCII, space/tab only, a path
# of letters digits and `_ . / : -`, and git arguments of bare words or quoted strings with no
# `$`, backtick, backslash, `;`, newline or non-ASCII. Everything else after a cd is "could not
# tell", exactly as on main. Every refusal below runs from a worktree with 32 files staged and
# `cd`s into a repo with nothing staged, so a wrongly followed cd counts 0 and lets it through.

def _cwd_big_cd_clean(repo, tmp_path):
    """(worktree with 32 staged files = where the shell really is, clean repo to `cd` into)."""
    return _big_wt(repo, tmp_path, count=32), repo


def _fwd(path):
    return str(path).replace(chr(92), "/")


def _ps_in(repo, cwd, command):
    return cloud_guard.evaluate(str(repo), "PowerShell", command.replace("\\", "/"),
                                {"cwd": str(cwd)}, "block", crew_mass.settings(str(repo)))


def _ps_clean(repo, cwd, command):
    result = _ps_in(repo, cwd, command)
    assert not _mass_rows(result) and result["decision"] == "allow", (command, result)


def _ps_stopped(repo, cwd, command):
    result = _ps_in(repo, cwd, command)
    assert _mass_rows(result) and result["decision"] in ("ask", "deny"), (command, result)


def _seen_as_git(command):
    """The scanner (not this grammar) must see a plain git commit for a stop to be expected:
    NBSP, FF, VT, 0x1c, CR and the like make main's own scanner read no git command at all."""
    return (command.isascii() and not any(ch in command for ch in "\f\v\x1c\r")
            and "git commit -m" in command and "echo" not in command
            and "cat <<" not in command)


BASH_REFUSED = [
    # whitespace that is not an ASCII space or tab, after the target and before git
    "cd {c}\u00a0&& git commit -m x", "cd {c}\u00a0; git commit -m x", "cd {c}\f&& git commit -m x",
    "cd {c}\v&& git commit -m x", "cd {c}\x1c&& git commit -m x", "cd {c}\u2003&& git commit -m x",
    "cd {c}\r&& git commit -m x", "cd {c} &&\u00a0git commit -m x", "cd\u00a0{c} && git commit -m x",
    "cd {c} && git commit -m x\u00a0", "cd {c} && git\u00a0commit -m x",
    # a newline: bash does a bare `cd` and the next line runs in the old directory
    "cd\n{c} && git commit -m x", "cd {c}\n&& git commit -m x", "cd {c} && git commit -m x\n",
    "cd {c} && git commit -m x\ncd {wt}",
    # `;` and `||` are not `&&`
    "cd {c}; git commit -m x", "cd {c} || git commit -m x",
    # quoting, tilde, expansion in the target
    "cd '{c}' && git commit -m x", 'cd "{c}" && git commit -m x', "cd $'{c}' && git commit -m x",
    "cd '~' && git commit -m x", "cd ~ && git commit -m x", "cd $DEST && git commit -m x",
    "cd {c}/* && git commit -m x", "cd -P {c} && git commit -m x", "cd - && git commit -m x",
    # other spellings of cd, and bash is case-sensitive
    "CD {c} && git commit -m x", "pushd {c} && git commit -m x", "sl {c} && git commit -m x",
    "Set-Location {c} && git commit -m x", "cd -LiteralPath {c} && git commit -m x",
    # a command inside the arguments
    'cd {c} && echo "$(${{X:-cd}} {wt}; git commit -qm y)"',
    'cd {c} && git commit -qm "$(${{X:-cd}} {wt} && git commit -qm y)"',
    'cd {c} && git commit -qm "`cd {wt}`"', "cd {c} && git commit -qm \"$(cd {wt})\"",
    "cd {c} && git commit -qm 'a;b'", "cd {c} && git commit -qm \"a;b\"",
    "cd {c} && git commit -qm x\\y", "cd {c} && git commit -qm 'a\\b'","cd {c} && cat <<EOF\n$(cd {wt})\nEOF",
    "cd {c} && git commit -F - <<EOF\nmsg\nEOF",
    # more than one command, a pipe, a redirect, an assignment, a prefix
    "cd {c} && git add -A && git commit -m x", "cd {c} && git status; git commit -m x",
    "cd {c} && git commit -m x | tail -3", "cd {c} && git commit -m x 2>&1",
    "cd {c} && X=1 git commit -m x", "cd {c} && exec git commit -m x",
    "cd {c} && git commit -m x && cd {wt}", "cd {c} && (cd {wt}; git commit -m x)",
    "cd {c} && git commit -m $MSG", "cd {c} && git commit -m {{a,b}}",
    "cd {c} && git log HEAD@{{1}}", "cd {c} && git commit -m x #c",
    "cd {c} && alias git=true; git commit -m x", "cd {c} && cd {wt} && git commit -m x",
    "cd {c} && bash -c 'cd {wt}; git commit -m x'", "cd {c} && git commit -m 'x",
    "cd {c} && git commit -m x \n", "cd {c} && git commit  -m x",
    "cd {c} && git commit -m \u00e9", "cd {c} && cd",
]

PS_REFUSED = [
    "Set-Location {c}\u00a0; git commit -m x", "Set-Location {c} ;\u00a0git commit -m x",
    "sl {c}\f; git commit -m x", "cd {c}\x1c; git commit -m x", "cd {c}\u2003&& git commit -m x",
    "cd {c}\r; git commit -m x", "cd {c}\n; git commit -m x", "cd\n{c}; git commit -m x",
    "cd.. ; git commit -m x", "cd\\ ; git commit -m x", "cd..; git commit -m x",
    "Set-Location '{c}'; git commit -m x", 'sl "{c}"; git commit -m x',
    "Set-Location -LiteralPath {c}; git commit -m x", "Set-Location -Path {c}; git commit -m x",
    "Push-Location {c}; git commit -m x", "pushd {c}; git commit -m x",
    "Set-Location {c}; git commit -m $m", "Set-Location {c}; $m = 'x'; git commit -m $m",
    "Set-Location {c}; $m = ./go.ps1; git commit -m $m", "Set-Location {c}; $m = cd..; git commit",
    "Set-Location {c}; git add -A; git commit -m x", "Set-Location {c}; git commit -m x | Out-Null",
    "Set-Location {c}; & git commit -m x", "Set-Location {c}; git commit -m \"$(sl {wt})\"",
    "Set-Location {c}; git commit -m `\n", "Set-Location {c}; git commit -m 'a;b'",
    "Set-Location {c}; sl {wt}; git commit -m x", "Set-Alias g sl; Set-Location {c}; git commit",
    "Set-Location {c}; git commit -m @x", "Set-Location {c} || git commit -m x",
    "Set-Location {c}; git commit -m x \n",
    "Set-Location {c}; git commit -m \u2018x\u2019", "(Set-Location {c}); git commit -m x",
]


@pytest.mark.parametrize("form", BASH_REFUSED)
def test_bash_cd_that_is_not_the_one_plain_line_is_could_not_tell(repo, tmp_path, form):
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    command = form.format(c=str(clean).replace("\\", "/"), wt=str(wt).replace("\\", "/"))
    assert crew_mass.leading_cd(command, str(wt), "bash") is None, command
    result = _in(repo, wt, command)
    if _seen_as_git(command):
        assert result["decision"] in ("ask", "deny"), (command, result)


def _first_semicolon_as_and(form):
    """`form` with its first `;` written `&&`: since round 12 a `;` is refused whatever
    surrounds it, so each refusal is also held in the one spelling that CAN be followed."""
    head, sep, tail = form.partition(";")
    return head.rstrip(" ") + " && " + tail.lstrip(" ") if sep else form


PS_REFUSED_AND = sorted({_first_semicolon_as_and(form) for form in PS_REFUSED} - set(PS_REFUSED))

# Round 12 (BLOCK-2). PowerShell's `;` does not short-circuit: when Set-Location fails, git runs
# where the shell already was. pwsh 7.6.9 on Linux refuses `cd ///<dir>` ("An object at the
# specified path /// does not exist") although os.path.isdir('///<dir>') is true, so the hook
# followed a cd the shell never made and counted the clean repo. No `;` form is followed, and
# neither is a relative target, `chdir`, `pushd` or `||`.
PS_SEMICOLON = [
    "cd ///{c}; git commit -m x", "cd //{c}; git commit -m x", "cd {c}; git commit -m x",
    "Set-Location {c}; git commit -m x", "sl {c}; git commit -m x", "SL {c};git commit -m x",
    "set-location {c} ; git commit -m x", "cd {c}\t;\tgit commit -m x",
    "chdir {c}; git commit -m x", "chdir {c} && git commit -m x", "pushd {c}; git commit -m x",
    "pushd {c} && git commit -m x", "Push-Location {c} && git commit -m x",
    "cd {c} || git commit -m x", "cd {c} ;; git commit -m x", "cd {c} & git commit -m x",
    "cd {c} | git commit -m x", "cd {c}; cd {c} && git commit -m x",
]


@pytest.mark.parametrize("form", PS_SEMICOLON)
def test_a_powershell_semicolon_cd_is_never_followed(repo, tmp_path, form):
    """The reviewer's scene: the shell is in a worktree with 32 staged files and the command
    names a clean repository. Followed, the count is 0 and the commit passes."""
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    command = form.format(c=_fwd(clean))
    assert crew_mass.leading_cd(command, str(wt), "powershell") is None, command
    _ps_stopped(repo, wt, command)


def test_a_powershell_target_is_followed_only_when_it_names_its_own_root(repo, tmp_path):
    """A relative PowerShell target is read against the current PROVIDER drive, which an
    earlier `cd Env:` or `cd HKCU:` may have left somewhere that is not the file system."""
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    (wt / "sub").mkdir()
    for form in ("cd ./sub && git commit -m x", "cd sub && git commit -m x",
                 "cd . && git commit -m x", "Set-Location sub/ && git commit -m x",
                 "sl ./ && git commit -m x"):
        assert crew_mass.leading_cd(form, str(wt), "powershell") is None, form
        _ps_stopped(repo, wt, form)
    assert crew_mass.leading_cd(f"cd {_fwd(clean)} && git commit -m x", str(wt), "powershell") \
        == os.path.normpath(clean)
    _ps_clean(repo, wt, f"cd {_fwd(clean)} && git commit -m x")


@pytest.mark.parametrize("form", PS_REFUSED + PS_REFUSED_AND)
def test_powershell_cd_that_is_not_the_one_plain_line_is_could_not_tell(repo, tmp_path, form):
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    command = form.format(c=str(clean).replace("\\", "/"), wt=str(wt).replace("\\", "/"))
    assert crew_mass.leading_cd(command, str(wt), "powershell") is None, command
    if _seen_as_git(command):
        _ps_stopped(repo, wt, command)


def test_the_one_plain_bash_line_is_followed_and_counted_there(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    for tail in ("git commit -m x", "git commit -m 'simple'", 'git commit -m "simple message"',
                 "git commit -am 'a & b | c > d'", "git push", "git push origin HEAD",
                 "git commit\t-m\tx", "git commit --amend --no-edit -q", "git log --oneline",
                 "git add src/a.py docs/b.md"):
        for sep in (" && ", "  &&\t"):
            _clean_in(repo, repo, f"cd {wt}{sep}{tail}")
    assert crew_mass.leading_cd(f"cd {_fwd(wt)} && git push", str(repo), "bash") \
        == os.path.normpath(wt)
    # ...and counted THERE: the same shapes over a 32-file worktree stop
    git(wt, "reset", "-q")
    _fill(wt / "docs", 32)
    git(wt, "add", "-A")
    for tail in ("git commit -m x", "git commit -m 'simple'"):
        _stopped_in(repo, repo, f"cd {wt} && {tail}", crew_mass.MASS_CREATE)
    git(wt, "commit", "-qm", "big")
    _stopped_in(repo, repo, f"cd {wt} && git push origin HEAD", crew_mass.MASS_CREATE)


def test_the_one_plain_powershell_line_is_followed_and_counted_there(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    for form in ("Set-Location {wt} && git commit -m x", "set-location {wt} && git commit -m x",
                 "cd {wt} && git commit -m 'simple'",
                 "sl {wt} && git commit -m \"simple message\"",
                 "SL {wt} && git push", "cd {wt} && git push origin HEAD",
                 "Set-Location {wt}\t&&\tgit commit -m x", "cd {wt}&&git commit -m x"):
        _ps_clean(repo, repo, form.format(wt=wt))
    # the same line with `;` is not followed: the count cannot be taken, so it is asked
    for form in ("Set-Location {wt}; git commit -m x", "cd {wt}; git commit -m 'simple'"):
        _ps_stopped(repo, repo, form.format(wt=wt))
    git(wt, "reset", "-q")
    _fill(wt / "docs", 32)
    git(wt, "add", "-A")
    command = f"Set-Location {wt} && git commit -m x"
    result = _ps_in(repo, repo, command)
    assert crew_mass.MASS_CREATE in _mass_rows(result) and result["decision"] in ("ask", "deny")


def test_bash_does_not_run_powershell_spellings_and_powershell_is_case_blind(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    for form in ("CD {wt} && git commit -m x", "sl {wt} && git commit -m x",
                 "Set-Location {wt} && git commit -m x", "pushd {wt} && git commit -m x"):
        assert crew_mass.leading_cd(form.format(wt=_fwd(wt)), str(repo), "bash") is None, form
    for form in ("CD {wt} && git commit", "Cd {wt} && git commit",
                 "SET-LOCATION {wt} && git commit"):
        assert crew_mass.leading_cd(form.format(wt=_fwd(wt)), str(repo), "powershell"), form


def test_what_was_followed_on_the_branch_but_is_could_not_tell_again_equals_main(
        repo, tmp_path):
    # Same as main, on purpose: these were briefly followed by the round-3 tokenizer and
    # are harmless in fact, but only the one plain line is provable, so each is "could not
    # tell" (the refusal names the cd as the reason).
    wt = _big_wt(repo, tmp_path, count=2)
    for tail in ("git add -A && git commit -m x", "git status; git commit -m x",
                 "git commit -m x 2>&1 | tail -3", 'git commit -m "$(echo hi)"',
                 "git commit -m \"$(cat <<'EOF'\nmsg\nEOF\n)\"", "exec git commit -m x",
                 "X=1 git commit -m x", "git log HEAD@{1} && git commit -m x"):
        result = _stopped_in(repo, repo, f"cd {wt} && {tail}", crew_mass.MASS_DELETE)
        assert "moves the shell" in result["reason"], (tail, result)
    for tail in ("$m='msg'; git commit -m $m", "git add -A; git commit -m x"):
        _ps_stopped(repo, repo, f"Set-Location {wt}; {tail}")


def test_a_dash_a_glob_and_a_tilde_are_never_a_followed_target(repo, tmp_path):
    # `cd -` is OLDPWD (bash) or the previous location (PowerShell), `cd d[1]` globs, `cd ~`
    # is home; none is the literal path. Bash refuses all three as a bare name anyway, so the
    # PowerShell grammar (no bare-name rule) is where the character class itself is held.
    for name in ("-", "d[1]", "d1", "~"):
        (repo / name).mkdir()
    for form in ("cd - && git commit -m x", "cd d[1] && git commit -m x",
                 "cd ~ && git commit -m x", "cd ./d[1] && git commit -m x"):
        assert crew_mass.leading_cd(form, str(repo), "bash") is None, form
    for form in ("cd - && git commit -m x", "cd d[1] && git commit -m x",
                 "cd ~ && git commit -m x", "sl - && git commit -m x",
                 "cd ./d[1] && git commit -m x", f"cd {_fwd(repo)}/d[1] && git commit -m x",
                 f"cd {_fwd(repo)}/~ && git commit -m x", f"cd -{_fwd(repo)} && git commit -m x"):
        assert crew_mass.leading_cd(form, str(repo), "powershell") is None, form
    assert crew_mass.leading_cd(f"cd {_fwd(repo)}/d1 && git commit -m x", str(repo), "powershell")


def test_leading_cd_needs_an_existing_directory_and_no_cdpath(repo, tmp_path, monkeypatch):
    wt = _worktree(repo, tmp_path)
    assert crew_mass.leading_cd(f"cd {_fwd(wt)}/missing && git commit", str(repo), "bash") is None
    assert crew_mass.leading_cd(f"cd {_fwd(wt)} && git commit", "", "bash") is None
    assert crew_mass.leading_cd(f"cd {_fwd(wt)} && git commit", str(repo), "bash")



def test_a_bare_relative_bash_cd_is_could_not_tell_whatever_cdpath_shows(
        repo, tmp_path, monkeypatch):
    # bash may take CDPATH from BASH_ENV or a profile, unexported, so this process cannot see
    # it: a bare name (`cd sub`) is never followed. Only absolute, ./x and ../x are (bash
    # does not consult CDPATH for those; verified with `CDPATH=d bash -c 'cd ./r'`).
    (repo / "sub").mkdir()
    _fill(repo / "docs", 2)
    git(repo, "add", "-A")
    monkeypatch.delenv("CDPATH", raising=False)
    for form in ("cd sub && git commit -m x", "cd sub/ && git commit -m x"):
        result = _stopped_in(repo, repo, form, crew_mass.MASS_DELETE)
        assert "moves the shell" in result["reason"], result
    monkeypatch.setenv("CDPATH", str(tmp_path))
    _stopped_in(repo, repo, "cd sub && git commit -m x", crew_mass.MASS_DELETE)
    # an explicit ./ or ../ or absolute path never consults CDPATH
    _clean_in(repo, repo, "cd ./sub && git commit -m x")
    _clean_in(repo, repo, f"cd {repo}/sub && git commit -m x")
    assert crew_mass.leading_cd("cd ./sub/. && git status", str(repo), "bash")
    assert crew_mass.leading_cd("cd . && git status", str(repo), "bash")
    monkeypatch.delenv("CDPATH")
    assert crew_mass.leading_cd("cd sub && git status", str(repo), "bash") is None
    assert crew_mass.leading_cd("cd ./sub && git status", str(repo), "bash")


# --- round 5: linear time, flags, PowerShell paths, GIT_* words, the upstream base -----

_GIT_TAILS_REFUSED = [
    "git -C ../wt commit -m x", "git -C../wt commit -m x", "git -C./../wt commit -m x",
    "git -c k=v commit -m x", "git --git-dir ../x commit -m x",
    "git --git-dir=../x commit -m x", "git --work-tree ../x commit -m x",
    "git commit --work-tree ../x -m x", "git commit -C HEAD", "git commit -c HEAD",
    "git --namespace ns commit -m x", "git --exec-path commit", "git --attr-source HEAD commit",
    "git commit --format=%s", "git log -5", "git commit -n5", "git commit -F -", "git -- commit",
    "git commit -m x --", "git commit --1x", "git -p log", "git --no-pager log",
    'git "commit" -m x', "git commit -m 'a'b", 'git commit -m "a""b"', "git commit -m 'a' 'b",
]


@pytest.mark.parametrize("tail", _GIT_TAILS_REFUSED)
def test_a_flag_that_carries_a_path_a_value_or_moves_git_is_could_not_tell(
        repo, tmp_path, tail):
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    tail = tail.format(c=_fwd(clean))
    assert crew_mass.leading_cd(f"cd {_fwd(clean)} && {tail}", str(wt), "bash") is None, tail
    for sep in ("; ", " && "):
        assert crew_mass.leading_cd(f"cd {_fwd(clean)}{sep}{tail}", str(wt), "powershell") \
            is None, tail
    if "commit" in tail and "-m x" in tail:
        # the real shell is at the 32-file worktree: a followed cd would count the clean repo
        result = _in(repo, wt, f"cd {_fwd(clean)} && {tail}")
        assert _mass_rows(result) and result["decision"] in ("ask", "deny"), (tail, result)
        _ps_stopped(repo, wt, f"cd {_fwd(clean)}; {tail}")


def test_plain_flags_are_followed_in_both_shells(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    for tail in ("git commit --amend --no-edit", "git commit -a -q -m 'x y'", "git commit -am x",
                 "git log --oneline --decorate origin/main..HEAD", "git status -s -b"):
        assert crew_mass.leading_cd(f"cd {_fwd(wt)} && {tail}", str(repo), "bash"), tail
        assert crew_mass.leading_cd(f"cd {_fwd(wt)} && {tail}", str(repo), "powershell"), tail


@pytest.mark.parametrize("target", [
    "Env:", "Variable:", "Function:", "Alias:", "Cert:", "HKLM:", "HKCU:/x", "foo:bar",
    "x\\y", "C:\\a\\b", "c:", "C:foo", "a/b:c", "C:/a:b", "C::/x", ":/x", "1:/x/y", "C:\\a:b",
    "\\\\srv\\share", "sub\\", "a\\b/c"])
def test_powershell_provider_drives_and_backslash_paths_are_not_a_target(target):
    line = f"cd {target} && git status"
    assert not crew_mass._PS_CD_RE.match(line), line  # pylint: disable=protected-access
    assert not crew_mass._PS_CD_RE.match(f"Set-Location {target} && git status")  # pylint: disable=protected-access


@pytest.mark.parametrize("target", ["C:/x", "C:\\x", "c:/Users/a-b_c.d/e", "sub/dir", "../x", ".",
                                    "..", "a-b_c.d"])
def test_powershell_a_plain_path_and_one_drive_prefix_are_a_target(target):
    assert crew_mass._PS_CD_RE.match(f"cd {target} && git status"), target  # pylint: disable=protected-access
    assert not crew_mass._PS_CD_RE.match(f"cd {target}; git status"), target  # pylint: disable=protected-access


_LINEAR_CHILD = '''
import json, sys, time
sys.path.insert(0, {scripts!r})
import crew_mass
A = "a" * 5000
cases = {{
    "5000-char word": "cd /tmp && git add " + A + " && git commit -m x",
    "5000-char word, no second command": "cd /tmp && git add " + A + " | x",
    "600 paths": "cd /tmp && git add " + " ".join(["src/aaa.py"] * 600) + " && git commit -m x",
    "the real hook shape, log": "cd /tmp/repo && git log --oneline --decorate origin/main..HEAD | head -5",
    "the real hook shape, add and commit":
        "cd /tmp/repo && git add plugin/crew/hooks/scripts/crew_mass.py && git commit -m x",
    "the short form that took 12 s": "cd /tmp && git add src/aaaaaaaaaaaaaaaa.py && git commit -m x",
    "a long quoted string": "cd /tmp && git commit -m '" + "x " * 3000 + "' && git push",
    "nested quote characters": "cd /tmp && git commit -m " + "'\\"' " * 1500 + "'",
    "many quoted words": "cd /tmp && git commit " + "'a' " * 3000 + "&& x",
    "many flags": "cd /tmp && git commit " + "-a " * 3000 + "$",
    "very long spacing": "cd /tmp && git" + " " * 5000 + "x y;",
    "a deep path": "cd " + "a/" * 2500 + " && git commit; x",
    "a long drive path": "cd C:/" + "a/" * 2500 + " && git commit; x",
    "tabs everywhere": "cd\\t/tmp\\t&&\\tgit\\t" + "a\\t" * 3000 + "&",
}}
out = {{}}
for label, text in cases.items():
    start = time.process_time()
    for shell in ("bash", "powershell"):
        crew_mass.leading_cd(text, "/", shell)
    crew_mass.sets_git_location(text, "bash")
    out[label] = time.process_time() - start
for label, text in {{
    "unterminated nested substitutions": '"$(' * 2000 + "a " * 3000,
    "many quotes": "\\"a\\" " * 5000 + "'",
    "many heredocs": "cat <<A <<B <<C\\n" + "x\\n" * 3000,
    "many words": "x " * 20000 + "GIT_DIR",
    "many env words": "env " * 20000 + "x",
    "many statements": "a; " * 20000 + "GIT_DIR=x",
    "many exported names": "export " + "A=1 " * 20000,
    "many brace words": "X{{a,b}}{{c,d}}{{e,f}}{{g,h}}{{i,j}}{{k,l}}{{m,n}} " * 3000,
    "one huge brace word": "export " + "{{a,b}}" * 5000,
    "unterminated ANSI-C quote": "export $'" + chr(92) * 5000,
    "nested eval": "eval " * 2000 + "x",
    "many redirects": "a >f " * 5000 + "GIT_DIR=x",
    "many dollar-quotes": "$'a' " * 5000 + "b",
}}.items():
    start = time.process_time()
    crew_mass.sets_git_location(text, "bash")
    out[label] = time.process_time() - start
print(json.dumps(out))
'''


def test_the_cd_grammar_and_the_git_variable_scan_are_linear_on_adversarial_input():
    """A nested quantifier in the old argument pattern took 12 s on a 16-character path and
    18 s through the real hook. Each input must take < 0.5 s of CPU time
    (round 8 measured 0.12 s at worst against the old 0.2 s cap, no margin on a loaded host;
    the old pattern needs seconds) (`time.process_time`
    in the child, so a loaded host cannot fail it: round 6 saw 0.25 s and 0.5 s of wall clock
    for 0.02 s of CPU), in a CHILD process with a wall-clock timeout: `re` holds the GIL, so
    a thread could not interrupt a backtracking match, and a mutant that restores the pattern
    must go red rather than hang the suite."""
    scripts = os.path.dirname(os.path.abspath(crew_mass.__file__))
    try:
        done = subprocess.run([sys.executable, "-c", _LINEAR_CHILD.format(scripts=scripts)],
                              capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail("leading_cd / sets_git_location did not finish in 60 s: exponential backtracking")
    assert done.returncode == 0, done.stderr
    timings = json.loads(done.stdout)
    slow = {label: round(secs, 3) for label, secs in timings.items() if secs >= 0.5}
    assert not slow, f"slower than 0.5 s of CPU: {slow}"


def test_a_glob_or_tab_in_a_cd_or_dash_C_target_is_could_not_tell_and_quick(repo, tmp_path):
    base = _fwd(tmp_path)
    (tmp_path / "w1").mkdir()
    for command in (f"git -C {base}/w? commit -m x", f"git -C {base}/w\t commit -m x",
                    f"cd {base}/w? && git commit -m x", f"cd {base}/w\t && git commit -m x",
                    f"cd {base}/w[1] && git commit -m x"):
        start = time.perf_counter()
        result = _in(repo, repo, command)
        assert time.perf_counter() - start < 5, command
        assert result["decision"] in ("ask", "deny"), (command, result)
        assert crew_mass.leading_cd(command, str(repo), "bash") is None, command


_LOCATION_WORDS = [
    "GIT_DIR=x git commit -m x", "export GIT_INDEX_FILE=x; git commit -m x",
    "env GIT_DIR=x git commit -m x", "export GIT_DIR", "git status && GIT_WORK_TREE=/x git commit",
    "(GIT_DIR=x git commit)", 'export "GIT_DIR=x"', "declare -x GIT_NAMESPACE=n; git commit",
    "env -i GIT_COMMON_DIR=x git commit", 'git commit -m "$(GIT_DIR=x true)"',
    "git commit -m `GIT_DIR=x true`", 'git commit -m "a $(b "$(GIT_DIR=x true)")"',
    "git commit -F - <<EOF\n$(GIT_DIR=x echo)\nEOF", "git_dir=x git commit",
    'git commit -m "$(a "$(b "$(c "$(d "$(GIT_DIR=x e)")")")")"', "GIT_DIR='x' git commit",
    # round 7 (F3): the cheap spellings
    "GIT_INDEX_FILE+=/x git commit -m x", "export GIT_INDEX_FILE+=/x; git commit -m x",
    "export $'GIT_INDEX_FILE=/x'; git commit -m x", "eval 'export GIT_INDEX_FILE=/x'; git commit",
    "export GIT_{INDEX_FILE,ZZ}=/x; git commit -m x", "GIT_{DIR,ZZ}=/x git commit -m x",
    "env -S 'X=1 GIT_INDEX_FILE=/x git commit -m x'", "env --split-string='GIT_DIR=/x git status'",
    "bash -c 'GIT_DIR=/x git commit -m x'", "sh -lc 'export GIT_WORK_TREE=/x; git commit'",
    "FOO=1 BAR=2 GIT_DIR=/x git commit -m x", "time GIT_DIR=/x git commit -m x",
    "if true; then GIT_DIR=/x git commit -m x; fi", "{ GIT_DIR=/x git commit -m x; }",
    "sudo GIT_DIR=/x git commit -m x", "env -u FOO GIT_DIR=/x git commit",
    "readonly GIT_DIR=/x", "local GIT_DIR=/x", "typeset -x GIT_DIR=/x",
    "eval \"eval 'GIT_DIR=/x git commit'\"", "pwsh -c '$env:GIT_DIR = 1; git commit'",
    "2>/dev/null GIT_DIR=/x git commit -m x",
    # round 12 (NIT): ONE wrapper list. timeout / stdbuf / coproc were missed while nice,
    # nohup and setsid were read; and a wrapper's own options hid the command behind it.
    "timeout 5 env GIT_DIR=/x git commit -m x", "stdbuf -oL env GIT_DIR=/x git commit -m x",
    "coproc GIT_DIR=/x git commit -m x", "coproc env GIT_DIR=/x git commit -m x",
    "nice -n 5 env GIT_DIR=/x git commit -m x", "nohup env GIT_INDEX_FILE=/x git commit",
    "setsid -w env GIT_DIR=/x git commit", "sudo -u me GIT_DIR=/x git commit -m x",
    "timeout -s KILL 5 bash -c 'GIT_DIR=/x git commit'", "ionice -c 3 env GIT_DIR=/x git commit",
    "timeout 5 nice stdbuf -o0 env GIT_WORK_TREE=/x git commit", "xargs env GIT_DIR=/x git commit",
    "time -p env GIT_DIR=/x git commit", "exec env GIT_DIR=/x git commit -m x",
    "command env GIT_DIR=/x git commit", "doas env GIT_DIR=/x git commit",
    "timeout 5 sh -c 'export GIT_DIR=/x; git commit'", "nice eval 'GIT_DIR=/x git commit'",
    "su -c 'GIT_DIR=/x git commit'", "busybox sh -c 'GIT_DIR=/x git commit'",
    "pwsh -Command '$env:GIT_DIR = 1; git commit'", "pwsh -NoProfile -com '$env:GIT_DIR = 1'",
    "pwsh -c '$env:GIT_DIR' = 1", "pwsh -EncodedCommand JABlAG4AdgA6AEcASQBUAA==",
    "powershell.exe -ec JABlAG4AdgA6AEcASQBUAA==", "timeout 5 pwsh -c '$env:GIT_DIR = 1'",
    # an assignment counts whether or not it is exported (stricter than main, on purpose)
    "GIT_DIR=/x; git commit -m x", "GIT_INDEX_FILE=/x && git commit -m x",
]
_LOCATION_MESSAGES = [
    'git commit -m "docs: explain GIT_DIR handling"', 'git commit -m "note on git_namespace"',
    "git commit -F - <<'EOF'\nGIT_INDEX_FILE=x is documented here\nEOF",
    "git commit -F - <<EOF\nGIT_INDEX_FILE=x is documented here\nEOF",
    "git -C repo commit -m 'fix GIT_DIR handling'", 'git commit -m "docs: GIT_DIR=x is documented"',
    "git commit -m 'GIT_WORK_TREE and GIT_COMMON_DIR'", "echo GIT_DIRECTORY=x; git commit",
    "git commit -F - <<-EOF\n\tGIT_DIR=x\n\tEOF\ngit status",
    # round 7 (F4): a mention is not an assignment
    'git commit -m "GIT_DIR=/x was wrong"', "git commit -m GIT_DIR",
    "unset GIT_DIR GIT_WORK_TREE; git commit -m x", "grep -rn GIT_INDEX_FILE . ; git commit -m x",
    "echo GIT_INDEX_FILE=x; git commit -m x", "git commit -m 'GIT_DIR=x' -m GIT_WORK_TREE=y",
    "env -u GIT_DIR git commit -m x", "MY_GIT_DIR=x git commit -m x",
    "cat GIT_DIR=x | git commit -F - ", "git log --grep=GIT_DIR=x; git commit -m x",
    "GIT_DIR; git commit -m x", "export -n; GIT_WORK_TREE; git commit -m x",
    # round 12: a wrapper does not make a mention an assignment
    "timeout 5 git commit -m x", "nice -n 5 git commit -m 'about GIT_DIR'",
    "timeout 5 git commit -m 'fix GIT_DIR=x handling'", "stdbuf -oL git log --grep GIT_DIR",
    "git commit -m x # GIT_DIR=x", "git commit -m x # export GIT_DIR=x",
    "nohup git push origin HEAD", "pwsh -NoProfile -File build.ps1; git commit -m x",
    "pwsh -c 'Write-Output $env:GIT_DIR'; git commit -m x",
]
_LOCATION_MESSAGES_PS = [
    "git commit -m $env:GIT_DIR", 'git commit -m "GIT_DIR=/x was wrong"',
    "Write-Output $env:GIT_INDEX_FILE; git commit -m x", "Get-Item Env:GIT_DIR; git commit -m x",
    "Remove-Item Env:GIT_DIR; git commit -m x", "git commit -m x # $env:GIT_DIR = 'y'",
    "$env:GIT_DIR; git commit -m x", "$env:GIT_INDEX_FILE -eq 'x'; git commit -m x",
    # round 12: quoted text is text, a read is a read, and the Env: drive alone sets nothing
    "git commit -m '$env:GIT_DIR = x'", "git commit -m '$env:GIT_DIR=x'",
    'git commit -m "$env:GIT_DIR=x"', "Test-Path Env:GIT_DIR; git commit -m x",
    "Get-ChildItem Env:; git commit -m x", "1 | % { $env:GIT_DIR }; git commit -m x",
    "if ($env:GIT_DIR -ne $null) { 1 }; git commit -m x", "git commit -m GIT_DIR",
    "Get-Content Env:GIT_DIR; git commit -m x", "$x = $env:GIT_DIR; git commit -m x",
]


@pytest.mark.parametrize("command", _LOCATION_WORDS)
def test_an_assignment_of_a_git_location_variable_is_seen(command):
    assert crew_mass.sets_git_location(command, "bash"), command


@pytest.mark.parametrize("command", [
    "$env:GIT_DIR = 'x'; git commit", "$env:git_index_file='x'; git commit",
    "Set-Item Env:GIT_DIR x; git commit",
    "[Environment]::SetEnvironmentVariable('GIT_DIR','x'); git commit",
    # round 7 (F3)
    "${env:GIT_INDEX_FILE}='/x'; git commit -m x", "$env:GIT_INDEX_FILE+='/x'; git commit -m x",
    "$env:GIT_INDEX_FILE += '/x'; git commit -m x",
    "Set-Item -Path Env:\\GIT_INDEX_FILE /x; git commit -m x",
    "Set-Content env:\\GIT_INDEX_FILE /x; git commit -m x",
    "Set-Item -Path:Env:GIT_DIR -Value x; git commit",
    "if ($true) { $env:GIT_DIR = 'x' }; git commit",
    "iex '$env:GIT_DIR = 1'; git commit", "bash -c 'GIT_DIR=/x git commit'",
    # round 12 (NIT): anywhere in a statement, `??=`, the provider in two words
    "1 | % { $env:GIT_DIR = 'x' }; git commit", "1 | ForEach-Object { $env:GIT_DIR='x' }; git commit",
    "$env:GIT_DIR ??= 'x'; git commit", "$env:GIT_DIR??='x'; git commit",
    "& { $env:GIT_DIR = 'x' }; git commit", ". { ${env:GIT_WORK_TREE} = 'x' }; git commit",
    "foreach ($i in 1) { $env:GIT_WORK_TREE='x' }; git commit",
    "$a = 1; $env:GIT_DIR, $b = 'x', 'y'; git commit", "$x = ($env:GIT_DIR = 'y'); git commit",
    "New-Item Env:GIT_DIR -Value x; git commit", "ni Env:\\GIT_DIR -Value x; git commit",
    "New-Item -Path Env: -Name GIT_DIR -Value x; git commit",
    "New-Item -Path Env:\\ -Name GIT_INDEX_FILE -Value x; git commit",
    "Set-Location Env:; Set-Item GIT_DIR x; Set-Location C:; git commit",
    "Push-Location Env:; ni GIT_WORK_TREE -Value x; Pop-Location; git commit",
    "Copy-Item Env:FOO Env:GIT_DIR; git commit", "Rename-Item Env:FOO GIT_DIR; git commit",
    "1 | % { Set-Item Env:GIT_DIR x }; git commit", "Set-Item 'Env:GIT_DIR' x; git commit",
    "pwsh -c { $env:GIT_DIR = 'x'; git commit }", "pwsh -Command \"`$env:GIT_DIR = 1\"; git commit",
    "timeout 5 env GIT_DIR=/x git commit", "powershell -enc JABlAG4AdgA6AEcASQBUAA==; git commit"])
def test_a_powershell_assignment_of_a_git_location_variable_is_seen(command):
    assert crew_mass.sets_git_location(command, "powershell"), command


@pytest.mark.parametrize("command", _LOCATION_MESSAGES)
def test_a_message_or_heredoc_that_only_mentions_a_git_variable_is_not_an_assignment(command):
    assert not crew_mass.sets_git_location(command, "bash"), command


def test_a_commit_message_naming_a_git_variable_is_counted_not_refused(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    for command in _LOCATION_MESSAGES[:6]:
        command = command.replace("git -C repo", f"git -C {_fwd(wt)}")
        _clean_in(repo, wt if "-C" not in command else repo, command)
    git(wt, "reset", "-q")
    _fill(wt / "docs", 22)
    git(wt, "add", "-A")
    # the count is still taken: a real mass commit with such a message stops
    _stopped_in(repo, wt, 'git commit -m "docs: explain GIT_DIR handling"', crew_mass.MASS_CREATE)
    _stopped_in(repo, repo, f"git -C {_fwd(wt)} commit -m 'fix GIT_DIR handling'",
                crew_mass.MASS_CREATE)


@pytest.mark.parametrize("command", ["GIT_DIR={x} git commit -m x",
                                     "export GIT_INDEX_FILE={x}; git commit -m x",
                                     "env GIT_DIR={x} git commit -m x"])
def test_a_git_location_assignment_in_the_command_still_stops(repo, tmp_path, command):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    result = _stopped_in(repo, wt, command.format(x=_fwd(tmp_path / "x")), crew_mass.MASS_DELETE)
    assert "not read here" in result["reason"], result


def _tracking(repo, upstream="fork", branch="feat", count=30):
    """`repo` on `branch` with `count` new files committed and ALREADY pushed to
    `<upstream>/<branch>`, which it tracks. Remotes `origin` and `fork` exist; origin/HEAD,
    origin/main and origin/master do not (unless the caller made one)."""
    for name in ("origin", "fork"):
        git(repo, "remote", "add", name, f"https://example.invalid/{name}.git")
    if branch != "main":
        git(repo, "checkout", "-qb", branch)
    _fill(repo / "new", count)
    _commit_all(repo, "new files")
    git(repo, "update-ref", f"refs/remotes/{upstream}/{branch}", "HEAD")
    git(repo, "config", f"branch.{branch}.remote", upstream)
    git(repo, "config", f"branch.{branch}.merge", f"refs/heads/{branch}")
    assert git(repo, "rev-parse", "--abbrev-ref", "@{u}") == f"{upstream}/{branch}"


def _no_origin_base(repo):
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        assert not git(repo, "rev-parse", "--verify", "-q", ref, check=False)


# Round 12 (BLOCK-1), option (a): with NO origin/HEAD, origin/main or origin/master there is
# no base, and every push is asked - exactly what main does. Rounds 9-11 measured such a push
# against the branch's upstream when its TEXT sent it there; git decides where a push goes from
# configuration the text does not show, so `git -c remote.pushDefault=origin push` sent 30
# files to origin and counted 0. The fixture: `feat` holds 30 new files, tracks fork/feat and
# is already pushed there, so anything measured against the upstream counts 0 and passes.
_PUSH_ELSEWHERE = [
    "git push origin HEAD:main", "git push origin feat", "git push origin HEAD",
    "git push -u origin feat", "git push origin feat:refs/heads/other", "git push --all origin",
    "git push --mirror origin",
    "git push origin", "git push --set-upstream origin feat", "git push origin refs/heads/feat",
    "git push fork feat:other", "git push fork HEAD:main", "git push fork main",
    "git push fork main:feat", "git push fork +feat", "git push fork :feat",
    "git push fork feat main", "git push --all", "git push --mirror", "git push --tags",
    "git push --all fork", "git push --mirror fork", "git push --tags fork feat",
    "git push --repo=origin", "git push -o ci.skip origin feat", "git push -uq origin feat",
    "git push --follow-tags", "git push --prune fork", "git push fork @",
    "git push https://example.invalid/origin.git feat", "git -C . push origin feat",
]
# The text of each of these says "to the upstream"; git's configuration may say otherwise.
_PUSH_TO_UPSTREAM = [
    "git push", "git push fork feat", "git push fork", "git push fork HEAD",
    "git push fork feat:feat", "git push fork HEAD:feat",
    "git push fork refs/heads/feat:refs/heads/feat", "git push -u fork feat",
    "git push --set-upstream fork feat", "git push -q fork feat", "git push --no-verify",
    "git push -v", "git push -u", "git push -v fork", "git push --progress fork feat",
]
# The reviewer's 24 `-c` spellings and the ones past them: each makes git push to origin (or
# everything, or a mirror) while the text names the upstream or nothing.
_PUSH_CONFIG_OPTS = [
    "-c remote.pushDefault=origin", "-c remote.pushdefault=origin",
    "-c branch.feat.pushRemote=origin", "-c branch.feat.remote=origin",
    "-c push.default=matching", "-c push.default=current", "-c push.default=nothing",
    "-c remote.fork.pushurl={origin}", "-c remote.fork.url={origin}",
    "-c url.{origin}.insteadOf=https://example.invalid/fork.git",
    "-c url.{origin}.pushInsteadOf=https://example.invalid/fork.git",
    "-c remote.fork.push=refs/heads/feat:refs/heads/main",
    "-c remote.fork.push=refs/heads/*:refs/heads/*", "-c remote.fork.mirror=true",
    "-c push.followTags=true", "-c branch.feat.merge=refs/heads/main",
    "-c include.path={origin}/cfg", "--config-env=remote.pushDefault=ORIGIN",
    "--config-env remote.pushDefault=ORIGIN", "-c remote.pushDefault=origin -c x.y=z",
    "-c x.y=z -c remote.pushDefault=origin", "-C . -c remote.pushDefault=origin",
    "-c remote.pushDefault=origin -C .", "--no-pager -c remote.pushDefault=origin",
]
_PUSH_CONFIG_TAILS = ["push", "push -u", "push -v", "push fork", "push fork feat",
                      "push fork HEAD", "push -u fork feat"]
# The same redirection written into the repository's own configuration.
_PUSH_REPO_CONFIG = [
    ("remote.pushDefault", "origin"), ("branch.feat.pushRemote", "origin"),
    ("push.default", "matching"), ("push.default", "current"),
    ("remote.fork.push", "refs/heads/feat:refs/heads/main"),
    ("remote.fork.pushurl", "{origin}"), ("remote.fork.mirror", "true"),
    ("url.{origin}.insteadOf", "https://example.invalid/fork.git"),
    ("url.{origin}.pushInsteadOf", "https://example.invalid/fork.git"),
]
_NO_BASE = "origin/master are all missing"


@pytest.mark.parametrize("command", _PUSH_ELSEWHERE + _PUSH_TO_UPSTREAM)
def test_no_push_is_measured_against_the_upstream_when_no_origin_ref_exists(repo, command):
    _tracking(repo)
    _no_origin_base(repo)
    result = _stops(repo, command, crew_mass.MASS_CREATE)
    assert _NO_BASE in result["reason"] and "upstream is not used" in result["reason"], result


def test_the_branch_upstream_is_not_a_base_when_no_origin_ref_exists(repo):
    """Nothing new, 2 new files or 25: with no origin ref the count cannot be taken, as on
    main. (Rounds 9-11 passed the first two as "0 against fork/feat".)"""
    _tracking(repo)
    _no_origin_base(repo)
    _stops(repo, "git push", crew_mass.MASS_CREATE)
    _fill(repo / "q", 2)
    _commit_all(repo, "two")
    for command in ("git push", "git push fork feat"):
        result = _stops(repo, command, crew_mass.MASS_CREATE)
        assert "could not be counted" in result["reason"], result


@pytest.mark.parametrize("opts", _PUSH_CONFIG_OPTS)
def test_a_push_redirected_by_a_c_option_is_asked(repo, tmp_path, opts):
    """BLOCK-1 as reported: `git -c remote.pushDefault=origin push` pushed 30 files to a bare
    origin and was allowed (measured against fork/feat: 0)."""
    _tracking(repo)
    _no_origin_base(repo)
    opts = opts.format(origin=_fwd(tmp_path / "origin.git"))
    for tail in _PUSH_CONFIG_TAILS:
        for tool in ("Bash", "PowerShell"):
            result = _stops(repo, f"git {opts} {tail}", crew_mass.MASS_CREATE, tool=tool)
            assert "could not be counted" in result["reason"], (tail, tool, result)


@pytest.mark.parametrize("key,value", _PUSH_REPO_CONFIG)
def test_a_push_redirected_by_the_repository_config_is_asked(repo, tmp_path, key, value):
    _tracking(repo)
    _no_origin_base(repo)
    origin = _fwd(tmp_path / "origin.git")
    git(repo, "config", key.format(origin=origin), value.format(origin=origin))
    for command in ("git push", "git push fork", "git push fork feat", "git push -u fork feat",
                    "git push fork HEAD"):
        _stops(repo, command, crew_mass.MASS_CREATE)


def test_the_push_the_reviewer_ran_really_goes_to_origin_and_is_asked(repo, tmp_path):
    """The reproduction itself, against two bare repositories: git's own dry run says the
    `-c` push goes to origin (which has none of the 30 files), and the guard asks."""
    bare = {}
    for name in ("origin", "fork"):
        bare[name] = tmp_path / f"{name}.git"
        git(tmp_path, "init", "-q", "--bare", str(bare[name]))
        git(repo, "remote", "add", name, str(bare[name]))
    git(repo, "checkout", "-qb", "feat")
    _fill(repo / "new", 30)
    _commit_all(repo, "new files")
    git(repo, "push", "-q", "-u", "fork", "feat")
    _no_origin_base(repo)
    assert git(repo, "rev-parse", "--abbrev-ref", "@{u}") == "fork/feat"
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "remote.pushDefault=origin", "-c", "push.default=current",
         "push", "--dry-run", "--porcelain"], capture_output=True, text=True, check=False)
    assert done.returncode == 0 and "origin.git" in done.stdout and "[new branch]" in done.stdout, \
        (done.stdout, done.stderr)
    for command in ("git -c remote.pushDefault=origin push",
                    "git -c remote.pushDefault=origin -c push.default=current push",
                    "git -c remote.pushDefault=origin push -u", "git push"):
        _stops(repo, command, crew_mass.MASS_CREATE)


def test_the_default_branch_is_measured_against_its_upstream_only_for_a_push_to_it(repo):
    """main's own upstream case, kept: on the default branch (origin/main is HEAD's own
    branch) the base is the upstream. Stricter than main, on purpose: only a push whose text
    sends the branch TO that upstream is measured against it. A push that names another
    remote, a refspec, an option, or carries `-c` / `--config-env` is asked, and so is
    `git push fork` when remote.pushDefault says origin (nothing would be pushed; main allows
    it). Recorded gap, the same on main: a pushurl / insteadOf / remote.<n>.push in the
    repository's config is not read here."""
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _tracking(repo, branch="main")
    for command in ("git push origin main", "git push origin HEAD", "git push origin",
                    "git push origin HEAD:main", "git push --all origin", "git push --all",
                    "git push --mirror fork", "git push --tags", "git push --repo=origin",
                    "git push fork main:other", "git push fork other", "git push fork +main",
                    "git push fork @", "git push fork :main", "git push fork main other",
                    "git push -uq fork main", "git push -o ci.skip fork main",
                    "git -c remote.pushDefault=origin push", "git -c x.y=z push fork main",
                    "git --config-env=remote.pushDefault=ORIGIN push",
                    "git -C . -c push.default=matching push"):
        result = _stops(repo, command, crew_mass.MASS_CREATE)
        assert "other than its upstream `fork/main`" in result["reason"], (command, result)
    for command in ("git push", "git push fork main", "git push fork", "git -C . push",
                    "git push fork HEAD", "git push fork main:main", "git push fork HEAD:main",
                    "git push fork refs/heads/main:refs/heads/main", "git push -u fork main",
                    "git push -q", "git push --no-verify fork"):
        _passes(repo, command)
    git(repo, "config", "remote.pushDefault", "origin")
    for command in ("git push", "git push fork"):
        _stops(repo, command, crew_mass.MASS_CREATE)
    _passes(repo, "git push fork main")
    # 25 more files really are new against fork/main: counted, and stopped
    git(repo, "config", "--unset", "remote.pushDefault")
    _fill(repo / "r", 25)
    _commit_all(repo, "twenty-five")
    _stops(repo, "git push", crew_mass.MASS_CREATE)


def test_gh_pr_create_does_not_use_the_branch_upstream_as_its_base(repo):
    """Round 9 (F-A): a PR's base is the repository's default branch, not the branch's
    upstream (a fork's feature branch, say). With no origin/HEAD, origin/main or origin/master
    `gh pr create` says it could not tell, and so does `git push` (round 12)."""
    git(repo, "checkout", "-qb", "feat")
    git(repo, "branch", "-q", "--set-upstream-to=main", "feat")
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        assert not git(repo, "rev-parse", "--verify", "-q", ref, check=False)
    _fill(repo / "r", 30)
    _commit_all(repo, "thirty")
    result = _stops(repo, "gh pr create --fill")
    assert "pull request" in result["reason"] and "origin/main" in result["reason"], result
    _stops(repo, "git push origin feat", crew_mass.MASS_CREATE)
    _stops(repo, "git push", crew_mass.MASS_CREATE)


def test_gh_pr_create_from_the_default_branch_is_asked(repo):
    """Stricter than main, on purpose (main measures it against the branch's upstream): a
    pull request FROM the default branch has no base to count against."""
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _tracking(repo, branch="main", count=2)
    result = _stops(repo, "gh pr create --fill")
    assert "is the default branch" in result["reason"], result


_LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                 reason="/proc/self/cwd exists on Linux only")
_POSIX_ONLY = pytest.mark.skipif(os.name == "nt",
                                 reason="the symlink walk is POSIX's (Windows judges the text)")


@pytest.mark.parametrize("target", [
    "/proc/self/cwd", "/proc/1/cwd", "/proc/", "/proc", "/dev/fd/3", "/dev/shm/x", "/dev",
    # round 10 (BLOCK-1): the same directory under another spelling
    "//proc/self/cwd", "///proc/self/cwd", "/./proc/self/cwd", "/././proc/self/cwd",
    "/.//proc/self/cwd", "//proc", "/./proc", "/proc//self/cwd", "/proc/./self/cwd",
    "//dev/fd/3", "/./dev/fd/3", "///dev", "/PROC/self/cwd", "/Dev/fd/3",
    "/proc/thread-self/cwd", "/dev/stdin"])
def test_a_per_process_cd_target_is_never_followed(target):
    """Round 9 (F-B), round 10 (BLOCK-1): `/proc/self/cwd` is the directory of whichever
    process reads it, so `cd /proc/self/cwd && git commit` names the shell's directory to bash
    and the hook's own to this process - however the path is spelled. On Windows `_resolve`
    refuses any such path anyway; this holds the text rule everywhere, and the Linux-only cases
    below hold the resolved-path walk and the calls."""
    assert crew_mass._names_per_process(target)  # pylint: disable=protected-access
    assert crew_mass._per_process_dir(target)  # pylint: disable=protected-access
    for shell in ("bash", "powershell"):
        assert crew_mass.leading_cd(f"cd {target} && git commit -m x", "/", shell) is None


@pytest.mark.parametrize("target", ["/procfs/x", "/devices/x", "/home/proc/x", "/opt/dev/x",
                                    "/tmp/proc", "proc/x", "dev", "./proc/x"])
def test_a_path_that_only_looks_like_proc_or_dev_is_not_per_process(target):
    assert not crew_mass._names_per_process(target)  # pylint: disable=protected-access
    assert not crew_mass._per_process_dir(target)  # pylint: disable=protected-access


@_LINUX_ONLY
def test_cd_into_proc_self_cwd_is_could_not_tell_on_linux():
    assert os.path.isdir("/proc/self/cwd")
    for target in ("/proc/self/cwd", "//proc/self/cwd", "/./proc/self/cwd", "/proc/self/cwd/",
                   "/proc/thread-self/cwd", f"/proc/{os.getpid()}/cwd"):
        assert crew_mass.leading_cd(f"cd {target} && git commit -m x", "/", "bash") is None
        assert crew_mass.leading_cd(f"cd {target}; git commit -m x", "/", "powershell") is None


def _proc_links(folder):
    """The round-10 symlinks, made in `folder`: `lncwd` -> /proc/self/cwd, `lnproc` -> /proc,
    `lnself` -> /proc/self, and the shapes past them."""
    for name, dest in (("lncwd", "/proc/self/cwd"), ("lnproc", "/proc"),
                       ("lnself", "/proc/self"), ("ln2", "lncwd"), ("lnroot", "/"),
                       ("lnslash", "//proc/self/cwd"), ("lnfd", "/dev/fd"),
                       ("lnrel", os.path.relpath("/proc/self/cwd", str(folder)))):
        os.symlink(dest, str(folder / name))
    (folder / "d").mkdir()
    os.symlink("../lncwd", str(folder / "d" / "up"))


# Round 10 (BLOCK-1, FIX-2). {t} is a directory that holds the links; the shell's directory
# (the payload cwd, a worktree with 32 staged files) holds them too, for the relative forms.
_PROC_SPELLINGS_BASH = [
    "cd //proc/self/cwd && git commit -m x", "cd ///proc/self/cwd && git commit -m x",
    "cd /./proc/self/cwd && git commit -m x", "cd {t}/lncwd && git commit -m x",
    "cd ./lncwd && git commit -m x", "cd {t}/lnproc/self/cwd && git commit -m x",
    "cd {t}/lnself/cwd && git commit -m x",
    # past the reviewer's list
    "cd /proc/self/cwd/ && git commit -m x", "cd /proc//self/./cwd && git commit -m x",
    "cd /proc/thread-self/cwd && git commit -m x", "cd {t}/lncwd/ && git commit -m x",
    "cd {t}/lncwd/. && git commit -m x", "cd {t}//lncwd && git commit -m x",
    "cd {t}/ln2 && git commit -m x", "cd ./ln2 && git commit -m x",
    "cd {t}/lnslash && git commit -m x", "cd {t}/lnrel && git commit -m x",
    "cd {t}/d/up && git commit -m x", "cd {t}/lnroot/proc/self/cwd && git commit -m x",
    "cd ./lnproc/self/cwd && git commit -m x", "cd ./lnself/cwd && git commit -m x",
    "cd {t}/lnroot{t}/lncwd && git commit -m x",
    # FIX-2: the same directory as a -C value, alone and in a chain
    "git -C /proc/self/cwd commit -m x", "git -C //proc/self/cwd commit -m x",
    "git -C /./proc/self/cwd commit -m x", "git -C {t}/lncwd commit -m x",
    "git -C lncwd commit -m x", "git -C {t}/lnproc/self/cwd commit -m x",
    "git -C {t}/lnself/cwd commit -m x", "git -C /proc/self/cwd/sub -C .. commit -m x",
    "git -C / -C proc/self/cwd commit -m x", "git -C {t} -C lncwd commit -m x",
    "git -C {t}/d -C up commit -m x", "git -C {t}/d -C ../lncwd commit -m x",
    "git -C {t}/lncwd/sub -C .. commit -m x", "git -C {t}/lnproc -C self -C cwd commit -m x",
    "git -C sub -C ../lncwd commit -m x", "git -C {t}/lnroot -C proc/self/cwd commit -m x",
]
_PROC_SPELLINGS_PS = [
    "cd //proc/self/cwd; git commit -m x", "cd /./proc/self/cwd; git commit -m x",
    "Set-Location {t}/lncwd; git commit -m x", "cd lncwd; git commit -m x",
    "sl lnproc/self/cwd; git commit -m x",
    # past the reviewer's list
    "cd ///proc/self/cwd && git commit -m x", "sl lnself/cwd && git commit -m x",
    "Set-Location ./ln2; git commit -m x", "cd {t}/lnrel; git commit -m x",
    "cd lncwd/; git commit -m x", "cd {t}/d/up; git commit -m x",
    "git -C lncwd commit -m x", "git -C //proc/self/cwd commit -m x",
]


def _shell_in_big_hook_in_clean(repo, tmp_path, monkeypatch):
    """The reviewer's scene: THIS process (the hook) sits in the clean repo, so that is what
    `/proc/self/cwd` names here; the shell sits in a worktree with 32 staged files."""
    wt = _big_wt(repo, tmp_path, count=32)
    links = tmp_path / "links"
    links.mkdir()
    for folder in (links, wt):
        _proc_links(folder)
    for folder in (repo, wt):
        (folder / "sub").mkdir(exist_ok=True)
    monkeypatch.chdir(repo)
    return wt, links


@_LINUX_ONLY
@pytest.mark.parametrize("form", _PROC_SPELLINGS_BASH)
def test_a_cd_or_dash_C_that_reaches_proc_is_asked_however_it_is_spelled(
        repo, tmp_path, monkeypatch, form):
    wt, links = _shell_in_big_hook_in_clean(repo, tmp_path, monkeypatch)
    result = _stopped_in(repo, wt, form.format(t=links), crew_mass.MASS_CREATE)
    assert "could not be counted" in result["reason"], result


@_LINUX_ONLY
@pytest.mark.parametrize("form", _PROC_SPELLINGS_PS)
def test_a_powershell_cd_or_dash_C_that_reaches_proc_is_asked(repo, tmp_path, monkeypatch, form):
    wt, links = _shell_in_big_hook_in_clean(repo, tmp_path, monkeypatch)
    _ps_stopped(repo, wt, form.format(t=links))


@_LINUX_ONLY
def test_a_dash_C_that_reaches_proc_names_the_reason(repo, tmp_path, monkeypatch):
    wt, links = _shell_in_big_hook_in_clean(repo, tmp_path, monkeypatch)
    for form in ("git -C /proc/self/cwd commit -m x", f"git -C {links}/lncwd commit -m x",
                 "git -C /proc/self/cwd/sub -C .. commit -m x"):
        result = _stopped_in(repo, wt, form, crew_mass.MASS_CREATE)
        assert "/proc or /dev" in result["reason"], result


@_POSIX_ONLY
def test_an_ordinary_symlink_is_still_followed_and_counted_where_it_points(repo, tmp_path):
    """The walk refuses /proc and /dev, not symlinks: a link to a real directory is the same
    directory for the shell and for this process."""
    wt = _big_wt(repo, tmp_path, count=32)
    os.symlink(str(wt), str(tmp_path / "lnwt"))
    os.symlink(str(repo), str(tmp_path / "lnrepo"))
    os.symlink("lnrepo", str(tmp_path / "lnchain"))
    for name in ("lnwt", "lnrepo", "lnchain"):
        assert not crew_mass._per_process_dir(str(tmp_path / name))  # pylint: disable=protected-access
    assert crew_mass.leading_cd(f"cd {tmp_path}/lnrepo && git status", str(wt), "bash")
    _clean_in(repo, wt, f"cd {tmp_path}/lnrepo && git commit -m x")
    _clean_in(repo, wt, f"cd {tmp_path}/lnchain && git commit -m x")
    _clean_in(repo, wt, f"git -C {tmp_path}/lnrepo commit -m x")
    _stopped_in(repo, repo, f"cd {tmp_path}/lnwt && git commit -m x", crew_mass.MASS_CREATE)
    _stopped_in(repo, repo, f"git -C {tmp_path}/lnwt commit -m x", crew_mass.MASS_CREATE)


@_POSIX_ONLY
def test_a_symlink_walk_that_cannot_finish_is_per_process_and_a_missing_path_is_not(tmp_path):
    """Could not tell is never "not per-process": a link loop is refused. A path that is not
    there has nothing to follow (the caller's own existence check refuses it)."""
    os.symlink("loop", str(tmp_path / "loop"))
    os.symlink("b", str(tmp_path / "a"))
    os.symlink("a", str(tmp_path / "b"))
    for name in ("loop", "a", "loop/x"):
        assert crew_mass._per_process_dir(str(tmp_path / name))  # pylint: disable=protected-access
    assert not crew_mass._per_process_dir(str(tmp_path / "missing" / "x"))  # pylint: disable=protected-access
    (tmp_path / "file").write_text("x", encoding="utf-8")
    assert not crew_mass._per_process_dir(str(tmp_path / "file" / "x"))  # pylint: disable=protected-access


@_LINUX_ONLY
def test_the_walk_refuses_proc_by_name_when_no_device_number_can_be_read(tmp_path, monkeypatch):
    """Two checks hold each step: the name (`/proc`, `/dev`) and the device number. The name
    alone must be enough, for a host where the device number cannot be read."""
    _proc_links(tmp_path)
    monkeypatch.setattr(crew_mass, "_special_mounts", lambda: (set(), set()))
    os.symlink("/dev/shm", str(tmp_path / "lnshm"))
    os.symlink("/proc", str(tmp_path / "lnp"))
    for name in ("lncwd", "lnproc/self/cwd", "lnself/cwd", "ln2", "lnrel", "d/up", "lnfd",
                 "lnroot/proc/self/cwd", "lnslash", "lnshm", "lnp", "lnp/sys",
                 "lnroot/dev/shm"):
        assert crew_mass._per_process_dir(str(tmp_path / name)), name  # pylint: disable=protected-access


@_POSIX_ONLY
def test_a_directory_on_the_proc_device_is_per_process_wherever_it_is_mounted(tmp_path,
                                                                              monkeypatch):
    """A directory ON a pseudo file system is refused by its device number, whatever the
    mount point is called. No test can mount one, so the device set is this directory's own."""
    folder = tmp_path / "mnt"
    folder.mkdir()
    assert not crew_mass._per_process_dir(str(folder))  # pylint: disable=protected-access
    monkeypatch.setattr(crew_mass, "_special_mounts",
                        lambda: (set(), {os.stat(str(folder)).st_dev}))
    assert crew_mass._per_process_dir(str(folder))  # pylint: disable=protected-access


# Round 12 (BLOCK-3). As root: `mount -t proc proc <dir>`, then `cd <dir>/self/cwd && git commit`
# and `git -C <dir>/self/cwd commit` were allowed (78 spellings): the second procfs has its own
# device number, so "is it /proc's device" said no. Three rules now, each enough alone: the
# SHAPE of the path (`self/cwd`, `<pid>/root`...), the TYPE of the file system (the mount
# table), and a symlink that reports no length (a procfs magic link).
_PROC_SHAPES = [
    "/mnt/p/self/cwd", "/mnt/p/self/cwd/", "/mnt/p/self/cwd/sub", "/mnt/p/1/cwd", "/x/4321/root",
    "/x/thread-self/cwd", "/x/self/root/etc", "/x/self/fd/3", "/x/self/task/77/cwd",
    "/x/SELF/CWD", "/x/self//cwd", "/x/self/./cwd", "/x/curproc/cwd", "/x/self/exe",
    "/x/self/ns/mnt", "/x/self/map_files/a", "/x/self/fdinfo", "x/self/cwd", "./p/self/cwd",
    "C:/x/self/cwd", "/x/12/fd",
]
_NOT_PROC_SHAPES = ["/home/self/x", "/a/cwd", "/a/12a/cwd", "/srv/1234/data", "/x/self",
                    "/x/selfie/cwd", "/x/self/cwdx", "/x/cwd/self", "/x/root/1", "/self/x/cwd"]


@pytest.mark.parametrize("target", _PROC_SHAPES)
def test_a_self_cwd_shaped_target_is_per_process_wherever_it_is_mounted(target):
    assert crew_mass._names_per_process(target), target  # pylint: disable=protected-access
    assert crew_mass._per_process_dir(target), target  # pylint: disable=protected-access


@pytest.mark.parametrize("target", _NOT_PROC_SHAPES)
def test_a_path_that_only_resembles_a_proc_entry_is_not_per_process(target):
    assert not crew_mass._names_per_process(target), target  # pylint: disable=protected-access


def _fake_procfs(tmp_path, repo):
    """What `mount -t proc proc <tmp>/p` looks like to a path walk, without root: `p/self/cwd`
    and `p/77/cwd` are links to THIS process's directory (the clean `repo`), as the magic links
    are for the hook."""
    for owner in ("self", "77", "thread-self"):
        (tmp_path / "p" / owner).mkdir(parents=True)
        os.symlink(str(repo), str(tmp_path / "p" / owner / "cwd"))
        os.symlink("/", str(tmp_path / "p" / owner / "root"))
    return tmp_path / "p"


_MOUNTED_PROC_FORMS = [
    "cd {p}/self/cwd && git commit -m x", "cd {p}/77/cwd && git commit -m x",
    "cd {p}/thread-self/cwd && git commit -m x", "cd {p}//self/./cwd/ && git commit -m x",
    "cd {p}/self/root{clean} && git commit -m x", "cd {t}/lnself/cwd && git commit -m x",
    "cd {t}/lnp/self/cwd && git commit -m x", "cd {t}/lncwd && git commit -m x",
    "git -C {p}/self/cwd commit -m x", "git -C {p}/77/cwd commit -m x",
    "git -C {p} -C self/cwd commit -m x", "git -C {p}/self -C cwd commit -m x",
    "git -C {t}/lnself/cwd commit -m x", "git -C {t}/lnself -C cwd commit -m x",
    "git -C {t}/lncwd commit -m x", "git -C {p}/self/root{clean} commit -m x",
    "git -C {p}/self/cwd/sub -C .. commit -m x",
]


@_POSIX_ONLY
@pytest.mark.parametrize("form", _MOUNTED_PROC_FORMS)
def test_a_procfs_mounted_elsewhere_is_asked_by_its_shape(repo, tmp_path, monkeypatch, form):
    """The mount table is emptied, so only the shape rule (on the text and on the walked path)
    stands between these and a count taken in the clean repo."""
    wt = _big_wt(repo, tmp_path, count=32)
    proc = _fake_procfs(tmp_path, repo)
    (repo / "sub").mkdir(exist_ok=True)
    os.symlink(str(proc / "self"), str(tmp_path / "lnself"))
    os.symlink(str(proc), str(tmp_path / "lnp"))
    os.symlink(str(proc / "self" / "cwd"), str(tmp_path / "lncwd"))
    monkeypatch.setattr(crew_mass, "_special_mounts", lambda: (set(), set()))
    command = form.format(p=proc, t=tmp_path, clean=repo)
    result = _stopped_in(repo, wt, command, crew_mass.MASS_CREATE)
    assert "could not be counted" in result["reason"], result
    _ps_stopped(repo, wt, command)


@_POSIX_ONLY
def test_a_pseudo_file_system_mount_point_is_asked_by_its_type(repo, tmp_path, monkeypatch):
    """`mount --bind /proc/self <dir>`: no `self` in the path, so the shape says nothing. The
    mount table names the file system, and the walk refuses the mount point and what is under
    it - reached directly, through a link, or as a -C chain."""
    wt = _big_wt(repo, tmp_path, count=32)
    bound = tmp_path / "bound"
    bound.mkdir()
    os.symlink(str(repo), str(bound / "here"))
    os.symlink(str(bound), str(tmp_path / "lnbound"))
    forms = ("cd {b}/here && git commit -m x", "cd {t}/lnbound/here && git commit -m x",
             "git -C {b}/here commit -m x", "git -C {b} -C here commit -m x",
             "git -C {t}/lnbound/here commit -m x")
    for form in forms:  # an ordinary directory: followed, counted in the clean repo
        _clean_in(repo, wt, form.format(b=bound, t=tmp_path))
    monkeypatch.setattr(crew_mass, "_special_mounts", lambda: ({str(bound)}, set()))
    assert crew_mass._per_process_dir(str(bound))  # pylint: disable=protected-access
    for form in forms:
        _stopped_in(repo, wt, form.format(b=bound, t=tmp_path), crew_mass.MASS_CREATE)


@_POSIX_ONLY
def test_a_symlink_that_reports_no_length_is_a_magic_link(repo, tmp_path, monkeypatch):
    """A procfs magic link (`cwd`, `root`, `fd/3`) has st_size 0; a real symlink has its
    target's length. With no name, shape or mount to go by, that alone refuses the path."""
    wt = _big_wt(repo, tmp_path, count=32)
    os.symlink(str(repo), str(tmp_path / "magic"))
    monkeypatch.setattr(crew_mass, "_special_mounts", lambda: (set(), set()))
    _clean_in(repo, wt, f"cd {tmp_path}/magic && git commit -m x")
    real = os.lstat

    def lstat(path, *args, **kwargs):
        info = real(path, *args, **kwargs)
        if str(path) == str(tmp_path / "magic"):
            fields = list(info)
            fields[6] = 0  # st_size
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(crew_mass.os, "lstat", lstat)
    assert crew_mass._per_process_dir(str(tmp_path / "magic"))  # pylint: disable=protected-access
    _stopped_in(repo, wt, f"cd {tmp_path}/magic && git commit -m x", crew_mass.MASS_CREATE)
    _stopped_in(repo, wt, f"git -C {tmp_path}/magic commit -m x", crew_mass.MASS_CREATE)


@_POSIX_ONLY
def test_a_mount_table_that_cannot_be_read_is_could_not_tell(repo, tmp_path, monkeypatch):
    """An unknown must not collapse into the safe-looking value: with no table, an ordinary
    directory is not known to be ordinary, so a cd or -C into it is asked."""
    wt = _big_wt(repo, tmp_path, count=32)
    monkeypatch.setattr(crew_mass, "_special_mounts", lambda: None)
    assert crew_mass._per_process_dir(str(repo))  # pylint: disable=protected-access
    _stopped_in(repo, wt, f"cd {repo} && git commit -m x", crew_mass.MASS_CREATE)
    result = _stopped_in(repo, wt, f"git -C {repo} commit -m x", crew_mass.MASS_CREATE)
    assert "per process" in result["reason"], result


_MOUNTINFO = """\
22 28 0:21 / /proc rw,nosuid shared:13 - proc proc rw
23 28 0:22 / /sys rw shared:7 - sysfs sysfs rw
24 28 0:5 / /dev rw shared:2 - devtmpfs udev rw,size=1k
25 24 0:23 / /dev/pts rw shared:3 - devpts devpts rw
26 24 0:24 / /dev/shm rw shared:4 - tmpfs tmpfs rw
28 1 8:2 / / rw shared:1 - ext4 /dev/sda2 rw
30 28 0:26 / /tmp rw shared:5 - tmpfs tmpfs rw
97 28 0:55 / /mnt/p rw - proc proc rw
98 28 0:21 /4242 /mnt/bound rw - proc proc rw
99 28 0:60 / /mnt/with\\040space rw master:1 shared:9 - cgroup2 cgroup2 rw
100 28 0:61 / /mnt/fuse rw - fuse.sshfs host:/x rw
101 28 0:62 / /mnt/c rw - 9p C:\\134 rw
"""


def test_the_mount_table_is_read_by_file_system_type():
    """A second procfs (`/mnt/p`) and a bind of `/proc/<pid>` (`/mnt/bound`) are pseudo file
    systems; tmpfs (`/tmp`, `/dev/shm`), ext4, fuse and 9p are not. tmpfs is left out on
    purpose: `/tmp` is tmpfs on many hosts and holds real repositories."""
    points, devices = crew_mass._parse_mountinfo(_MOUNTINFO)  # pylint: disable=protected-access
    assert points == {"/proc", "/sys", "/dev", "/dev/pts", "/mnt/p", "/mnt/bound",
                      "/mnt/with space"}
    assert devices == {crew_mass._device(0, minor) for minor in (21, 22, 5, 23, 55, 60)}  # pylint: disable=protected-access
    # a /dev that is a plain directory of the root file system is in no table: not flagged
    plain = "28 1 8:2 / / rw shared:1 - ext4 /dev/sda2 rw\n22 28 0:21 / /proc rw - proc proc rw\n"
    assert crew_mass._parse_mountinfo(plain) == ({"/proc"}, {crew_mass._device(0, 21)})  # pylint: disable=protected-access
    # an automount point is listed as autofs AND as what is mounted over it: repositories live
    # there (NFS homes), so autofs is no pseudo file system
    home = ("28 1 8:2 / / rw - ext4 /dev/sda2 rw\n40 28 0:44 / /home rw - autofs systemd-1 rw\n"
            "41 40 0:50 / /home rw - nfs4 srv:/home rw\n")
    assert crew_mass._parse_mountinfo(home) == (set(), set())  # pylint: disable=protected-access


@pytest.mark.parametrize("text", ["garbage\n", "22 28 0:21 / /proc rw shared:13 proc proc rw\n",
                                  "22 28 x:y / /proc rw - proc proc rw\n",
                                  "22 28 0:21 / /proc rw - \n", "22 28 0:21 - proc proc rw\n"])
def test_a_mount_table_line_that_cannot_be_read_is_not_an_empty_table(text):
    assert crew_mass._parse_mountinfo(_MOUNTINFO + text) is None  # pylint: disable=protected-access


def test_a_dev_that_is_not_its_own_mount_does_not_flag_the_root_file_system(monkeypatch):
    """Round 11 NIT: where `/dev` is a plain directory it shares the root's device number, and
    the old device rule made EVERY path on the root file system per-process. With no mount
    table (macOS, BSD) only a `/proc` or `/dev` that is a mount of its own lends its device."""
    class Info:  # pylint: disable=too-few-public-methods
        def __init__(self, device):
            self.st_dev = device
    devices, real = {"/": 7, "/dev": 7, "/proc": 9}, os.stat
    monkeypatch.setattr(crew_mass.os, "stat", lambda path, *a, **k: (
        Info(devices[path]) if path in devices else real(path, *a, **k)))
    assert crew_mass._root_mounts() == ({"/proc", "/dev"}, {9})  # pylint: disable=protected-access
    devices["/dev"] = 8
    assert crew_mass._root_mounts() == ({"/proc", "/dev"}, {8, 9})  # pylint: disable=protected-access


@_LINUX_ONLY
def test_the_real_mount_table_here_names_proc_and_not_this_directory(tmp_path, monkeypatch):
    points, devices = crew_mass._special_mounts()  # pylint: disable=protected-access
    assert "/proc" in points and os.stat("/proc").st_dev in devices
    assert os.stat(str(tmp_path)).st_dev not in devices
    assert not crew_mass._per_process_dir(str(tmp_path))  # pylint: disable=protected-access
    # Linux with no table to read (no /proc mounted): could not tell, not "no pseudo mounts"
    monkeypatch.setattr(crew_mass, "_MOUNTINFO", str(tmp_path / "absent"))
    assert crew_mass._special_mounts() is None  # pylint: disable=protected-access
    assert crew_mass._per_process_dir(str(tmp_path))  # pylint: disable=protected-access


@pytest.mark.skipif(os.name != "nt", reason="the /c/ drive form is mapped on Windows only")
def test_powershell_does_not_read_a_slash_drive_path_as_a_git_bash_drive(tmp_path):
    """Round 9 (F-C), verified on this host: `Set-Location /c/Users` from drive D fails with
    `Cannot find path 'D:/c/Users'`; PowerShell reads `/c/x` against the CURRENT drive. Git Bash
    maps it to C:/x, so the same text is followed in bash and refused in PowerShell."""
    folder = tmp_path / "d"
    folder.mkdir()
    posix = "/" + _fwd(folder)[0].lower() + _fwd(folder)[2:]
    assert crew_mass.leading_cd(f"cd {posix} && git status", "/", "powershell") is None
    assert crew_mass.leading_cd(f"cd {posix}; git status", "/", "powershell") is None
    assert crew_mass.leading_cd(f"cd {posix} && git status", "/", "bash") == os.path.normpath(
        str(folder))


@pytest.mark.parametrize("opt", ["--attr-source HEAD", "--attr-source=HEAD",
                                 "--super-prefix x/"])
def test_git_value_options_do_not_hide_the_subcommand(repo, tmp_path, opt):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    _clean_in(repo, wt, f"git {opt} commit -m x")
    git(wt, "reset", "-q")
    _fill(wt / "docs", 22)
    git(wt, "add", "-A")
    _stopped_in(repo, wt, f"git {opt} commit -m x", crew_mass.MASS_CREATE)
    _stopped_in(repo, repo, f"git -C {wt} {opt} commit -m x", crew_mass.MASS_CREATE)


def test_a_repeated_C_is_resolved_cumulatively(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    _clean_in(repo, repo, f"git -C {tmp_path} -C wt-records commit -m x")
    _clean_in(repo, repo, f"git -C {tmp_path} -C . -C wt-records/docs commit -m x")
    git(wt, "reset", "-q")
    _fill(wt / "docs", 22)
    git(wt, "add", "-A")
    _stopped_in(repo, repo, f"git -C {tmp_path} -C wt-records commit -m x", crew_mass.MASS_CREATE)
    # the second -C is absolute: it replaces the first
    _stopped_in(repo, repo, f"git -C {repo} -C {wt} commit -m x", crew_mass.MASS_CREATE)


@pytest.mark.parametrize("env", ["GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                                 "GIT_CEILING_DIRECTORIES", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                                 "GIT_NAMESPACE"])
def test_a_git_location_variable_in_the_command_is_could_not_tell(repo, tmp_path, env):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    result = _stopped_in(repo, wt, f"{env}={tmp_path}/x git commit -m x", crew_mass.MASS_DELETE)
    assert "not read here" in result["reason"], result
    _clean_in(repo, wt, "git commit -m x")


@pytest.mark.parametrize("prefix", ["git --git-dir={g}", "git --git-dir {g}",
                                    "git --work-tree={w}", "GIT_DIR={g} git"])
def test_a_command_that_redirects_git_to_another_repo_is_could_not_tell(repo, tmp_path, prefix):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    command = prefix.format(g=repo / ".git", w=wt) + " commit -m x"
    result = _stopped_in(repo, repo, command, crew_mass.MASS_DELETE)
    assert "not read here" in result["reason"], result["reason"]


@pytest.mark.parametrize("prefix", [
    "git -c k=v --git-dir={g} --work-tree={w}",
    "git -C {w} --git-dir={g} --work-tree={w}",
    "git -c a=b -C {w} --git-dir={g}",
    "git -C {w} -c k=v --git-dir={g}",
    "git -c a=b -c c=d --work-tree={w}",
    "git --namespace ns --git-dir={g}",
])
def test_a_redirect_after_a_c_or_C_value_is_still_could_not_tell(repo, tmp_path, prefix):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    command = prefix.format(g=repo / ".git", w=wt) + " commit -m x"
    result = _stopped_in(repo, repo, command, crew_mass.MASS_DELETE)
    assert "not read here" in result["reason"], result["reason"]


def test_a_c_option_without_a_redirect_is_still_counted_and_allowed(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    _clean_in(repo, wt, "git -c k=v commit -m x")
    _clean_in(repo, wt, "git -c a=b -c c=d commit -m x")
    _clean_in(repo, repo, f"git -C {wt} -c k=v commit -m x")


@pytest.mark.parametrize("make", [
    lambda wt, other: f"cd {wt}/missing && git commit -m x",       # not a directory
    lambda wt, other: f"cd {wt} && cd {other} && git commit -m x",  # a second move
    lambda wt, other: f"git commit -m x && cd {wt}",                # the cd is not first
    lambda wt, other: f"cd {wt} || git commit -m x",                # not guaranteed
    lambda wt, other: "cd $DEST && git commit -m x",                # not a literal
    lambda wt, other: f"cd {wt} && (cd {other}; git commit -m x)",  # moved again
])
def test_any_other_cd_is_still_could_not_tell_and_stops(repo, tmp_path, make):
    wt = _worktree(repo, tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    result = _stopped_in(repo, repo, make(wt, other), crew_mass.MASS_DELETE)
    assert "could not be counted" in result["reason"]
    assert "moves the shell" in result["reason"]


def test_the_refusal_names_the_real_reason(repo, tmp_path):
    wt = _worktree(repo, tmp_path)
    result = _stopped_in(repo, repo, f"cd {wt} && cd {tmp_path} && git commit -m x",
                         crew_mass.MASS_CREATE)
    assert "moves the shell" in result["reason"]
    # git itself failing is quoted, not summarised
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    result = _stopped_in(repo, repo, f"git -C {outside} commit -m x", crew_mass.MASS_DELETE)
    assert "`git diff --name-status` exited" in result["reason"], result["reason"]
    # no base at all: the missing refs are named
    _fill(repo / "q", 5)
    _commit_all(repo)
    result = _stopped_in(repo, repo, "git push origin HEAD", crew_mass.MASS_DELETE)
    assert "origin/main" in result["reason"] and "upstream" in result["reason"]


def test_git_timing_out_or_missing_is_named(repo):
    def timeout(argv, **_kwargs):
        raise crew_mass.subprocess.TimeoutExpired(argv, 15)

    def missing(argv, **_kwargs):
        raise FileNotFoundError("git")
    for runner, words in ((timeout, "timed out after"), (missing, "could not run")):
        spec = crew_mass.classify("git", ["commit"], "bash", False)[0]
        assert crew_mass.count(spec, str(repo), False, runner) is None
        assert words in spec.why, spec.why


def test_a_repo_that_git_cannot_read_says_rev_parse_failed(repo):
    def broken(argv, **_kwargs):
        class Done:  # pylint: disable=too-few-public-methods
            returncode, stdout, stderr = 128, "", "fatal: not a git repository\n"
        return Done()
    spec = crew_mass.classify("git", ["commit"], "bash", False)[0]
    verdict = crew_mass.judge(spec, "git commit", str(repo), False, False,
                              crew_mass.settings(str(repo)), runner=broken)
    assert verdict[0] == "ask" and "git rev-parse failed:" in verdict[1] \
        and "exited 128" in verdict[1], verdict


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


# --- round 7 (crew 1.3.52) -------------------------------------------------------------

@pytest.mark.parametrize("command", _LOCATION_MESSAGES_PS)
def test_a_powershell_mention_of_a_git_variable_is_not_an_assignment(command):
    assert not crew_mass.sets_git_location(command, "powershell"), command


def test_a_git_variable_mention_is_counted_not_refused_and_the_count_is_still_taken(
        repo, tmp_path):
    """F4: these were asked on the PR and allowed on main (0 files). They must be counted."""
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    mentions = ('git commit -m "GIT_DIR=/x was wrong"', "git commit -m GIT_DIR",
                "unset GIT_DIR GIT_WORK_TREE; git commit -m x",
                "grep -rn GIT_INDEX_FILE . ; git commit -m x", "env -u GIT_DIR git commit -m x")
    for command in mentions:
        _clean_in(repo, wt, command)
    git(wt, "reset", "-q")
    _fill(wt / "docs", 22)
    git(wt, "add", "-A")
    for command in mentions:
        _stopped_in(repo, wt, command, crew_mass.MASS_CREATE)


@pytest.mark.parametrize("command", [
    "GIT_INDEX_FILE={x}; git commit -m x",
    "export GIT_INDEX_FILE+={x}; git commit -m x",
    "eval 'export GIT_INDEX_FILE={x}'; git commit -m x",
    "env -S 'X=1 GIT_INDEX_FILE={x} git commit -m x'",
    "export GIT_{{INDEX_FILE,ZZ}}={x}; git commit -m x",
    "GIT_INDEX_FILE+={x} git commit -m x"])
def test_a_cheap_spelling_of_a_git_location_assignment_still_stops(repo, tmp_path, command):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    result = _stopped_in(repo, wt, command.format(x=_fwd(tmp_path / "x")), crew_mass.MASS_DELETE)
    assert "not read here" in result["reason"], result


@pytest.mark.parametrize("command", [
    "${{env:GIT_INDEX_FILE}}='{x}'; git commit -m x", "$env:GIT_INDEX_FILE+='{x}'; git commit -m x",
    "Set-Item -Path Env:/GIT_INDEX_FILE {x}; git commit -m x",
    "1 | % {{ $env:GIT_INDEX_FILE = '{x}' }}; git commit -m x",
    "$env:GIT_INDEX_FILE ??= '{x}'; git commit -m x",
    "New-Item -Path Env: -Name GIT_INDEX_FILE -Value {x}; git commit -m x"])
def test_a_powershell_location_assignment_still_stops(repo, tmp_path, command):
    wt = _worktree(repo, tmp_path)
    _fill(wt / "docs", 2)
    git(wt, "add", "-A")
    _ps_stopped(repo, wt, command.format(x=_fwd(tmp_path / "x")))


@pytest.mark.parametrize("command", [
    "bash <<< 'GIT_INDEX_FILE=x git commit -m y'",
    "bash <<'EOT'\nGIT_INDEX_FILE=x git commit -m y\nEOT",
    "printf -v GIT_INDEX_FILE %s /x; git commit -m x", "n=GIT_INDEX_FILE; export $n=/x"])
def test_the_known_gaps_of_the_git_variable_scan_are_pinned(command):
    """Not caught, as on main (listed in CONFIG.md under the known gaps): the assignment is
    in a heredoc or here-string fed to a shell, built by `printf -v`, or its name comes from a
    variable. Pinned so closing a gap shows up here, and in the docs, as a deliberate change."""
    assert not crew_mass.sets_git_location(command, "bash"), command


@pytest.mark.parametrize("target", ["..", "../x", "./..", "a/..", "a/../b", "./lnk/..", "a/b/../c",
                                    "../..", "x/../.."])
def test_a_dotdot_component_in_a_cd_target_is_never_followed(repo, tmp_path, target):
    """B1: bash may walk a symlink for `..` (a logical cd, or `set -P` from BASH_ENV) and this
    process would cut the text, so any `..` component is could-not-tell in both shells."""
    root = repo / "sub"
    for name in ("a/b", "x", "lnk"):
        (root / name).mkdir(parents=True, exist_ok=True)
    assert crew_mass.leading_cd(f"cd {target} && git status", str(root), "bash") is None, target
    for sep in ("; ", " && "):
        assert crew_mass.leading_cd(f"cd {target}{sep}git status", str(root), "powershell") \
            is None, target


def test_a_dotdot_cd_is_asked_where_the_text_says_the_repo_is_clean(repo):
    """B1, reviewer scenario A: the hook's cwd is `repo/sub` (clean); bash may really be in a
    symlink that `..` leaves for a 32-file worktree. A followed `cd ..` counts the clean parent
    (0) and passes; refused, it is asked, exactly as on main."""
    (repo / "sub").mkdir()
    result = _stopped_in(repo, repo / "sub", "cd .. && git commit -m x", crew_mass.MASS_DELETE)
    assert "moves the shell" in result["reason"], result
    result = _stopped_in(repo, repo, "cd ./sub/.. && git commit -m x", crew_mass.MASS_DELETE)
    assert "moves the shell" in result["reason"], result
    result = _ps_in(repo, repo / "sub", "cd ..; git commit -m x")
    assert _mass_rows(result) and result["decision"] in ("ask", "deny"), result


def test_a_name_that_only_contains_dots_is_still_followed(repo):
    """The refusal is the whole component `..`, not any two dots: `..x` and `a..b` are names."""
    for name in ("..x", "a..b"):
        (repo / name).mkdir()
        assert crew_mass.leading_cd(f"cd ./{name} && git status", str(repo), "bash"), name
        assert crew_mass.leading_cd(f"cd {_fwd(repo)}/{name} && git status", str(repo),
                                    "powershell"), name


def test_a_powershell_drive_prefix_is_followed_only_where_drives_exist(repo, tmp_path,
                                                                       monkeypatch):
    """F1: on Linux a directory can be named `c:`; pwsh Set-Location 'c:/x' fails ("Cannot find
    drive"). A drive prefix is a target only when os.name == "nt"; where there are no drives a
    target must start with `/`."""
    if os.name == "nt":
        target = _fwd(_worktree(repo, tmp_path))
    else:
        (repo / "c:" / "x").mkdir(parents=True)
        target = "c:/x"
    cwd = str(repo)
    monkeypatch.setattr(crew_mass, "_WINDOWS", False)
    assert crew_mass.leading_cd(f"cd {target} && git status", cwd, "powershell") is None
    assert crew_mass.leading_cd(f"Set-Location {target} && git status", cwd, "powershell") is None
    monkeypatch.setattr(crew_mass, "_WINDOWS", os.name == "nt")
    if os.name == "nt":
        assert crew_mass.leading_cd(f"cd {target} && git status", cwd, "powershell")
    else:
        assert crew_mass.leading_cd(f"cd {_fwd(repo)} && git status", cwd, "powershell")


def test_an_absolute_dash_C_after_a_cd_is_counted_there_as_on_main(repo, tmp_path):
    """`cd X && git -C /abs commit` is not a followed cd (-C is refused after one), but the
    absolute -C path is still counted: allowed when /abs is clean, stopped when it is not,
    the same on origin/main (round-5 report said "could not tell"; that was wrong)."""
    wt = _big_wt(repo, tmp_path, count=32)
    other = tmp_path / "other"
    other.mkdir()
    _clean_in(repo, wt, f"cd {_fwd(other)} && git -C {_fwd(repo)} commit -m x")
    _stopped_in(repo, repo, f"cd {_fwd(other)} && git -C {_fwd(wt)} commit -m x",
                crew_mass.MASS_CREATE)


# --- round 13 (crew-lin) ------------------------------------------------------------
# BLOCK-A: a repeated -C was joined as TEXT and then tilde-expanded, so `-C aa -C ~/r` was read
# as the literal `aa/~/r` (clean) while bash expands `~/r` to $HOME/r (dirty): main asked, the
# PR allowed, and real bash committed 75 files there. Each -C is now resolved against the
# directory the one before it reached, and a chain holding a `~` is "could not tell" (its
# quoting is gone by the time the words reach the guard).

def _dirty(path, count=35, armed=False):
    """A repo at `path` whose `a/` holds `count` committed files, every one modified and
    UNSTAGED, plus an unmodified `one.txt` and `README`."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        git(path, "config", key, value)
    _fill(path / "a", count, text="one")
    (path / "one.txt").write_text("one", encoding="utf-8")
    (path / "README").write_text("x", encoding="utf-8")
    if armed:
        (path / ".crew").mkdir()
        (path / ".crew" / "config.json").write_text(
            json.dumps({"guards": {"mass": {"enabled": True}}}), encoding="utf-8")
        (path / ".gitignore").write_text(".crew/\nlist*\nsmall*\n-\n", encoding="utf-8")
    _commit_all(path, "root")
    _fill(path / "a", count, text="two")
    (path / "one.txt").write_text("two", encoding="utf-8")
    return path


def _raw(repo, cwd, command, tool="Bash"):
    """`evaluate` with the command text exactly as given (no backslash rewrite)."""
    return cloud_guard.evaluate(str(repo), tool, command, {"cwd": str(cwd)}, "block",
                                crew_mass.settings(str(repo)))


@pytest.mark.parametrize("command", [
    "git -C aa -C ~/rbig commit -a -m x", "git -C aa -C ~/rbig reset --hard",
    "git -C aa -C ~ -C rbig commit -a -m x", "git -C '~' -C rb commit -a -m x",
    "git -C \\~ -C rb reset --hard", "git -C ~ -C rb commit -a -m x",
])
def test_a_repeated_C_holding_a_tilde_is_could_not_tell(repo, tmp_path, command):
    home = tmp_path / "home"
    _dirty(home / "rbig", 75)
    _dirty(home / "rb", 0)  # $HOME/rb: clean
    _dirty(repo / "aa" / "~" / "rbig", 0)  # the literal aa/~/rbig: clean
    _dirty(repo / "~" / "rb", 75)  # the literal ./~/rb: dirty
    git(repo / "aa" / "~" / "rbig", "commit", "-qam", "clean")
    git(home / "rb", "commit", "-qam", "clean")
    result = _raw(repo, repo, command)
    assert _mass_rows(result) and result["decision"] in ("ask", "deny"), (command, result)


def test_a_single_tilde_C_and_a_tilde_free_chain_are_still_counted(repo, tmp_path):
    home = tmp_path / "home"
    for clean in (home / "rb", repo / "aa" / "rb"):
        _dirty(clean, 0)
        git(clean, "commit", "-qam", "clean")
    _clean_in(repo, repo, "git -C ~/rb commit -a -m x")  # one -C: expanded, as on main
    _clean_in(repo, repo, f"git -C {_fwd(home)} -C rb commit -a -m x")
    _clean_in(repo, repo, "git -C aa -C rb reset --hard")
    _dirty(repo / "aa" / "big", 35)
    _stopped_in(repo, repo, "git -C aa -C big reset --hard", crew_mass.MASS_CHANGE)


def test_a_chain_after_an_unfollowed_cd_is_walked_from_its_absolute_head(repo, tmp_path):
    """`cd X; git -C /abs -C rel`: the cd is not followed, but every value after an absolute
    first one is known, so the chain is counted (clean: allowed; dirty: stopped)."""
    base = tmp_path / "b"
    git(_dirty(base / "small", 0), "commit", "-qam", "clean")
    _dirty(base / "big", 35)
    _clean_in(repo, repo, f"cd {_fwd(tmp_path)}; git -C {_fwd(base)} -C small commit -a -m x")
    _stopped_in(repo, repo, f"cd {_fwd(tmp_path)}; git -C {_fwd(base)} -C big commit -a -m x",
                crew_mass.MASS_CHANGE)
    _stopped_in(repo, repo, f"cd {_fwd(tmp_path)}; git -C b -C small commit -a -m x",
                crew_mass.MASS_DELETE)  # a relative head after a cd: could not tell


@pytest.mark.skipif(os.name != "nt", reason="a drive and Git Bash's /c/ form exist on Windows")
def test_a_chain_is_not_joined_across_drives_on_windows(tmp_path):
    """`os.path.join("C:/x", "/c/y")` keeps the drive (`C:/c/y`); git (after Git Bash maps
    `/c/y` to `C:/y`) goes to C:/y. Each value is resolved on its own."""
    folder = _fwd(tmp_path)
    posix = "/" + folder[0].lower() + folder[2:]
    path, ok = crew_mass._resolve_override(  # pylint: disable=protected-access
        ("C:/elsewhere", posix), str(tmp_path), False)
    assert ok and os.path.normcase(os.path.normpath(path)) == os.path.normcase(
        os.path.normpath(str(tmp_path)))


# BLOCK-B: `git commit <pathspec>` commits those paths' WORKING-TREE state whatever is staged,
# and `--pathspec-from-file <f>` was read as the pathspec `f`. Main counted the index (0) and
# allowed; real bash committed / deleted / rewrote 45 files. Both forms are now counted, plain
# and after a followed cd, BESIDE main's own count (never instead of it).

_PATHSPEC_BLOCKS = [
    "git commit -m x .", "git commit -m x a", "git commit -m x -- a", "git commit -mx a",
    "git commit -m x -o a", "git commit -m x --only a", "git commit -m x a/",
    "git commit -m x ':(glob)a/*'", "git commit -F README a",
    "git commit --author 'a <b@c.d>' -m x a", "git commit -m x --pathspec-from-file list.txt",
    "git commit -m x --pathspec-from-file=list.txt",
    "git commit -m x --pathspec-from-file=list0.txt --pathspec-file-nul",
    "git rm -f --pathspec-from-file list.txt", "git rm -f --pathspec-from-file=list.txt",
    "git restore --pathspec-from-file list.txt", "git restore --pathspec-from-file=list.txt",
    "git checkout --pathspec-from-file=list.txt", "git checkout HEAD --pathspec-from-file=list.txt",
    "git checkout --pathspec-from-file list.txt",
    # could not tell: standard input, a missing file, a C-quoted line, a NUL without the flag,
    # a file that is not UTF-8
    "git commit -m x --pathspec-from-file=-", "git rm -f --pathspec-from-file -",
    "git commit -m x --pathspec-from-file=missing.txt",
    "git commit -m x --pathspec-from-file=listq.txt",
    "git commit -m x --pathspec-from-file=list0.txt",
    "git restore --pathspec-from-file=listl.txt",
]


def _pathspec_lists(repo, count=35):
    names = [f"a/f{index}.txt" for index in range(count)]
    (repo / "list.txt").write_text("\n".join(names) + "\n", encoding="utf-8", newline="\n")
    (repo / "list0.txt").write_text("\0".join(names) + "\0", encoding="utf-8", newline="\n")
    (repo / "listq.txt").write_text("\n".join(f'"{n}"' for n in names) + "\n",
                                    encoding="utf-8", newline="\n")
    (repo / "listl.txt").write_bytes(b"a/f\xe9.txt\n")
    (repo / "small.txt").write_text("one.txt\nREADME\n", encoding="utf-8", newline="\n")
    (repo / "small0.txt").write_text("one.txt\0README\0", encoding="utf-8", newline="\n")


@pytest.mark.parametrize("command", _PATHSPEC_BLOCKS)
def test_a_pathspec_or_a_pathspec_file_is_counted(tmp_path, machine, command):
    assert machine
    dirty = _dirty(tmp_path / "dirty", armed=True)
    _pathspec_lists(dirty)
    elsewhere = _dirty(tmp_path / "elsewhere", 0, armed=True)
    _stops(dirty, command)
    result = _in(dirty, elsewhere, f"cd {_fwd(dirty)} && {command}")
    assert _mass_rows(result) and result["decision"] in ("ask", "deny"), (command, result)


@pytest.mark.parametrize("command", [
    "git commit -m x one.txt", "git commit -m a one.txt", "git commit -m x README one.txt",
    "git commit -m x --pathspec-from-file small.txt",
    "git commit -m x --pathspec-from-file=small0.txt --pathspec-file-nul",
    "git rm -f --pathspec-from-file small.txt", "git restore --pathspec-from-file small.txt",
    "git checkout --pathspec-from-file=small.txt",
])
def test_a_small_pathspec_beside_a_large_unstaged_change_passes(tmp_path, machine, command):
    """Must-allow beside each must-block: the 35 unstaged files under a/ are not in the
    pathspec (and `-m a` is the message, not a pathspec)."""
    assert machine
    dirty = _dirty(tmp_path / "dirty", armed=True)
    _pathspec_lists(dirty)
    elsewhere = _dirty(tmp_path / "elsewhere", 0, armed=True)
    _passes(dirty, command)
    if "=" not in command:  # a glued value is no plain flag: that line is not followed
        _clean_in(dirty, elsewhere, f"cd {_fwd(dirty)} && {command}")


def test_a_file_named_dash_is_not_the_standard_input(tmp_path, machine):
    assert machine
    dirty = _dirty(tmp_path / "dirty", armed=True)
    (dirty / "-").write_text("one.txt\n", encoding="utf-8", newline="\n")
    _stops(dirty, "git commit -m x --pathspec-from-file -", crew_mass.MASS_CHANGE)
    (dirty / "-").unlink()
    _stops(dirty, "git commit -m x --pathspec-from-file -", crew_mass.MASS_CHANGE)


def test_commit_include_counts_the_index_and_the_paths_together(tmp_path, machine):
    """`-i` commits what is staged AND the paths: 20 staged + 20 listed is 40 (> 30), though
    neither alone reaches the limit."""
    assert machine
    dirty = _dirty(tmp_path / "dirty", count=20, armed=True)
    _fill(dirty / "b", 20, text="one")
    _commit_all(dirty, "b")
    _fill(dirty / "b", 20, text="two")
    _fill(dirty / "a", 20, text="three")
    git(dirty, "add", "a")
    _passes(dirty, "git commit -m x")
    _stops(dirty, "git commit -m x -i b", crew_mass.MASS_CHANGE)


# NIT: a bare --attr-source / --super-prefix took the subcommand as its value, so
# `git --super-prefix reset --hard` was no command at all. Both readings are now judged.

@pytest.mark.parametrize("opt", ["--super-prefix", "--attr-source"])
def test_a_bare_value_option_cannot_swallow_the_subcommand(tmp_path, machine, opt):
    assert machine
    dirty = _dirty(tmp_path / "dirty", armed=True)
    result = _stops(dirty, f"git {opt} reset --hard")
    assert "may or may not take the next word" in result["reason"], result["reason"]
    force = cloud_guard._git_force_push  # pylint: disable=protected-access
    assert force([opt, "push", "--force"]) and force([opt, "HEAD", "push", "-f"])
    assert not force([opt, "HEAD", "push"])


# FIX-1: PowerShell's legacy native argument passing (pwsh 7.0-7.2, Windows PowerShell 5.1,
# `$PSNativeCommandArgumentPassing = 'Legacy'`) strips or re-splits a `"` inside a quoted
# argument and drops an empty one, so neither is a plain PowerShell argument. Measured on
# Windows pwsh 7.6.9: Legacy passes `'." -dx ".'` as `. -dx .` and drops `''`.

def test_a_powershell_quoted_argument_holding_a_quote_or_nothing_is_not_followed(repo, tmp_path):
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    target = _fwd(clean)
    for tail in ("git clean -f '.\" -dx \".'", "git commit -m 'a\"b'", "git commit -m ''",
                 'git commit -m ""', "git commit -m x ''"):
        command = f"Set-Location {target} && {tail}"
        assert crew_mass.leading_cd(command, str(wt), "powershell") is None, command
    # bash passes both exactly as written
    assert crew_mass.leading_cd(f"cd {target} && git commit -m 'a\" b'", str(wt), "bash")
    assert crew_mass.leading_cd(f"cd {target} && git commit -m ''", str(wt), "bash")
    assert crew_mass.leading_cd(f"Set-Location {target} && git commit -m 'a b'", str(wt),
                                "powershell")


def test_the_powershell_cd_words_are_matched_in_ascii_only(repo, tmp_path):
    """Python's re.IGNORECASE folds `\u017f` (U+017F) to `s`: `\u017fl` is no PowerShell
    alias, so it is not a cd here either."""
    wt, clean = _cwd_big_cd_clean(repo, tmp_path)
    target = _fwd(clean)
    assert crew_mass.leading_cd(f"\u017fl {target} && git commit -m x", str(wt),
                                "powershell") is None
    assert crew_mass.leading_cd(f"SL {target} && git commit -m x", str(wt), "powershell")


# Owner pick (round 13, via crew-lin): pull, fetch and a fast-forward merge carry no mass rule
# on main or here. Pinned, so a rule added for them later is a deliberate change. The repo has
# 35 STAGED changes, so a rule that counted the index (as commit does) would stop them.

@pytest.mark.parametrize("tail", ["git pull --ff-only", "git pull", "git fetch",
                                  "git merge --ff-only origin/main"])
def test_pull_fetch_and_a_fast_forward_merge_are_not_judged(tmp_path, machine, tail):
    assert machine
    dirty = _dirty(tmp_path / "dirty", armed=True)
    git(dirty, "add", "a")
    elsewhere = _dirty(tmp_path / "elsewhere", 0, armed=True)
    assert crew_mass.classify("git", tail.split()[1:]) == []
    _passes(dirty, tail)
    _passes(dirty, tail, tool="PowerShell")
    assert crew_mass.leading_cd(f"cd {_fwd(dirty)} && {tail}", str(elsewhere), "bash")
    _clean_in(dirty, elsewhere, f"cd {_fwd(dirty)} && {tail}")
    command = f"Set-Location {_fwd(dirty)} && {tail}"
    assert crew_mass.leading_cd(command, str(elsewhere), "powershell")
    result = _ps_in(dirty, elsewhere, command)
    assert not _mass_rows(result) and result["decision"] == "allow", (command, result)
