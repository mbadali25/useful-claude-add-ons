"""Tests for handoff staleness detection and archiving.

See crew_state.py's "Handoff staleness" section for what each signal catches
and why. Every fixture here is a real git repository (crew_fixtures.make_repo)
for the same reason the rest of this suite insists on one: the code under
test asks git for HEAD and ancestry, and mocking that would test the mock.
"""
import json
import os
import time

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _iso(epoch):
    return time.strftime(_ISO, time.gmtime(epoch))


def _write_handoff(root, written=None, branch=None, head=None,
                   body="## Next action\nSomething.\n"):
    lines = ["# Handoff"]
    if written is not None:
        lines.append(f"written: {written}")
    if branch is not None:
        lines.append(f"branch: {branch}")
    if head is not None:
        lines.append(f"head: {head}")
    lines.append("")
    lines.append(body)
    path = os.path.join(str(root), ".work", "HANDOFF.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path


def _read(path):
    return crew_state.read_text(path)


def _current_branch(root):
    # Not hardcoded "main": git's init.defaultBranch is a local/CI setting
    # (this machine's default is "master"), and hardcoding the wrong one
    # would make every "matches the checkout" test assert branch MISMATCH
    # instead of match.
    return crew_state.git_out(str(root), "rev-parse", "--abbrev-ref", "HEAD")


# --- handoff_staleness -------------------------------------------------------


def test_fresh_handoff_is_not_stale(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head=head,
    )
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got == {
        "stale": False, "reasons": [],
        "ageHours": got["ageHours"], "commitsBehind": 0,
    }
    assert got["ageHours"] < 2


def test_age_past_the_configured_limit_is_stale(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 200 * 3600), branch=_current_branch(root),
        head=head,
    )
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["stale"] is True
    assert any("h old" in r for r in got["reasons"])


def test_written_line_with_handoff_writes_auto_suffix_still_parses(
    tmp_path,
):
    # handoff-write.sh's auto skeleton stamps
    # `written: <iso> (auto, at <trigger> compact)` -- the regex must capture
    # only the timestamp token, not the whole line.
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = os.path.join(str(root), ".work", "HANDOFF.md")
    branch = _current_branch(root)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            f"# Handoff\nwritten: {_iso(now - 200 * 3600)} "
            f"(auto, at compact compact)\nbranch: {branch}\nhead: {head}\n"
        )
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["ageHours"] is not None
    assert got["stale"] is True


def test_commits_landed_past_the_noted_head_is_stale(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head=head,
    )
    for i in range(3):
        (root / f"file{i}.txt").write_text("x", encoding="utf-8")
        crew_fixtures.commit_with_date(str(root), f"file{i}.txt", _iso(now))
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["stale"] is True
    assert got["commitsBehind"] == 3
    assert any("commit(s) have landed" in r for r in got["reasons"])


def test_two_commits_behind_stays_under_the_default_limit(tmp_path):
    # The default limit is 3 -- two real commits landing on top of a note
    # (the exact case that motivated this feature) must not itself trip the
    # default; a repo that wants it tighter sets maxCommitsBehind.
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head=head,
    )
    for i in range(2):
        (root / f"file{i}.txt").write_text("x", encoding="utf-8")
        crew_fixtures.commit_with_date(str(root), f"file{i}.txt", _iso(now))
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["commitsBehind"] == 2
    assert got["stale"] is False


def test_config_can_tighten_the_commits_behind_limit(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head=head,
    )
    for i in range(2):
        (root / f"file{i}.txt").write_text("x", encoding="utf-8")
        crew_fixtures.commit_with_date(str(root), f"file{i}.txt", _iso(now))
    cfg = {"context": {"staleHandoff": {"maxCommitsBehind": 2}}}
    got = crew_state.handoff_staleness(str(root), _read(path), cfg, now=now)
    assert got["stale"] is True


def test_branch_mismatch_is_stale(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(root, written=_iso(now - 3600),
                          branch="feature/some-other-ticket", head=head)
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["stale"] is True
    assert any("checkout is now on" in r for r in got["reasons"])


def test_unknown_head_is_stale(tmp_path):
    # A sha this checkout has never seen -- a different clone, or history
    # rewritten past it. Unverifiable provenance resolves to stale, matching
    # how _read_graph and read_diagrams treat a graph or diagram with no
    # recorded provenance elsewhere in this module.
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now)
    assert got["stale"] is True
    assert any("not a commit this repository can find" in r
              for r in got["reasons"])


def test_no_signals_at_all_is_not_stale(tmp_path):
    """A hand-written note with none of the template's header lines cannot be
    judged by either signal. Unlike _read_graph / read_diagrams -- where a
    missing anchor means the generating tool never ran -- a handoff is free
    prose, and omitting the header is a legitimate (if imperfect) use of the
    format, so unknown here must NOT resolve to stale."""
    root = crew_fixtures.make_repo(tmp_path)
    path = os.path.join(str(root), ".work", "HANDOFF.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Handoff\n\n## Next action\nSomething.\n")
    got = crew_state.handoff_staleness(str(root), _read(path), {},
                                       now=time.time(), mtime=None)
    assert got["stale"] is False
    assert got["ageHours"] is None


def test_mtime_is_the_fallback_age_signal_when_written_is_absent(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(root, branch=_current_branch(root), head=head)  # no written:
    old_mtime = now - 200 * 3600
    got = crew_state.handoff_staleness(str(root), _read(path), {}, now=now,
                                       mtime=old_mtime)
    assert got["stale"] is True
    assert any("file mtime" in r for r in got["reasons"])


def test_handoff_path_honours_the_configured_override(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    cfg = {"context": {"handoffPath": ".work/CUSTOM.md"}}
    got = crew_state.handoff_path(str(root), cfg)
    assert got == os.path.realpath(
        os.path.join(str(root), ".work", "CUSTOM.md")
    )


# --- archive_stale_handoff ---------------------------------------------------


def test_archive_reports_no_handoff_when_none_exists(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    got = crew_state.archive_stale_handoff(str(root), {})
    assert got["archived"] is False
    assert got["reason"] == "no handoff"


def test_archive_leaves_a_fresh_handoff_exactly_in_place(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    head = crew_fixtures.head_sha(root, length=40)
    path = _write_handoff(
        root, written=_iso(now - 3600), branch=_current_branch(root),
        head=head,
    )
    before = _read(path)
    got = crew_state.archive_stale_handoff(str(root), {}, now=now)
    assert got["archived"] is False
    assert got["reason"] == "fresh"
    assert os.path.exists(path)
    assert _read(path) == before


def test_archive_moves_a_stale_handoff_and_preserves_its_content(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    path = _write_handoff(
        root, written=_iso(now - 200 * 3600),
        branch=_current_branch(root),
        head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    original = _read(path)
    got = crew_state.archive_stale_handoff(str(root), {}, now=now)
    assert got["archived"] is True
    assert not os.path.exists(path)  # never left in the original spot
    assert os.path.exists(got["archivedPath"])
    assert _read(got["archivedPath"]) == original  # never deleted, never edited
    assert got["archivedPath"].startswith(
        os.path.join(str(root), crew_state.HANDOFF_ARCHIVE_DIR)
    )


def test_archive_does_not_clobber_a_same_minute_collision(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    now = time.time()
    archive_dir = os.path.join(str(root), crew_state.HANDOFF_ARCHIVE_DIR)
    os.makedirs(archive_dir, exist_ok=True)
    base = time.strftime("HANDOFF-%Y%m%d-%H%M", time.gmtime(now))
    earlier = os.path.join(archive_dir, base + ".md")
    with open(earlier, "w", encoding="utf-8") as handle:
        handle.write("earlier archive\n")

    _write_handoff(
        root, written=_iso(now - 200 * 3600),
        branch=_current_branch(root),
        head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    got = crew_state.archive_stale_handoff(str(root), {}, now=now)
    assert got["archived"] is True
    assert got["archivedPath"] != earlier
    with open(earlier, encoding="utf-8") as handle:
        assert handle.read() == "earlier archive\n"  # untouched, not overwritten


def test_cli_archive_stale_handoff_prints_the_verdict_as_json(tmp_path,
                                                               capsys):
    root = crew_fixtures.make_repo(tmp_path)
    _write_handoff(
        root, written=_iso(time.time() - 200 * 3600),
        branch=_current_branch(root),
        head="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    code = crew_state.main(["--root", str(root), "--archive-stale-handoff"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["archived"] is True
    assert "reasons" in payload
