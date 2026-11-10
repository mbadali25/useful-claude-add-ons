"""`/crew:review` bundles from the ticket's START, not the default-branch
merge-base.

Codex FIX (formerly `review.md:124`, now `review_run.review_base`): the bundle base was
`git merge-base HEAD "$DEFAULT_BRANCH"`, so on a branch carrying more than
this ticket the reviewer read -- and the receipt bound -- everything since the
trunk, not the ticket's change. `scope_base.py` already records where a ticket
started (`/crew:work` step 1) and falls back to the merge-base itself, naming
the fallback. Since L-0726 the base is `review_run.review_base`, which these tests call.
"""
import context  # noqa: F401  pylint: disable=unused-import
import review_fixtures as fx
import review_run


def test_review_base_comes_from_scope_base_first(monkeypatch, tmp_path):
    seen = []

    def fake(name, *argv):
        seen.append((name, argv))
        return 0, b"abc123\n"

    monkeypatch.setattr(review_run, "_run_tool", fake)

    result = review_run.review_base(".", str(tmp_path), "T1")

    assert result == ("abc123", None)
    assert seen == [("scope_base.py", ("--root", ".", "--base", "T1"))]


def test_review_merge_base_is_only_a_stated_fallback(monkeypatch, tmp_path):
    repo = fx.init_repo(tmp_path / "r")
    monkeypatch.setattr(review_run, "_run_tool", lambda name, *argv: (0, b""))
    del review_run.SAID[:]

    base, refused = review_run.review_base(".", str(repo), "T1")

    assert (base, refused) == (fx.git(repo, "rev-parse", "HEAD"), None)
    assert any("merge-base with" in line and "(fallback" in line for line in review_run.SAID)


def test_review_base_could_not_tell_stops_with_exit_3(monkeypatch, tmp_path):
    monkeypatch.setattr(review_run, "_run_tool", lambda name, *argv: (3, b""))

    assert review_run.review_base(".", str(tmp_path), "T1") == (None, 3)
