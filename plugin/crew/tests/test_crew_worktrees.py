"""crew 1.3.19: one standard worktree root outside the repo (`worktrees.root`).

    python3 -m pytest plugin/crew/tests/test_crew_worktrees.py -q

`crew_worktrees.py` resolves the root, lists and classifies worktrees
(read-only), removes ONE worktree on the owner's `--yes`, and is the entry point
of the opt-in `WorktreeCreate` / `WorktreeRemove` hook. Every case builds a
throwaway origin, clone and linked worktrees under tmp_path, and points HOME at
a scratch directory: nothing reads or writes the real `~/.claude`, the real
config or a real worktree.

The MUST-REFUSE cases are the ones `worktrees_mutations.py` reintroduces a bug
against: a refused setting falling back to the default, a root inside the repo,
a removal of work that is not safe to lose, `--force`, and a hook that
overwrites or deletes what it did not create.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import crew_wave
import crew_worktrees

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts", "crew_worktrees.py")  # pylint: disable=protected-access


def git(cwd, *args, check=True):
    done = subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@example.com", "-c", "user.name=t",
                           "-c", "core.autocrlf=false"] + list(args), capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL)
    if check and done.returncode != 0:
        raise AssertionError(f"git {args}: {done.stderr}")
    return done.stdout.strip()


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def repo(tmp_path):
    """A clone `myrepo` of a bare origin whose main branch is pushed."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "a.txt").write_text("a\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "seed")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True,
                   stdin=subprocess.DEVNULL)
    git(seed, "push", "-q", str(origin), "main")
    clone = tmp_path / "work" / "myrepo"
    clone.parent.mkdir()
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, stdin=subprocess.DEVNULL)
    return clone


def _cfg(repo, **worktrees):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "config.json").write_text(json.dumps({"worktrees": worktrees}), encoding="utf-8")


def _std(repo):
    return crew_worktrees.resolve(str(repo))["dir"]


def _lane(repo, name, commit=False, where=None):
    """A linked worktree on origin/main (no unique commits) or with one commit."""
    dest = where or os.path.join(_std(repo), name)
    git(repo, "worktree", "add", "-q", "-b", name, dest, "origin/main")
    if commit:
        with open(os.path.join(dest, "n.txt"), "w", encoding="utf-8") as handle:
            handle.write(name)
        git(dest, "add", "-A")
        git(dest, "commit", "-qm", name)
    return dest


def _row(repo, path, days=0):
    rows, _ = crew_worktrees.survey(str(repo), days=days)
    return next(r for r in rows if os.path.normcase(os.path.realpath(r["path"])) ==
                os.path.normcase(os.path.realpath(path)))


# --- the resolver -----------------------------------------------------------------------

def test_default_root_is_a_per_user_directory_outside_the_repo(repo, _home):
    got = crew_worktrees.resolve(str(repo))

    assert got["problem"] == "" and got["source"] == "default"
    assert os.path.dirname(got["dir"]) == str(_home / ".claude" / "crew" / "worktrees")
    assert os.path.basename(got["dir"]).startswith("myrepo-")
    assert not crew_worktrees._inside(got["dir"], str(repo))  # pylint: disable=protected-access


def test_a_repo_setting_names_the_base_and_tilde_is_expanded(repo, tmp_path, _home):
    _cfg(repo, root=str(tmp_path / "elsewhere"))
    assert os.path.dirname(_std(repo)) == str(tmp_path / "elsewhere")

    _cfg(repo, root="~/wts")
    assert os.path.dirname(_std(repo)) == str(_home / "wts")


def test_the_machine_layer_supplies_the_base_and_the_repo_layer_wins(repo, tmp_path, monkeypatch):
    glob = tmp_path / "global.json"
    glob.write_text(json.dumps({"worktrees": {"root": str(tmp_path / "from-machine")}}), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(glob))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(glob))
    assert os.path.dirname(_std(repo)) == str(tmp_path / "from-machine")

    _cfg(repo, root=str(tmp_path / "from-repo"))
    assert os.path.dirname(_std(repo)) == str(tmp_path / "from-repo")


@pytest.mark.parametrize("bad", ["relative/path", "./x", 5, True, "   ", ["a"]])
def test_an_unusable_setting_is_refused_and_never_replaced_by_the_default(repo, bad):
    _cfg(repo, root=bad)

    got = crew_worktrees.resolve(str(repo))

    assert got["problem"] and got["dir"] is None
    with pytest.raises(crew_worktrees.WorktreeRootError):
        crew_worktrees.repo_dir(str(repo))


@pytest.mark.parametrize("inside", ["", ".claude/worktrees", "sub/dir"])
def test_a_root_inside_the_repo_is_refused(repo, inside):
    _cfg(repo, root=str(repo / inside) if inside else str(repo))

    got = crew_worktrees.resolve(str(repo))

    assert got["dir"] is None and "inside the repo" in got["problem"]


def test_a_linked_worktree_resolves_to_the_main_checkouts_directory(repo):
    lane = _lane(repo, "lane")

    assert crew_worktrees.resolve(lane)["dir"] == _std(repo)


def test_two_repos_with_one_basename_get_different_directories(tmp_path, repo):
    other = tmp_path / "elsewhere" / "myrepo"
    other.mkdir(parents=True)
    git(other, "init", "-q", "-b", "main")

    assert crew_worktrees.resolve(str(other))["dir"] != _std(repo)


def test_path_flattens_a_branch_into_one_level_under_the_repo_dir(repo):
    base = _std(repo)

    assert crew_worktrees.worktree_path(str(repo), "feat/x") == os.path.join(base, "feat-x")
    assert os.path.dirname(crew_worktrees.worktree_path(str(repo), "a/../../b")) == base
    assert os.path.basename(crew_worktrees.worktree_path(str(repo), "..")) == "detached"


def test_the_state_cli_answers_with_the_standard_root(repo, capsys):
    assert crew_state.main(["--root", str(repo), "--worktree-path", "fix"]) == 0

    assert capsys.readouterr().out.strip() == os.path.join(_std(repo), "fix")


def test_the_state_cli_refuses_a_bad_setting_with_exit_2(repo, capsys):
    _cfg(repo, root="relative")

    assert crew_state.main(["--root", str(repo), "--worktree-path", "fix"]) == 2
    out = capsys.readouterr()
    assert out.out == "" and "refused" in out.err


# --- the survey (read-only) ---------------------------------------------------------------

def test_a_clean_merged_pushed_old_worktree_is_removable(repo):
    path = _lane(repo, "done")

    row = _row(repo, path)

    assert (row["removable"], row["where"], row["why"]) == (True, "standard", [])


@pytest.mark.parametrize("make, reason", [
    (lambda p: open(os.path.join(p, "a.txt"), "w", encoding="utf-8").write("changed\n"), "uncommitted"),
    (lambda p: open(os.path.join(p, "new.txt"), "w", encoding="utf-8").write("x\n"), "uncommitted"),
])
def test_uncommitted_or_untracked_work_is_never_removable(repo, make, reason):
    path = _lane(repo, "wip")
    make(path)

    row = _row(repo, path)

    assert row["removable"] is False and any(reason in why for why in row["why"])


def test_commits_no_remote_has_are_never_removable(repo):
    path = _lane(repo, "ahead", commit=True)

    row = _row(repo, path)

    assert row["removable"] is False
    assert any("no remote has" in why for why in row["why"]) and row["unpushed"] == 1


def test_a_young_worktree_is_kept_until_it_is_old_enough(repo):
    path = _lane(repo, "fresh")

    assert _row(repo, path, days=0)["removable"] is True
    assert _row(repo, path, days=14)["removable"] is False


def test_a_locked_worktree_is_kept(repo):
    path = _lane(repo, "pinned")
    git(repo, "worktree", "lock", path)

    assert _row(repo, path)["removable"] is False


def test_a_probe_that_fails_is_could_not_tell_and_not_removable(repo, monkeypatch):
    path = _lane(repo, "odd")
    real = crew_worktrees._git  # pylint: disable=protected-access

    def failing(cwd, *args, **kw):
        if args[:1] == ("status",):
            return None, "", "boom"
        return real(cwd, *args, **kw)
    monkeypatch.setattr(crew_worktrees, "_git", failing)

    row = _row(repo, path)

    assert row["dirty"] == crew_worktrees.UNKNOWN and row["removable"] is False


def test_a_missing_default_branch_is_could_not_tell_not_merged(repo, monkeypatch):
    path = _lane(repo, "x")
    monkeypatch.setattr(crew_worktrees, "_default_ref", lambda main: None)

    row = _row(repo, path)

    assert row["merged"] == crew_worktrees.UNKNOWN and row["removable"] is False


def test_the_main_checkout_is_never_removable(repo):
    rows, _ = crew_worktrees.survey(str(repo), days=0)

    assert rows[0]["main"] is True and rows[0]["removable"] is False


def test_a_worktree_inside_the_repo_is_classified_in_repo(repo):
    inside = repo / ".claude" / "worktrees" / "agent-1"
    git(repo, "worktree", "add", "-q", "-b", "agent-1", str(inside), "origin/main")

    assert _row(repo, inside)["where"] == "in-repo"


def test_list_prints_every_worktree_and_changes_nothing(repo):
    path = _lane(repo, "done")
    before = git(repo, "worktree", "list", "--porcelain")

    done = subprocess.run([sys.executable, _SCRIPT, "list", "--root", str(repo), "--days", "0"],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)

    assert done.returncode == 0, done.stderr
    assert "REMOVABLE" in done.stdout and "Nothing was changed" in done.stdout
    assert os.path.isdir(path) and git(repo, "worktree", "list", "--porcelain") == before


# --- remove ---------------------------------------------------------------------------------

def test_remove_needs_the_owners_yes(repo):
    path = _lane(repo, "done")

    ok, message = crew_worktrees.remove(str(repo), path, yes=False, days=0)

    assert not ok and "--yes" in message and os.path.isdir(path)


def test_remove_deletes_one_removable_worktree_and_its_merged_branch(repo):
    path = _lane(repo, "done")

    ok, message = crew_worktrees.remove(str(repo), path, yes=True, days=0)

    assert ok, message
    assert not os.path.exists(path)
    assert "done" not in git(repo, "branch", "--list", "done")


def test_remove_refuses_work_it_cannot_prove_safe_and_leaves_it_on_disk(repo):
    dirty = _lane(repo, "dirty")
    with open(os.path.join(dirty, "x.txt"), "w", encoding="utf-8") as handle:
        handle.write("x")
    ahead = _lane(repo, "ahead", commit=True)

    for path in (dirty, ahead):
        ok, message = crew_worktrees.remove(str(repo), path, yes=True, days=0)
        assert not ok and message.startswith("refused"), message
        assert os.path.isdir(path)


def test_remove_never_forces(repo, monkeypatch):
    path = _lane(repo, "done")
    seen = []
    real = crew_worktrees._git  # pylint: disable=protected-access

    def spy(cwd, *args, **kw):
        seen.append(args)
        return real(cwd, *args, **kw)
    monkeypatch.setattr(crew_worktrees, "_git", spy)

    crew_worktrees.remove(str(repo), path, yes=True, days=0)

    removals = [a for a in seen if a[:2] == ("worktree", "remove")]
    assert removals and all("--force" not in a and "-f" not in a for a in removals)


def test_remove_refuses_the_main_checkout_a_stranger_and_the_current_one(repo, tmp_path, monkeypatch):
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    for path in (str(repo), str(stranger)):
        ok, message = crew_worktrees.remove(str(repo), path, yes=True, days=0)
        assert not ok and message.startswith("refused"), message
    here = _lane(repo, "here")
    monkeypatch.chdir(here)

    ok, message = crew_worktrees.remove(str(repo), here, yes=True, days=0)

    assert not ok and "runs in" in message and os.path.isdir(here)


# --- the hook ----------------------------------------------------------------------------------

def test_hook_create_places_the_worktree_under_the_standard_root_on_a_worktree_branch(repo):
    ok, path = crew_worktrees.hook_create({"cwd": str(repo), "name": "bold-oak-a3f2"})

    assert ok, path
    assert path == os.path.join(_std(repo), "bold-oak-a3f2") and os.path.isdir(path)
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "worktree-bold-oak-a3f2"
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")
    assert not os.path.exists(repo / ".claude" / "worktrees")


def test_hook_create_from_inside_a_linked_worktree_uses_the_same_directory(repo):
    lane = _lane(repo, "lane")

    ok, path = crew_worktrees.hook_create({"cwd": lane, "name": "sub"})

    assert ok and os.path.dirname(path) == _std(repo)


def test_hook_create_reuses_its_own_worktree_and_refuses_a_stranger_directory(repo):
    first = crew_worktrees.hook_create({"cwd": str(repo), "name": "same"})
    again = crew_worktrees.hook_create({"cwd": str(repo), "name": "same"})
    os.makedirs(os.path.join(_std(repo), "squatter"))
    squatter = crew_worktrees.hook_create({"cwd": str(repo), "name": "squatter"})

    assert first == again and first[0] is True
    assert squatter[0] is False and "not a worktree" in squatter[1]


@pytest.mark.parametrize("name", ["", "../escape", "a/b", "a\\b", ".hidden", "x..y", "bad name", "end."])
def test_hook_create_refuses_a_name_that_is_not_a_plain_name(repo, name):
    ok, message = crew_worktrees.hook_create({"cwd": str(repo), "name": name})

    assert not ok and message.startswith("refused")
    assert not os.path.exists(os.path.join(os.path.dirname(_std(repo)), "escape"))


def test_hook_create_refuses_under_a_refused_root_and_creates_nothing(repo, tmp_path):
    _cfg(repo, root="relative")

    ok, message = crew_worktrees.hook_create({"cwd": str(repo), "name": "w"})

    assert not ok and message.startswith("refused")
    assert not os.path.exists(repo / ".claude" / "worktrees")
    assert git(repo, "worktree", "list").count("\n") == 0


def test_hook_create_honours_a_head_base_and_copies_worktreeinclude(repo):
    (repo / ".gitignore").write_text(".env\nsecret/\n", encoding="utf-8")
    (repo / ".worktreeinclude").write_text(".env\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=1\n", encoding="utf-8")
    (repo / "secret").mkdir()
    (repo / "secret" / "k").write_text("k", encoding="utf-8")
    (repo / "local.txt").write_text("not ignored", encoding="utf-8")
    git(repo, "add", ".gitignore", ".worktreeinclude")
    git(repo, "commit", "-qm", "ignore")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps({"worktree": {"baseRef": "head"}}),
                                                    encoding="utf-8")

    ok, path = crew_worktrees.hook_create({"cwd": str(repo), "name": "inc"})

    assert ok, path
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "HEAD")
    assert os.path.isfile(os.path.join(path, ".env"))
    assert not os.path.exists(os.path.join(path, "secret")) and not os.path.exists(os.path.join(path, "local.txt"))


def test_hook_remove_removes_a_clean_worktree_and_its_merged_branch(repo):
    _, path = crew_worktrees.hook_create({"cwd": str(repo), "name": "gone"})

    ok, message = crew_worktrees.hook_remove({"worktree_path": path})

    assert ok, message
    assert not os.path.exists(path)
    assert git(repo, "branch", "--list", "worktree-gone") == ""


def test_hook_remove_leaves_uncommitted_work_and_unmerged_commits_in_place(repo):
    _, dirty = crew_worktrees.hook_create({"cwd": str(repo), "name": "dirty"})
    with open(os.path.join(dirty, "wip.txt"), "w", encoding="utf-8") as handle:
        handle.write("wip")
    _, ahead = crew_worktrees.hook_create({"cwd": str(repo), "name": "ahead"})
    with open(os.path.join(ahead, "c.txt"), "w", encoding="utf-8") as handle:
        handle.write("c")
    git(ahead, "add", "-A")
    git(ahead, "commit", "-qm", "c")

    assert crew_worktrees.hook_remove({"worktree_path": dirty})[0] is False
    assert os.path.isdir(dirty)
    # a clean tree whose branch has an unmerged commit is removed, the branch is kept
    ok, _ = crew_worktrees.hook_remove({"worktree_path": ahead})
    assert ok and git(repo, "branch", "--list", "worktree-ahead") != ""


def test_hook_remove_refuses_the_main_checkout_and_a_path_that_is_not_a_worktree(repo, tmp_path):
    stranger = tmp_path / "stranger"
    stranger.mkdir()

    for path in (str(repo), str(stranger), "", str(tmp_path / "missing")):
        ok, message = crew_worktrees.hook_remove({"worktree_path": path})
        assert not ok and message.startswith("refused"), (path, message)
    assert os.path.isdir(repo / ".git") and stranger.is_dir()


def test_the_hook_cli_prints_only_the_path_on_stdout_and_exits_1_on_refusal(repo):
    run = lambda payload: subprocess.run(  # noqa: E731
        [sys.executable, _SCRIPT, "hook-create"], input=json.dumps(payload), capture_output=True,
        text=True, check=False, cwd=str(repo))

    good = run({"cwd": str(repo), "name": "cli"})
    bad = run({"cwd": str(repo), "name": "../x"})

    assert good.returncode == 0 and good.stdout.strip() == os.path.join(_std(repo), "cli")
    assert bad.returncode == 1 and bad.stdout == "" and "refused" in bad.stderr


def test_the_hook_cli_survives_garbage_on_stdin(repo):
    done = subprocess.run([sys.executable, _SCRIPT, "hook-create"], input="not json", capture_output=True,
                          text=True, check=False, cwd=str(repo))

    assert done.returncode == 1 and done.stdout == ""


# --- registration is the owner's ---------------------------------------------------------------

def test_the_snippet_names_both_events_and_this_script():
    block = json.loads(crew_worktrees.hook_snippet(python="py", script="/p/crew_worktrees.py"))["hooks"]

    assert set(block) == {"WorktreeCreate", "WorktreeRemove"}
    assert "hook-create" in block["WorktreeCreate"][0]["hooks"][0]["command"]
    assert "hook-remove" in block["WorktreeRemove"][0]["hooks"][0]["command"]


def test_hook_state_reads_the_user_settings_and_says_when_the_path_is_gone(_home, tmp_path):
    assert crew_worktrees.hook_state()[0] == "not registered"
    settings = _home / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(crew_worktrees.hook_snippet(python="py", script=_SCRIPT), encoding="utf-8")
    assert crew_worktrees.hook_state()[0] == "registered"
    settings.write_text(crew_worktrees.hook_snippet(python="py", script=str(tmp_path / "gone" / "crew_worktrees.py")),
                        encoding="utf-8")
    assert crew_worktrees.hook_state()[0] == "missing script"
    settings.write_text("{not json", encoding="utf-8")
    assert crew_worktrees.hook_state()[0] == crew_worktrees.UNKNOWN


def test_crew_registers_no_worktree_hook_of_its_own():
    with open(os.path.join(context._ROOT, "hooks", "hooks.json"), encoding="utf-8") as handle:  # pylint: disable=protected-access
        events = json.load(handle)["hooks"]

    assert "WorktreeCreate" not in events and "WorktreeRemove" not in events


# --- the wave lane admits the standard root ---------------------------------------------------

def test_lane_init_admits_a_worktree_under_the_standard_root_and_still_refuses_a_sibling(repo, tmp_path):
    inside = _lane(repo, "std-lane")
    sibling = _lane(repo, "sib", where=str(tmp_path / "sibling-wt"))

    assert ".claude/worktrees" not in (crew_wave._init_refusal(inside, str(repo), "s", "T-1") or "")  # pylint: disable=protected-access
    assert ".claude/worktrees" in crew_wave._init_refusal(sibling, str(repo), "s", "T-1")  # pylint: disable=protected-access
