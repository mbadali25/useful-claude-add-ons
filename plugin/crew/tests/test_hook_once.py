"""Tests for the once-per-session hook claim."""
import os

import context  # noqa: F401  pylint: disable=unused-import
import hook_once


def test_first_caller_wins_and_second_loses(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    assert hook_once.claim(str(root), "pm-brief", "s1") is True
    assert hook_once.claim(str(root), "pm-brief", "s1") is False


def test_a_different_session_gets_its_own_claim(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    assert hook_once.claim(str(root), "pm-brief", "s1") is True
    assert hook_once.claim(str(root), "pm-brief", "s2") is True


def test_a_different_hook_gets_its_own_claim(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    assert hook_once.claim(str(root), "pm-brief", "s1") is True
    assert hook_once.claim(str(root), "handoff-read", "s1") is True


def test_the_claim_persists_within_a_session(tmp_path):
    """The module's LIMIT, asserted so a caller cannot miss it.

    The marker is never consumed, so repeated claims under one session id keep
    losing. That is correct for SessionStart, which fires once per session, and
    WRONG for Stop, which fires once per turn -- a Stop hook claiming here would
    run on turn 1 and silently skip every turn after. Do not use this module for
    an event that fires more than once per session.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    assert hook_once.claim(str(root), "verify-gate", "s1") is True
    for _ in range(5):
        assert hook_once.claim(str(root), "verify-gate", "s1") is False


def test_no_session_id_fails_open(tmp_path):
    # Nothing to scope a claim to. Running twice is bad; never running is worse.
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    assert hook_once.claim(str(root), "pm-brief", None) is True
    assert hook_once.claim(str(root), "pm-brief", "") is True


def test_a_repo_with_no_crew_dir_fails_open(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert hook_once.claim(str(plain), "pm-brief", "s1") is True
    assert hook_once.claim(str(plain), "pm-brief", "s1") is True


def test_markers_land_under_crew_and_are_named_for_the_hook(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    hook_once.claim(str(root), "pm-brief", "abc")
    assert (root / ".crew" / ".hook-pm-brief-abc").exists()


def test_a_stale_marker_is_pruned(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    marker = root / ".crew" / ".hook-pm-brief-old"
    marker.write_text("", encoding="utf-8")
    stale = os.path.getmtime(marker) - (hook_once._STALE_SECONDS + 60)  # pylint: disable=protected-access
    os.utime(marker, (stale, stale))
    assert hook_once.claim(str(root), "pm-brief", "old") is True


def test_main_returns_zero_when_it_wins_and_one_when_it_loses(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    assert hook_once.main(["pm-brief", "s1"]) == 0
    assert hook_once.main(["pm-brief", "s1"]) == 1


def test_main_with_too_few_arguments_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert hook_once.main([]) == 0
    assert hook_once.main(["pm-brief"]) == 0
