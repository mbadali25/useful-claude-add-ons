"""Rebuilding a reviewed bundle after its head merged into main (L-0770).

`review_delta.reviewed_bundle` asks `merged_main.resolve` which main commit
the head had merged. Once the head itself is merged into main, `merge-base
<head> main` IS the head, so every committed path reads as identical to merged
main and the rebuild drops all of it: the accepted bundle can never be rebuilt
again. promote-gate's release mode (L-0765) needs exactly that rebuild, so the
caller may pin the merged commit with `merged_main.pinned`: the commit that
was main's merged commit when the round ran.

Must-match: a pinned rebuild equals the bundle the round read (with and
without a catch-up merge of main). Must-not-match: a review of a dirty tree,
and an unpinned rebuild after the merge (the defect this exists for).
Every repository is built under tmp_path.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import merged_main
import review_delta
import review_patch
from review_fixtures import git, init_repo


def _commit(root, files, message):
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


class World:  # pylint: disable=too-few-public-methods
    """main, a lane cut from it at `start`, a ticket commit, main moving on."""

    def __init__(self, tmp_path, catch_up):
        self.repo = init_repo(tmp_path / "r")
        self.start = _commit(self.repo, {"app.py": "def app():\n    return 1\n"}, "seed")
        self.lane = tmp_path / "lane"
        git(self.repo, "worktree", "add", "-q", "-b", "lane", str(self.lane), "main")
        _commit(self.lane, {"app.py": "def app():\n    return 2\n"}, "ticket")
        _commit(self.repo, {"other.py": "x = 1\n"}, "main moved")
        if catch_up:
            git(self.lane, "merge", "--no-edit", "-q", "main")
        self.head = git(self.lane, "rev-parse", "HEAD")

    def review(self):
        """The bundle /crew:review would build and a round would accept."""
        return review_patch.compute(str(self.lane), self.start)[0]["bundle_sha256"]

    def land(self):
        """Merge the lane into main with a merge commit; return its first parent."""
        first = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "merge", "--no-ff", "--no-edit", "-q", "lane")
        return first


@pytest.mark.parametrize("catch_up", [True, False], ids=["caught-up", "not-caught-up"])
def test_a_pinned_rebuild_after_landing_is_the_reviewed_bundle(tmp_path, catch_up):
    """MUST MATCH: pinned to merge-base(head, merge's first parent)."""
    world = World(tmp_path, catch_up)
    accepted = world.review()
    first = world.land()
    pin = merged_main.pinned(str(world.repo), world.start,
                             git(world.repo, "merge-base", world.head, first))
    rebuilt, _ = review_delta.reviewed_bundle(str(world.repo), world.start, world.head, pin)
    assert rebuilt == accepted


def test_an_unpinned_rebuild_after_landing_is_not_the_reviewed_bundle(tmp_path):
    """The defect: once the head is in main, resolve() drops everything."""
    world = World(tmp_path, catch_up=True)
    accepted = world.review()
    world.land()
    git(world.repo, "checkout", "-q", "-b", "probe")
    rebuilt, _ = review_delta.reviewed_bundle(str(world.repo), world.start, world.head)
    assert rebuilt != accepted


def test_a_review_of_a_dirty_tree_is_not_rebuilt_by_a_pin(tmp_path):
    """MUST NOT MATCH: the round read uncommitted bytes the head lacks."""
    world = World(tmp_path, catch_up=True)
    (world.lane / "app.py").write_text("def app():\n    return 3\n", encoding="utf-8")
    accepted = world.review()
    git(world.lane, "checkout", "--", "app.py")
    first = world.land()
    pin = merged_main.pinned(str(world.repo), world.start,
                             git(world.repo, "merge-base", world.head, first))
    rebuilt, _ = review_delta.reviewed_bundle(str(world.repo), world.start, world.head, pin)
    assert rebuilt != accepted


@pytest.mark.parametrize("commit", ["", None, "0" * 40, "no-such-ref"])
def test_a_pin_that_names_no_commit_is_could_not_tell(tmp_path, commit):
    world = World(tmp_path, catch_up=False)
    pin = merged_main.pinned(str(world.repo), world.start, commit)
    assert pin["commit"] is None and pin["applies"] is False
    assert pin["reason"].startswith(merged_main.UNKNOWN)


def test_a_pin_before_the_start_drops_nothing(tmp_path):
    world = World(tmp_path, catch_up=False)
    pin = merged_main.pinned(str(world.repo), world.start, world.start)
    assert pin["commit"] == world.start and pin["applies"] is False


def test_a_pin_past_the_start_applies(tmp_path):
    world = World(tmp_path, catch_up=True)
    main_moved = git(world.repo, "rev-parse", "main")
    pin = merged_main.pinned(str(world.repo), world.start, main_moved)
    assert pin["commit"] == main_moved and pin["applies"] is True
