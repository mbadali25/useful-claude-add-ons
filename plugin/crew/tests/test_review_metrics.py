"""`review_run.py` writes the `.crew/metrics.md` row for every round it records (L-0578).

Measured 2026-10-01: 162 ledger rounds, 59 scored rows in the main checkout's
`.crew/metrics.md`. /crew:review's step 6 appended the row by prose, and lanes
and headless reviewers skipped it; rows that were written from a linked
worktree went to that worktree's own (gitignored) `.crew/`, which the main
checkout never reads. Every case runs against a throwaway repository under
tmp_path and the fake `codex` from `review_fixtures`.
"""
import json
import os
import subprocess
import sys

import pytest

# isort: split
import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import crew_standards
import crew_state
import scope_base
import review_ledger
import review_limit
import review_metrics
from review_fixtures import bundle, env_with_path, fake_reviewer_bin, git, init_repo, run_review

_RUN = os.path.join(os.path.dirname(os.path.abspath(review_metrics.__file__)), "review_run.py")


def _rows(root):
    path = os.path.join(str(root), ".crew", "metrics.md")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line for line in fh.read().splitlines() if line.strip()]


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


@pytest.fixture(name="repo")
def _repo(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    return repo


def _codex(repo, tmp_path, mode, name="s"):
    scratch = tmp_path / name
    bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    return run_review(repo, scratch, fakes, mode, "--model", "gpt-5.6-sol",
                      "--work-dir", str(tmp_path / f"w-{name}"))


def _claude(repo, scratch, *extra):
    return subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
         "--provider", "claude"] + list(extra),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120,
        env=env_with_path(scratch))


def test_codex_findings_round_appends_one_scored_row(repo, tmp_path):
    result = _codex(repo, tmp_path, "findings")

    rows = _rows(repo)
    assert (result.returncode, len(rows), _cells(rows[0])[1:]) == (
        1, 1, ["T1", _cells(rows[0])[2], "0", "1"]), result.stdout + result.stderr


def test_codex_row_names_provider_model_round_and_std(repo, tmp_path):
    _codex(repo, tmp_path, "findings")

    assert _cells(_rows(repo)[0])[2].startswith("codex/gpt-5.6-sol (r1, std:none, ")


def test_scored_row_is_counted_by_read_metrics(repo, tmp_path):
    _codex(repo, tmp_path, "findings")

    health = crew_state.read_metrics(str(repo))

    assert (health["tickets"], health["findings"]) == (1, 1)


def test_clean_round_appends_a_zero_row(repo, tmp_path):
    result = _codex(repo, tmp_path, "clean")

    assert (result.returncode, _cells(_rows(repo)[0])[3:]) == (0, ["0", "0"]), result.stdout


def test_incomplete_round_is_recorded_as_incomplete_not_zero(repo, tmp_path):
    """A failed call is retried once (L-0514): one row per round, both INCOMPLETE."""
    result = _codex(repo, tmp_path, "fail")

    rows = _rows(repo)
    assert (result.returncode, len(rows), [_cells(r)[3:] for r in rows],
            crew_state.read_metrics(str(repo))["tickets"]) == (
        3, 2, [["INCOMPLETE", "INCOMPLETE"]] * 2, 0), result.stdout + result.stderr


def test_two_rounds_write_two_rows_for_one_ticket(repo, tmp_path):
    _codex(repo, tmp_path, "findings", "s1")
    (repo / "change.txt").write_text("changed again\n", encoding="utf-8")
    _codex(repo, tmp_path, "findings", "s2")

    rows = _rows(repo)
    assert ([("(r1," in r, "(r2," in r) for r in rows],
            crew_state.read_metrics(str(repo))["tickets"]) == (
        [(True, False), (False, True)], 1)


def test_claude_reserve_only_writes_no_row(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)

    result = _claude(repo, scratch, "--reserve-only", "--authors", "gpt")

    assert (result.stdout.strip(), _rows(repo)) == ("ROUND=1", []), result.stderr


def test_claude_recorded_round_writes_exactly_one_row(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")
    (scratch / "out.txt").write_text("BLOCK: a.py:1 broken\n", encoding="utf-8")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    rows = _rows(repo)
    assert [(_cells(r)[1], _cells(r)[2].split(" (")[0]) for r in rows] == [("T1", "claude/default")]


def test_claude_round_after_a_codex_limit_is_labelled_same_family(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")
    review_limit.record(str(repo), "T1", 0, "codex", "gpt-5.6-sol", "You've hit your usage limit.")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert "same-family: codex limit" in _cells(_rows(repo)[0])[2]


def test_claude_round_with_an_older_codex_limit_is_not_labelled_codex_limit(repo, tmp_path):
    review_limit.record(str(repo), "T1", 5, "codex", "gpt-5.6-sol", "You've hit your usage limit.")
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert "codex limit" not in _rows(repo)[0]


def test_a_linked_worktree_writes_the_main_checkouts_file(tmp_path):
    main = init_repo(tmp_path / "main")
    lane = tmp_path / "lane"
    git(main, "worktree", "add", "-q", "-b", "lane", str(lane))
    (lane / "change.txt").write_text("change\n", encoding="utf-8")

    _codex(lane, tmp_path, "findings")

    assert (len(_rows(main)), os.path.exists(lane / ".crew")) == (1, False)


def test_a_failed_write_keeps_the_verdict_and_prints_the_line(repo, tmp_path):
    (repo / ".crew" / "metrics.md").mkdir(parents=True)

    result = _codex(repo, tmp_path, "findings")

    ledger = review_ledger.status(str(repo), "T1")
    assert (result.returncode, ledger["rounds"][0]["verdict"],
            "metrics row NOT written" in result.stdout, "| T1 | codex/" in result.stdout) == (
        1, "FINDINGS", True, True), result.stdout + result.stderr


def test_the_written_path_is_printed(repo, tmp_path):
    result = _codex(repo, tmp_path, "findings")

    assert "review: metrics row appended to " + os.path.join(
        os.path.realpath(str(repo)), ".crew", "metrics.md") in result.stdout, result.stdout


def test_a_pipe_in_the_model_never_splits_a_cell():
    line = review_metrics.row("2026-10-01", "T1", "copilot", "a|b", 2, "std:none", "x|y",
                              "FINDINGS", {"BLOCK": 1, "FIX": 2}, refunded=False)

    assert len(_cells(line)) == 5


def test_row_reads_as_one_round_for_the_round_parser():
    line = review_metrics.row("2026-10-01", "T1", "codex", "gpt-5.6-sol", 3, "std:abcd1234",
                              "different family, author from config", "FINDINGS",
                              {"BLOCK": 1, "FIX": 0}, refunded=False)

    assert line == ("2026-10-01 | T1 | codex/gpt-5.6-sol (r3, std:abcd1234, different family, "
                    "author from config) | 1 | 0")


def test_refunded_round_says_so():
    line = review_metrics.row("2026-10-01", "T1", "codex", "", 2, "std:none", "family unknown",
                              "INCOMPLETE", {"BLOCK": 0, "FIX": 0}, refunded=True)

    assert line.endswith("(r2, std:none, family unknown, refunded) | INCOMPLETE | INCOMPLETE")


def test_metrics_path_outside_git_is_the_roots(tmp_path):
    path, note = review_metrics.metrics_path(str(tmp_path))

    assert (path, note) == (os.path.join(str(tmp_path), ".crew", "metrics.md"), "")


def test_append_adds_a_missing_trailing_newline_first(tmp_path):
    path = tmp_path / "m.md"
    path.write_text("old row without newline", encoding="utf-8")

    review_metrics.append(str(path), "new row")

    assert path.read_text(encoding="utf-8") == "old row without newline\nnew row\n"


@pytest.mark.parametrize("families,source,expected", [
    (frozenset({"claude"}), "dispatch", "same-family, author from dispatch"),
    (frozenset({"claude"}), "config", "same-family, author from config"),
    (frozenset({"claude", "gpt"}), "unknown", "same-family, author from unknown"),
    (frozenset({"gpt"}), "dispatch", "different family, author from dispatch"),
    (frozenset({"gpt"}), "config", "different family unproven, author from config"),
    (frozenset({"gpt"}), "stale", "different family unproven, author from stale"),
    (frozenset({"gpt"}), "unknown", "family unknown, author from unknown"),
    (frozenset({"gpt"}), "unreadable config", "family unknown, author from unreadable config"),
    (frozenset({"claude"}), "unreadable config", "same-family, author from unreadable config"),
    (frozenset(), "config", "family unknown, author from config"),
])
def test_family_relation(families, source, expected):
    assert review_metrics.family_relation("claude", families, source) == expected


def test_family_relation_with_an_unknown_reviewer_family_is_unknown():
    assert review_metrics.family_relation(None, frozenset({"gpt"}), "dispatch") == (
        "family unknown, author from dispatch")


def test_review_json_is_unchanged_by_the_row(repo, tmp_path):
    _codex(repo, tmp_path, "findings")

    review = json.loads((tmp_path / "w-s" / "review.json").read_text(encoding="utf-8"))
    assert "metrics" not in json.dumps(sorted(review))


def test_claude_round_with_a_codex_limit_note_is_labelled_same_family(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"),
            "--note", "codex-probe=5")

    assert "(r1, std:none, same-family: codex limit, " in _rows(repo)[0]


@pytest.mark.parametrize("note", ["codex-probe=0", "codex-probe=6", "codex-probe=not-run", ""])
def test_a_claude_note_that_is_not_a_limit_is_not_labelled_one(monkeypatch, note):
    monkeypatch.setattr(review_metrics.crew_state, "author_families",
                        lambda root, cfg: (frozenset({"claude"}), "config"))
    monkeypatch.setattr(review_metrics, "codex_limit_before", lambda *a: False)

    tag = review_metrics.family_tag("/nonexistent-l0578", "T1", 1, "claude", "claude", note)

    assert tag == "same-family, author from config"


def test_a_row_that_cannot_be_built_keeps_the_verdict(repo, tmp_path):
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text("{not json", encoding="utf-8")

    result = _codex(repo, tmp_path, "findings")

    assert (result.returncode, review_ledger.status(str(repo), "T1")["rounds"][0]["verdict"]) == (
        1, "FINDINGS"), result.stdout + result.stderr


def test_record_never_raises_when_building_the_row_fails(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise review_ledger.LedgerError("git rev-parse --git-common-dir could not run")
    monkeypatch.setattr(review_metrics, "family_tag", boom)

    line = review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {}},
                                 "std:none")

    assert (line.startswith("review: metrics row NOT written (could not build it: "),
            os.path.exists(tmp_path / ".crew")) == (True, False)


def test_an_unresolvable_main_checkout_writes_nothing_and_quotes_the_row(monkeypatch, tmp_path):
    monkeypatch.setattr(review_metrics.crew_common, "_main_checkout",
                        lambda root: (None, "git could not name its main checkout"))
    monkeypatch.setattr(review_metrics, "family_tag", lambda *a, **k: "family unknown, author from unknown")

    line = review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {},
                                                          "provider": "codex"},
                                 "std:none")

    assert (line.startswith("review: metrics row NOT written (git could not name"),
            "| T1 | codex/default (r1, " in line, os.path.exists(tmp_path / ".crew")) == (
        True, True, False)


def test_a_short_write_is_finished_not_duplicated(monkeypatch, tmp_path):
    real = os.write
    calls = []

    def short(fd, data):
        calls.append(len(data))
        return real(fd, data[:3] if len(calls) == 1 else data)
    monkeypatch.setattr(review_metrics.os, "write", short)

    review_metrics.append(str(tmp_path / "m.md"), "a row")

    assert ((tmp_path / "m.md").read_text(encoding="utf-8"), len(calls)) == ("a row\n", 2)


def test_a_write_failing_after_some_bytes_reports_a_partial_row(monkeypatch, tmp_path):
    real = os.write
    calls = []

    def fail_second(fd, data):
        calls.append(1)
        if len(calls) > 1:
            raise OSError(28, "No space left on device")
        return real(fd, data[:2])
    monkeypatch.setattr(review_metrics.os, "write", fail_second)
    monkeypatch.setattr(review_metrics, "family_tag", lambda *a, **k: "family unknown, author from unknown")

    line = review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {}},
                                 "std:none")

    assert line.startswith("review: metrics row PARTLY written to "), line


def test_the_row_survives_a_review_json_that_cannot_be_written(repo, tmp_path):
    blocked = tmp_path / "w-blocked"
    blocked.write_text("a file where the work dir should be\n", encoding="utf-8")
    scratch = tmp_path / "s"
    bundle(repo, scratch)

    result = run_review(repo, scratch, fake_reviewer_bin(tmp_path / "bin"), "findings",
                        "--work-dir", str(blocked))

    assert (result.returncode != 0, len(_rows(repo))) == (True, 1), result.stdout + result.stderr


def test_a_multi_line_error_prints_as_one_line(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise ValueError("first line\nsecond line")
    monkeypatch.setattr(review_metrics, "family_tag", boom)

    line = review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {}},
                                 "std:none")

    assert ("\n" in line, "first line second line" in line) == (False, True)


def _record(tmp_path):
    return review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {}},
                                 "std:none")


@pytest.fixture(name="known_family")
def _known_family(monkeypatch):
    monkeypatch.setattr(review_metrics, "family_tag", lambda *a, **k: "family unknown, author from x")


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32",
                    reason="symlinks need privileges on Windows")
def test_a_symlinked_metrics_file_is_not_followed(tmp_path, known_family):
    outside = tmp_path / "outside.txt"
    outside.write_text("victim\n", encoding="utf-8")
    (tmp_path / ".crew").mkdir()
    os.symlink(outside, tmp_path / ".crew" / "metrics.md")

    line = _record(tmp_path)

    assert (line.startswith("review: metrics row NOT written"),
            outside.read_text(encoding="utf-8")) == (True, "victim\n"), line


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32",
                    reason="symlinks need privileges on Windows")
def test_a_symlinked_crew_dir_is_not_followed(tmp_path, known_family):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, tmp_path / ".crew")

    line = _record(tmp_path)

    assert (line.startswith("review: metrics row NOT written"), os.listdir(elsewhere)) == (
        True, []), line


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_fifo_is_refused_without_blocking(tmp_path, known_family):
    (tmp_path / ".crew").mkdir()
    os.mkfifo(tmp_path / ".crew" / "metrics.md")

    line = _record(tmp_path)

    assert line.startswith("review: metrics row NOT written"), line


def test_a_regular_file_is_still_appended(tmp_path, known_family):
    (tmp_path / ".crew").mkdir()
    (tmp_path / ".crew" / "metrics.md").write_text("old\n", encoding="utf-8")

    line = _record(tmp_path)

    assert ((tmp_path / ".crew" / "metrics.md").read_text(encoding="utf-8").count("\n"),
            line.startswith("review: metrics row appended to ")) == (2, True), line


def test_a_close_failing_after_the_write_says_the_row_is_written(monkeypatch, tmp_path,
                                                                    known_family):
    real = os.close

    def close_then_fail(fd):
        real(fd)
        raise OSError(5, "Input/output error")
    monkeypatch.setattr(review_metrics.os, "close", close_then_fail)

    line = _record(tmp_path)

    assert ("the row is written" in line,
            (tmp_path / ".crew" / "metrics.md").read_text(encoding="utf-8").count("| T1 |")) == (
        True, 1), line


def test_prose_naming_the_limit_does_not_label_it(monkeypatch):
    monkeypatch.setattr(review_metrics.crew_state, "author_families",
                        lambda root, cfg: (frozenset({"claude"}), "config"))
    monkeypatch.setattr(review_metrics, "codex_limit_before", lambda *a: False)

    tag = review_metrics.family_tag("/nonexistent-l0578", "T1", 1, "claude", "claude",
                                    "codex-probe=0 same-family: codex limit was not observed")

    assert tag == "same-family, author from config"



# ---- L-0578 review round 2 (owner: fix all 5, no third round) ----

_POSIX_LINKS = pytest.mark.skipif(sys.platform == "win32" or not hasattr(os, "symlink"),
                                  reason="POSIX symlinks")


@_POSIX_LINKS
def test_the_open_itself_refuses_a_crew_symlink_swapped_in_after_the_check(
        monkeypatch, tmp_path, known_family):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, tmp_path / ".crew")
    # Every check passes, as if the link were swapped in after each one: only
    # the open itself can refuse it.
    monkeypatch.setattr(review_metrics, "_refuse_links", lambda path: None)
    monkeypatch.setattr(review_metrics, "is_link_or_junction", lambda path: False)

    line = _record(tmp_path)

    assert (line.startswith("review: metrics row NOT written"), os.listdir(elsewhere)) == (
        True, []), line


@_POSIX_LINKS
def test_the_open_itself_refuses_a_metrics_symlink_swapped_in_after_the_check(
        monkeypatch, tmp_path, known_family):
    outside = tmp_path / "outside.txt"
    outside.write_text("victim\n", encoding="utf-8")
    (tmp_path / ".crew").mkdir()
    os.symlink(outside, tmp_path / ".crew" / "metrics.md")
    monkeypatch.setattr(review_metrics, "_refuse_links", lambda path: None)

    line = _record(tmp_path)

    assert (line.startswith("review: metrics row NOT written"),
            outside.read_text(encoding="utf-8")) == (True, "victim\n"), line


class _Stat:  # pylint: disable=too-few-public-methods
    def __init__(self, mode, attributes):
        self.st_mode, self.st_file_attributes = mode, attributes


@pytest.mark.parametrize("attributes,expected", [(0x400, True), (0x410, True), (0x10, False),
                                                 (0, False)])
def test_a_windows_reparse_point_is_a_link(monkeypatch, attributes, expected):
    monkeypatch.setattr(review_metrics.os, "lstat", lambda p: _Stat(0o040755, attributes))

    assert review_metrics.is_link_or_junction("C:/repo/.crew") is expected


def test_a_junction_parent_is_refused(monkeypatch, tmp_path, known_family):
    (tmp_path / ".crew").mkdir()
    crew = str(tmp_path / ".crew")
    real = review_metrics.is_link_or_junction
    monkeypatch.setattr(review_metrics, "is_link_or_junction",
                        lambda p: True if os.path.normpath(p) == os.path.normpath(crew) else real(p))

    line = _record(tmp_path)

    assert (line.startswith("review: metrics row NOT written"),
            os.listdir(tmp_path / ".crew")) == (True, []), line


def test_a_plain_directory_is_not_a_link(tmp_path):
    assert review_metrics.is_link_or_junction(str(tmp_path)) is False


def _marker(repo, text=None, fifo=False):
    path = review_limit.marker_path(str(repo), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fifo:
        os.mkfifo(path)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return path


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_fifo_limit_marker_neither_blocks_nor_claims_a_limit(repo):
    _marker(repo, fifo=True)

    state = review_metrics.codex_limit_before(str(repo), "T1", 1)

    assert state == review_metrics.MARKER_UNREADABLE


@pytest.mark.parametrize("text", ['{"round": 0}', '{"round": 0, "provider": "claude", "error": "x"}',
                                  '{"round": 0, "provider": "codex", "error": ""}',
                                  '{"round": true, "provider": "codex", "error": "x"}',
                                  '[0]', "not json"])
def test_a_malformed_limit_marker_is_unreadable_not_a_limit(repo, text):
    _marker(repo, text)

    assert review_metrics.codex_limit_before(str(repo), "T1", 1) == (
        review_metrics.MARKER_UNREADABLE)


def test_a_well_formed_marker_for_the_round_before_is_a_limit(repo):
    _marker(repo, '{"round": 0, "provider": "codex", "error": "You have hit your usage limit"}')

    assert review_metrics.codex_limit_before(str(repo), "T1", 1) is True


def test_no_marker_is_no_limit(repo):
    assert review_metrics.codex_limit_before(str(repo), "T1", 1) is False


def test_an_unreadable_marker_is_named_in_the_family_tag(monkeypatch, repo):
    _marker(repo, '{"round": 0}')
    monkeypatch.setattr(review_metrics.crew_state, "author_families",
                        lambda root, cfg: (frozenset({"claude"}), "config"))

    tag = review_metrics.family_tag(str(repo), "T1", 1, "claude", "claude")

    assert tag == "same-family, author from config, codex-limit marker unreadable"


def test_a_malformed_config_is_not_reported_as_config_provenance(repo, tmp_path):
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text("{not json", encoding="utf-8")

    _codex(repo, tmp_path, "findings")

    assert "author from unreadable config)" in _rows(repo)[0], _rows(repo)


def test_a_readable_config_is_config_provenance(repo, tmp_path):
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text('{"dev": {"provider": "claude"}}',
                                                encoding="utf-8")

    _codex(repo, tmp_path, "findings")

    assert "author from config)" in _rows(repo)[0], _rows(repo)


def _gated(repo):
    """An approved ticket T1 with a stamped self-check, so the std: token is a digest."""
    scope_base.record(str(repo), "T1")
    path = crew_ticket.approval_path(str(repo), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": "T1", "approved_by": "fixture"}, fh)
    assert crew_standards.init(str(repo), "T1")[0] == 0
    check = repo / ".work" / "tickets" / "T1" / "selfcheck.md"
    import re  # pylint: disable=import-outside-toplevel
    check.write_text(re.sub(r"^\| ([A-Z]+-\d\d) \|  \|  \|$",
                            r"| \1 | n/a | the fixture change is one text file |",
                            check.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    code, lines = crew_standards.stamp(str(repo), "T1")
    assert code == 0, lines


def test_the_std_token_is_the_one_checked_at_reservation(repo, tmp_path):
    _gated(repo)
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    reserved = _claude(repo, scratch, "--reserve-only", "--authors", "gpt")
    token = reserved.stderr.split("(std:", 1)[1][:8]
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "standards.md").write_text(
        '---\nset: REPO\napplies-to: ["**"]\n---\n\n## REPO-01 Local\n\n**Rule.** r\n\n'
        "**Self-check.** s\n", encoding="utf-8")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert f"(r1, std:{token}, " in _rows(repo)[0], (reserved.stderr, _rows(repo))


def test_a_codex_round_carries_its_reservation_token(repo, tmp_path):
    _gated(repo)

    result = _codex(repo, tmp_path, "findings")

    token = result.stderr.split("(std:", 1)[1][:8]
    assert f"(r1, std:{token}, " in _rows(repo)[0], (result.stderr, _rows(repo))


def test_no_reservation_record_is_std_unknown_never_a_recomputation(repo, tmp_path):
    _gated(repo)
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")
    os.remove(scratch / "reserved-std.json")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert "(r1, std:unknown, " in _rows(repo)[0], _rows(repo)


def test_a_reservation_record_for_another_round_is_not_used(repo, tmp_path):
    _gated(repo)
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only", "--authors", "gpt")
    record = json.loads((scratch / "reserved-std.json").read_text(encoding="utf-8"))
    record["round"] = 7
    (scratch / "reserved-std.json").write_text(json.dumps(record), encoding="utf-8")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert "(r1, std:unknown, " in _rows(repo)[0], _rows(repo)
