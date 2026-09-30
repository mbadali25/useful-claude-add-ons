"""`crew_train.py`, the merge train (L-0520): gate+land serialised per
overlapping Touch set, lanes still implementing in parallel.

Every repository here is a throwaway under pytest's tmp_path, with linked
worktrees (`git worktree add`) where a test needs two lanes, and an isolated
global git config: nothing reads or writes the real repository's
`.git/crew/`, and `test_catch_up_never_writes_global_config` asserts the
global file byte-identical afterwards.
"""
import ast
import json
import os
import pathlib
import shutil
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import crew_train
import review_gate
import review_ledger
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    glob = home / ".gitconfig"
    glob.write_text("[user]\n\tname = t\n\temail = t@example.com\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(glob))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return glob


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def _spec(top, ticket, touch=None, body=None):
    folder = top / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = "## Touch\n\n" + "".join(f"- `{p}`\n" for p in touch) + "\n"
    (folder / "spec.md").write_text(f"# {ticket}\n\n## Intent\n\nx\n\n{body}", encoding="utf-8")
    return folder / "spec.md"


def _worktree(repo, name, branch, start="main"):
    path = repo.parent / name
    git(repo, "worktree", "add", "-q", "-b", branch, str(path), start)
    return path


def _commit(top, name, text, message="c"):
    path = top / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(top, "add", name)
    git(top, "commit", "-qm", message)
    return git(top, "rev-parse", "HEAD")


def _cli(capsys, root, *argv):
    code = crew_train.main(["--root", str(root)] + list(argv))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _events(repo):
    path = os.path.join(crew_train.train_dir(str(repo)), "events.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _arm(capsys, repo):
    code, out = _cli(capsys, repo, "arm")
    assert code == 0, out


# --- overlap -------------------------------------------------------------------------

@pytest.mark.parametrize("mine,theirs,overlaps", [
    (["x/a.py"], ["x/a.py"], True),
    (["x/a.py"], ["x"], True),
    (["x/**"], ["x/y/z.py"], True),
    (["**"], ["anything/at/all.md"], True),
    (["x/a.py"], ["x/b.py"], False),
    (["X/A.py"], ["x/a.py"], True),
    ([".crew/codemap/*.md"], [".crew/codemap/crew.md"], False),
    (["graphify-out/graph.json"], ["graphify-out/graph.json"], False),
    (["docs/diagrams/a.mmd"], ["docs/diagrams/a.mmd"], False),
    ([".claude/rules/crew.md"], [".claude/rules/crew.md"], False),
    (["a/*.py"], ["a/b/c.py"], True),
    (["a/b.py", "c/d.py"], ["e/f.py", "c/d.py"], True),
    (["a/b.py"], ["a/bb.py"], False),
])
def test_touch_overlap_table(mine, theirs, overlaps):
    assert bool(crew_train.touch_overlap(mine, theirs)) is overlaps
    assert bool(crew_train.touch_overlap(theirs, mine)) is overlaps  # pylint: disable=arguments-out-of-order


@pytest.mark.parametrize("source", ["no-spec", "no-touch", "no-bullet", "parse-problem",
                                    "unreadable"])
def test_undeclared_touch_overlaps_everything(repo, capsys, monkeypatch, source):
    if source == "no-touch":
        _spec(repo, "T-1", body="## Exclusions\n\nnone\n")
    elif source == "no-bullet":
        _spec(repo, "T-1", body="## Touch\n\nprose only, no bullet\n")
    elif source == "parse-problem":
        _spec(repo, "T-1", body="## Touch\n\n- two words here\n")
    elif source == "unreadable":
        _spec(repo, "T-1", ["a.txt"])
        real = crew_ticket.read_contract
        monkeypatch.setattr(crew_ticket, "read_contract",
                            lambda top, t: {**real(top, t), "spec.md": None})
    touch, why = crew_train.touch_of(str(repo), "T-1")
    assert touch is None and why.startswith("undeclared: "), why
    assert crew_train.touch_overlap(touch, ["unrelated/file.txt"])
    assert crew_train.touch_overlap(["unrelated/file.txt"], touch)
    _spec(repo, "T-2", ["unrelated/file.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-1")
    assert code == 1 and "waiting behind T-2" in out, out
    code, out = _cli(capsys, repo, "status")
    assert code == 0 and "undeclared: " in out, out


# --- the queue -----------------------------------------------------------------------

def test_second_overlapping_acquire_waits(repo, capsys):
    one, two = _worktree(repo, "wt1", "l1"), _worktree(repo, "wt2", "l2")
    _spec(one, "T-1", ["a.txt"])
    _spec(two, "T-2", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, one, "acquire", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, two, "acquire", "--ticket", "T-2")
    assert code == 1 and "waiting behind T-1" in out, out
    code, out = _cli(capsys, repo, "status", "--json")
    rows = {e["ticket"]: e["state"] for e in json.loads(out)["entries"]}
    assert rows == {"T-1": "holding", "T-2": "waiting"}
    assert _cli(capsys, one, "release", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, two, "acquire", "--ticket", "T-2")
    assert code == 0, out


def test_disjoint_touch_sets_hold_concurrently(repo, capsys):
    _spec(repo, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["b.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-2")
    assert code == 0, out


def test_different_bases_are_different_trains(repo, capsys):
    git(repo, "branch", "release")
    _spec(repo, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-1", "--base", "main")[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-2", "--base", "release")
    assert code == 0, out


def test_earlier_overlapping_waiter_goes_first(repo, capsys):
    _spec(repo, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["a.txt", "b.txt"])
    _spec(repo, "T-3", ["a.txt", "b.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-1")[0] == 0
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 1
    assert _cli(capsys, repo, "acquire", "--ticket", "T-3")[0] == 1
    assert _cli(capsys, repo, "release", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-3")
    assert code == 1 and "waiting behind T-2" in out, out
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 0
    assert _cli(capsys, repo, "acquire", "--ticket", "T-3")[0] == 1


def test_overlap_decision_logged_with_paths(repo, capsys):
    _spec(repo, "T-1", ["src/a.py"])
    _spec(repo, "T-2", ["src"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-2")
    assert code == 1 and "colliding: src x src/a.py" in out, out
    events = _events(repo)
    assert [e["kind"] for e in events] == ["acquire", "wait"]
    assert events[0]["ticket"] == "T-1"
    blocker = events[1]["blockers"][0]
    assert blocker["ticket"] == "T-1"
    assert blocker["paths"] == [["src", "src/a.py"]]


def test_arm_is_exclusive_and_disarm_refuses_with_entries(repo, capsys):
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)
    code, out = _cli(capsys, repo, "arm")
    assert code == 1 and "already armed" in out, out
    assert _cli(capsys, repo, "enqueue", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, repo, "disarm")
    assert code == 1 and "T-1" in out, out
    assert _cli(capsys, repo, "release", "--ticket", "T-1")[0] == 0
    assert _cli(capsys, repo, "disarm")[0] == 0
    code, out = _cli(capsys, repo, "status")
    assert code == 0 and "armed: no" in out, out


@pytest.mark.parametrize("verb", [["enqueue", "--ticket", "T-1"], ["acquire", "--ticket", "T-1"],
                                  ["release", "--ticket", "T-1"], ["disarm"],
                                  ["check-land", "--ticket", "T-1", "--no-fetch"]])
def test_not_armed_verbs_say_so(repo, capsys, verb):
    _spec(repo, "T-1", ["a.txt"])
    code, out = _cli(capsys, repo, *verb)
    assert code == 1 and "train not armed" in out, out
    code, out = _cli(capsys, repo, "status")
    assert code == 0 and "armed: no" in out, out


# --- fail closed ---------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["garbage", "schema", "directory", "permission"])
def test_unreadable_state_is_could_not_tell(repo, capsys, monkeypatch, kind):
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)
    path = os.path.join(crew_train.train_dir(str(repo)), "state.json")
    if kind == "garbage":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
    elif kind == "schema":
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schema": 99, "entries": [], "seq": 0}, fh)
    elif kind == "directory":
        os.remove(path)
        os.mkdir(path)
    else:
        def denied(_path):
            raise PermissionError(13, "Permission denied", _path)
        monkeypatch.setattr(crew_train, "_read_file", denied)
    assert crew_train.load(str(repo))[1] == "could not tell"
    for verb in (["enqueue", "--ticket", "T-1"], ["acquire", "--ticket", "T-1"],
                 ["release", "--ticket", "T-1"], ["status"], ["disarm"],
                 ["check-land", "--ticket", "T-1", "--no-fetch"]):
        code, out = _cli(capsys, repo, *verb)
        assert code == 3 and "could not tell" in out and "state.json" in out, (verb, out)


def test_lock_is_never_broken_by_age(repo, capsys, monkeypatch):
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)
    lock = os.path.join(crew_train.train_dir(str(repo)), "state.json.lock")
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write("99999999")
    old = time.time() - 86400
    os.utime(lock, (old, old))
    monkeypatch.setattr(crew_train, "LOCK_WAIT_SECONDS", 0.2)
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-1")
    assert code == 3 and lock in out, out
    assert os.path.exists(lock)


@pytest.mark.parametrize("evidence", ["worktree", "merged"])
def test_stale_holder_is_reported_never_released(repo, capsys, evidence):
    one = _worktree(repo, "wt1", "l1")
    _spec(one, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, one, "acquire", "--ticket", "T-1")[0] == 0
    if evidence == "worktree":
        shutil.rmtree(one)
        expect = "worktree missing"
    else:
        _commit(repo, "z.txt", "z\n")
        expect = "already in main"
    code, out = _cli(capsys, repo, "status")
    assert code == 0 and "stale?" in out and expect in out, out
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-2")
    assert code == 1 and "stale?" in out and expect in out, out
    code, out = _cli(capsys, repo, "status", "--json")
    rows = {e["ticket"]: e["state"] for e in json.loads(out)["entries"]}
    assert rows["T-1"] == "holding"
    code, out = _cli(capsys, repo, "release", "--ticket", "T-1", "--force")
    assert code == 2, out
    code, out = _cli(capsys, repo, "release", "--ticket", "T-1", "--force",
                     "--by", "owner", "--reason", "session died")
    assert code == 0, out
    assert _events(repo)[-1]["kind"] == "force-release"
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 0


def test_release_by_another_worktree_needs_force(repo, capsys):
    one = _worktree(repo, "wt1", "l1")
    _spec(one, "T-1", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, one, "acquire", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, repo, "release", "--ticket", "T-1")
    assert code == 1 and "--force" in out, out


def test_acquire_refuses_until_base_moves_in_touch_are_merged(repo, capsys):
    lane = _worktree(repo, "wt1", "l1")
    _spec(lane, "T-1", ["a.txt"])
    _spec(lane, "T-2", ["b.txt"])
    _arm(capsys, repo)
    _commit(repo, "a.txt", "main moved a\n")
    code, out = _cli(capsys, lane, "acquire", "--ticket", "T-1")
    assert code == 1 and "merge main first" in out and "a.txt" in out, out
    code, out = _cli(capsys, lane, "acquire", "--ticket", "T-2")
    assert code == 0, out
    git(lane, "merge", "--no-edit", "-q", "main")
    code, out = _cli(capsys, lane, "acquire", "--ticket", "T-1")
    assert code == 0, out


def test_release_broadcasts_to_overlapping_lanes_once(repo, capsys):
    lane = _worktree(repo, "wt1", "l1")
    _spec(lane, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["a.txt"])
    _spec(repo, "T-3", ["z.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, lane, "acquire", "--ticket", "T-1")[0] == 0
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 1
    assert _cli(capsys, repo, "acquire", "--ticket", "T-3")[0] == 0
    _commit(lane, "a.txt", "lane change\n")
    git(repo, "merge", "--no-ff", "--no-edit", "-q", "l1")
    merged = git(repo, "rev-parse", "HEAD")
    assert _cli(capsys, lane, "release", "--ticket", "T-1", "--merged", merged)[0] == 0
    code, out = _cli(capsys, repo, "acquire", "--ticket", "T-2")
    notice = f"T-1 merged {merged[:12]} touching a.txt - merge main now"
    assert code == 0 and out.count(notice) == 1, out
    assert "T-3:" not in out
    code, out = _cli(capsys, repo, "status")
    assert notice not in out, out
    code, out = _cli(capsys, repo, "release", "--ticket", "T-2", "--merged", "deadbeef")
    assert code == 0, out
    code, out = _cli(capsys, repo, "status")
    assert "T-3: T-2 merged deadbeef touching (paths unreadable)" in out, out


# --- catch-up ------------------------------------------------------------------------

def _conflicting_lane(repo, name="wt1", branch="l1"):
    _commit(repo, "f.txt", "one\ntwo\n")
    lane = _worktree(repo, name, branch)
    _commit(lane, "f.txt", "one\nLANE\n")
    _commit(repo, "f.txt", "one\nMAIN\n")
    return lane


def _merge_log(repo, ticket):
    rows, where, why = crew_train.read_merge_log(str(repo), ticket)
    assert where == "ok", why
    return rows


def test_catch_up_replays_rerere_resolution_into_merge_log(repo, capsys):
    lane = _conflicting_lane(repo)
    assert git(lane, "config", "--get", "rerere.enabled", check=False) == ""
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")
    assert code == 1 and "f.txt" in out, out
    assert _merge_log(repo, "T-1")[-1]["outcome"] == "conflicted"
    (lane / "f.txt").write_text("one\nRESOLVED\n", encoding="utf-8")
    git(lane, "add", "f.txt")
    git(lane, "commit", "-q", "--no-edit")
    git(lane, "reset", "-q", "--hard", "HEAD~1")
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")
    assert code == 1 and "rerere" in out, out
    row = _merge_log(repo, "T-1")[-1]
    assert row["outcome"] == "rerere-resolved" and row["rerere_replayed"] == ["f.txt"], row
    assert "f.txt" in git(lane, "diff", "--name-only", "--cached")
    assert os.path.exists(os.path.join(git(lane, "rev-parse", "--absolute-git-dir"),
                                       "MERGE_HEAD"))
    code, out = _cli(capsys, lane, "merge-log", "--ticket", "T-1")
    assert code == 0 and "rerere_replayed: f.txt" in out, out
    assert git(lane, "config", "--get", "rerere.enabled") == "true"
    assert git(lane, "config", "--get", "rerere.autoupdate") == "true"


@pytest.mark.parametrize("worktree_config", [False, True])
def test_catch_up_never_writes_global_config(repo, capsys, _isolated_git, worktree_config):
    before = _isolated_git.read_bytes()
    if worktree_config:
        git(repo, "config", "extensions.worktreeConfig", "true")
    lane = _worktree(repo, "wt1", "l1")
    _commit(repo, "other.txt", "x\n")
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")
    assert code == 0, out
    assert _isolated_git.read_bytes() == before
    common = git(lane, "rev-parse", "--git-common-dir")
    shared = (lane / common if not os.path.isabs(common) else pathlib.Path(common)) / "config"
    own = os.path.join(git(lane, "rev-parse", "--absolute-git-dir"), "config.worktree")
    if worktree_config:
        with open(own, encoding="utf-8") as fh:
            assert "rerere" in fh.read()
        assert "rerere" not in shared.read_text(encoding="utf-8")
    else:
        assert "rerere" in shared.read_text(encoding="utf-8")
        assert not os.path.exists(own)
        assert git(lane, "config", "--get", "extensions.worktreeConfig", check=False) == ""


def test_catch_up_merges_and_never_commits_a_conflict(repo, capsys):
    lane = _conflicting_lane(repo)
    (lane / "f.txt").write_text("dirty\n", encoding="utf-8")
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")
    assert code == 1 and "dirty" in out, out
    git(lane, "checkout", "--", "f.txt")
    head = git(lane, "rev-parse", "HEAD")
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")
    assert code == 1, out
    assert git(lane, "rev-parse", "HEAD") == head
    assert os.path.exists(os.path.join(git(lane, "rev-parse", "--absolute-git-dir"),
                                       "MERGE_HEAD"))
    git(lane, "merge", "--abort")
    clean = _worktree(repo, "wt2", "l2")
    _commit(clean, "mine.txt", "mine\n")
    _commit(repo, "theirs.txt", "theirs\n")
    code, out = _cli(capsys, clean, "catch-up", "--ticket", "T-2")
    assert code == 0, out
    parents = git(clean, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(parents) == 3
    assert "rebase" not in git(clean, "reflog")
    assert _merge_log(repo, "T-2")[-1]["outcome"] == "merged"
    code, out = _cli(capsys, clean, "catch-up", "--ticket", "T-2")
    assert code == 0 and _merge_log(repo, "T-2")[-1]["outcome"] == "up-to-date", out


def test_overlapping_lane_can_enqueue_and_catch_up_while_other_holds(repo, capsys):
    one, two = _worktree(repo, "wt1", "l1"), _worktree(repo, "wt2", "l2")
    _spec(one, "T-1", ["a.txt"])
    _spec(two, "T-2", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, one, "acquire", "--ticket", "T-1")[0] == 0
    assert _cli(capsys, two, "enqueue", "--ticket", "T-2")[0] == 0
    _commit(repo, "other.txt", "x\n")
    code, out = _cli(capsys, two, "catch-up", "--ticket", "T-2")
    assert code == 0, out


def test_catch_up_fetch_failure_is_could_not_tell(repo, capsys, tmp_path):
    git(repo, "remote", "add", "origin", str(tmp_path / "no-such-remote"))
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    lane = _worktree(repo, "wt1", "l1")
    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1", "--base", "origin/main")
    assert code == 3 and "could not tell" in out and "fetch" in out, out


# --- check-land ----------------------------------------------------------------------

def _holding_lane(repo, capsys, touch=("a.txt",)):
    lane = _worktree(repo, "wt1", "l1")
    _spec(lane, "T-1", list(touch))
    _commit(lane, "c.txt", "lane\n")
    _arm(capsys, repo)
    code, out = _cli(capsys, lane, "acquire", "--ticket", "T-1")
    assert code == 0, out
    return lane


def _passing_verdict(monkeypatch):
    monkeypatch.setattr(review_ledger, "check_receipt",
                        lambda root, ticket: (True, "receipt current: fixture"))
    monkeypatch.setattr(review_gate, "gate_state",
                        lambda root: (review_gate.VERIFIED, "fixture"))


def test_check_land_refuses_base_moved_in_touch(repo, capsys, monkeypatch):
    lane = _holding_lane(repo, capsys)
    _passing_verdict(monkeypatch)
    _commit(repo, "a.txt", "main moved a\n")
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 1 and "a.txt" in out and "catch-up" in out, out


def test_check_land_allows_base_moved_outside_touch(repo, capsys):
    lane = _holding_lane(repo, capsys)
    _commit(repo, "z.txt", "main moved z\n")
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert "base moved outside Touch only" in out, out
    assert code == 1 and "no accepted review receipt" in out, out


def test_check_land_requires_receipt_on_merged_head(repo, capsys, monkeypatch):
    lane = _holding_lane(repo, capsys)
    _commit(repo, "a.txt", "main moved a\n")
    assert _cli(capsys, lane, "catch-up", "--ticket", "T-1")[0] == 0
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 1 and "no accepted review receipt for T-1" in out, out
    monkeypatch.setattr(review_ledger, "check_receipt",
                        lambda root, ticket: (True, "receipt current: fixture"))
    monkeypatch.setattr(review_gate, "gate_state",
                        lambda root: (review_gate.UNVERIFIED, "fixture red"))
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 1 and "fixture red" in out, out
    _passing_verdict(monkeypatch)
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 0, out


def test_check_land_refuses_merge_tree_conflict(repo, capsys, monkeypatch):
    lane = _holding_lane(repo, capsys, touch=("f.txt",))
    _passing_verdict(monkeypatch)
    _commit(lane, "f.txt", "lane line\n")
    _commit(repo, "f.txt", "main line\n")
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 1 and "conflict" in out and "f.txt" in out, out


def test_check_land_requires_the_hold(repo, capsys, monkeypatch):
    _passing_verdict(monkeypatch)
    _spec(repo, "T-1", ["a.txt"])
    _spec(repo, "T-2", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "acquire", "--ticket", "T-2")[0] == 0
    assert _cli(capsys, repo, "acquire", "--ticket", "T-1")[0] == 1
    code, out = _cli(capsys, repo, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 1 and "does not hold" in out, out


def test_check_land_prints_match_head_commit(repo, capsys, monkeypatch):
    lane = _holding_lane(repo, capsys)
    _passing_verdict(monkeypatch)
    head = git(lane, "rev-parse", "HEAD")
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch", "--pr", "42")
    assert code == 0, out
    assert f"LAND_OK head={head}" in out
    assert f"gh pr merge 42 --merge --match-head-commit {head}" in out
    assert _events(repo)[-1]["kind"] == "check-land"


def test_check_land_on_old_git_is_could_not_tell(repo, capsys, monkeypatch):
    lane = _holding_lane(repo, capsys)
    real = crew_train._git  # pylint: disable=protected-access

    def old_git(root, *args, **kwargs):
        if args and args[0] == "merge-tree":
            return 129, "", "error: unknown option `write-tree'"
        return real(root, *args, **kwargs)
    monkeypatch.setattr(crew_train, "_git", old_git)
    code, out = _cli(capsys, lane, "check-land", "--ticket", "T-1", "--no-fetch")
    assert code == 3 and "could not tell" in out and "merge-tree" in out, out


# --- hardening: GEN-01/02/04/07 ------------------------------------------------------

def test_train_dir_under_a_file_is_could_not_tell(repo, capsys):
    crew = crew_ticket.state_dir(str(repo))
    shutil.rmtree(crew, ignore_errors=True)
    with open(crew, "w", encoding="utf-8") as fh:
        fh.write("not a directory")
    _spec(repo, "T-1", ["a.txt"])

    assert crew_train.load(str(repo))[1] == "could not tell"
    for verb in (["status"], ["acquire", "--ticket", "T-1"]):
        code, out = _cli(capsys, repo, *verb)
        assert code == 3 and "could not tell" in out, (verb, out)


def test_windows_style_not_found_under_a_file_is_could_not_tell(repo, monkeypatch):
    """Windows answers a lookup under a regular file with FileNotFoundError
    (crew_standards' T-0085 land fix); only a directory ancestor proves absent."""
    crew = crew_ticket.state_dir(str(repo))
    shutil.rmtree(crew, ignore_errors=True)
    with open(crew, "w", encoding="utf-8") as fh:
        fh.write("not a directory")
    real = os.lstat

    def windows_lstat(path, *args, **kwargs):
        try:
            return real(path, *args, **kwargs)
        except NotADirectoryError as exc:
            raise FileNotFoundError(2, "not found", path) from exc
    monkeypatch.setattr(os, "lstat", windows_lstat)

    state, where, why = crew_train.load(str(repo))

    assert (state, where) == (None, "could not tell") and "not a directory" in why, why


@pytest.mark.parametrize("entry", [{"ticket": 5}, "T-1", {"ticket": "T-1", "base": "main",
                                                           "state": "parked", "order": 1}])
def test_malformed_entry_is_could_not_tell(repo, capsys, entry):
    _arm(capsys, repo)
    path = os.path.join(crew_train.train_dir(str(repo)), "state.json")
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    state["entries"] = [entry]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)

    code, out = _cli(capsys, repo, "status")

    assert code == 3 and "could not tell" in out and "entries" in out, out


@pytest.mark.parametrize("argv", [["acquire", "--ticket", "T-1", "--base=-x"],
                                  ["acquire", "--ticket", "T-1", "--lane", "a\nb"],
                                  ["release", "--ticket", "T-1", "--merged=--upload-pack=x"],
                                  ["check-land", "--ticket", "T-1", "--pr", "42; rm -rf /"],
                                  ["catch-up", "--ticket", "T-1", "--base", "main main"]])
def test_bad_cli_values_are_usage_errors(repo, capsys, argv):
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)

    code, out = _cli(capsys, repo, *argv)

    assert code == 2, out


def test_catch_up_refuses_a_merge_in_progress(repo, capsys):
    lane = _conflicting_lane(repo)
    assert _cli(capsys, lane, "catch-up", "--ticket", "T-1")[0] == 1

    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")

    assert code == 1 and "already in progress" in out, out


def test_release_refusals(repo, capsys):
    git(repo, "branch", "release")
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)
    code, out = _cli(capsys, repo, "release", "--ticket", "T-9")
    assert code == 1 and "no train entry" in out, out
    assert _cli(capsys, repo, "enqueue", "--ticket", "T-1", "--base", "main")[0] == 0
    assert _cli(capsys, repo, "enqueue", "--ticket", "T-1", "--base", "release")[0] == 0

    code, out = _cli(capsys, repo, "release", "--ticket", "T-1")

    assert code == 2 and "several bases" in out, out


def test_acquire_of_a_ticket_held_elsewhere_is_refused(repo, capsys):
    one, two = _worktree(repo, "wt1", "l1"), _worktree(repo, "wt2", "l2")
    _spec(one, "T-1", ["a.txt"])
    _spec(two, "T-1", ["a.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, one, "acquire", "--ticket", "T-1")[0] == 0

    code, out = _cli(capsys, two, "acquire", "--ticket", "T-1")

    assert code == 1 and "held from" in out, out


def test_lock_release_verifies_its_owner(repo, capsys):
    _arm(capsys, repo)
    path = os.path.join(crew_train.train_dir(str(repo)), "state.json")

    with crew_train._Lock(path) as lock:  # pylint: disable=protected-access
        with open(lock.path, "w", encoding="utf-8") as fh:
            fh.write("someone else")

    assert os.path.exists(path + ".lock")


def test_arm_leaves_no_staging_file(repo, capsys):
    _arm(capsys, repo)

    names = sorted(os.listdir(crew_train.train_dir(str(repo))))

    assert names == ["state.json"], names


def _failing(monkeypatch, match):
    real = crew_train._git  # pylint: disable=protected-access

    def fake(root, *args, **kwargs):
        if match(args):
            return 128, "", "fatal: fixture failure"
        return real(root, *args, **kwargs)
    monkeypatch.setattr(crew_train, "_git", fake)


def test_catch_up_rerere_probe_failure_is_could_not_tell(repo, capsys, monkeypatch):
    lane = _worktree(repo, "wt1", "l1")
    _failing(monkeypatch, lambda a: a[:1] == ("config",) and "extensions.worktreeConfig" in a)

    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")

    assert code == 3 and "could not tell" in out, out
    assert git(lane, "config", "--get", "rerere.enabled", check=False) == ""


def test_catch_up_unreadable_conflict_list_is_could_not_tell(repo, capsys, monkeypatch):
    lane = _conflicting_lane(repo)
    _failing(monkeypatch, lambda a: "--diff-filter=U" in a)

    code, out = _cli(capsys, lane, "catch-up", "--ticket", "T-1")

    assert code == 3 and "could not tell" in out, out
    assert _merge_log(repo, "T-1")[-1]["outcome"] == "could not tell"


# --- hardening: the PYTHON standards (T-0086) -----------------------------------------

def test_events_split_only_on_newline(repo, capsys):
    _arm(capsys, repo)
    path = os.path.join(crew_train.train_dir(str(repo)), "events.jsonl")
    raw = '{"kind": "release", "seq": 1, "ticket": "T-9", "note": "a\u2028b\x85c"}'
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(raw + "\n")

    events, problems = crew_train.read_events(str(repo))

    assert problems == [] and [e["ticket"] for e in events] == ["T-9"], (events, problems)


def test_merge_log_splits_only_on_newline(repo):
    path = crew_train.merge_log_path(str(repo), "T-1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write('{"outcome": "merged", "note": "x\u2029y"}\n')

    rows = _merge_log(repo, "T-1")

    assert [r["outcome"] for r in rows] == ["merged"]


def test_failed_state_replace_leaves_state_and_no_temp(repo, capsys, monkeypatch):
    _spec(repo, "T-1", ["a.txt"])
    _arm(capsys, repo)
    folder = crew_train.train_dir(str(repo))
    with open(os.path.join(folder, "state.json"), encoding="utf-8") as fh:
        before = fh.read()

    def refuse(_src, _dst):
        raise PermissionError(13, "held open", _dst)
    monkeypatch.setattr(crew_train.os, "replace", refuse)
    with pytest.raises(PermissionError):
        crew_train.enqueue(str(repo), "T-1")

    with open(os.path.join(folder, "state.json"), encoding="utf-8") as fh:
        assert fh.read() == before
    assert sorted(n for n in os.listdir(folder) if n != "events.jsonl") == ["state.json"]


@pytest.mark.parametrize("bad", [{"paths": "a.txt"}, {"paths": [1]}, {"touch": "a.txt"}])
def test_malformed_event_fields_broadcast_as_unreadable(repo, capsys, bad):
    _spec(repo, "T-2", ["zz/only.txt"])
    _arm(capsys, repo)
    assert _cli(capsys, repo, "enqueue", "--ticket", "T-2")[0] == 0
    path = os.path.join(crew_train.train_dir(str(repo)), "events.jsonl")
    event = {"kind": "merged" if "paths" in bad else "force-release", "seq": 99,
             "ticket": "T-1", "sha": "abc", "base": "main", "by": "o", "reason": "r"}
    event.update(bad)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")

    code, out = _cli(capsys, repo, "status")

    assert code == 0 and "T-2: T-1" in out and "unreadable" in out, out


def test_git_is_resolved_and_decoded_explicitly(repo, monkeypatch):
    seen = {}
    real = crew_train.subprocess.run

    def spy(argv, **kwargs):
        seen["argv0"], seen["kwargs"] = argv[0], kwargs
        return real(argv, **kwargs)  # pylint: disable=subprocess-run-check
    monkeypatch.setattr(crew_train.subprocess, "run", spy)

    code, _out, _err = crew_train._git(str(repo), "rev-parse", "HEAD")  # pylint: disable=protected-access

    assert code == 0 and os.path.isabs(seen["argv0"])
    assert seen["kwargs"]["encoding"] == "utf-8"
    assert seen["kwargs"]["errors"] == "surrogateescape"
    assert seen["kwargs"]["env"]["GIT_TERMINAL_PROMPT"] == "0"


# --- structure -----------------------------------------------------------------------

def test_only_the_review_path_imports_the_train():
    importers = set()
    for name in os.listdir(_SCRIPTS):
        if not name.endswith(".py") or name == "crew_train.py":
            continue
        with open(os.path.join(_SCRIPTS, name), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module] if isinstance(node, ast.ImportFrom) else [])
            if "crew_train" in names:
                importers.add(name)
    assert importers <= {"review_run.py", "review_prompt.py"}, importers
