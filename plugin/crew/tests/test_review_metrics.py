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
import crew_state
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
    result = _codex(repo, tmp_path, "fail")

    rows = _rows(repo)
    assert (result.returncode, len(rows), _cells(rows[0])[3:],
            crew_state.read_metrics(str(repo))["tickets"]) == (
        3, 1, ["INCOMPLETE", "INCOMPLETE"], 0), result.stdout + result.stderr


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

    result = _claude(repo, scratch, "--reserve-only")

    assert (result.stdout.strip(), _rows(repo)) == ("ROUND=1", []), result.stderr


def test_claude_recorded_round_writes_exactly_one_row(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only")
    (scratch / "out.txt").write_text("BLOCK: a.py:1 broken\n", encoding="utf-8")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    rows = _rows(repo)
    assert [(_cells(r)[1], _cells(r)[2].split(" (")[0]) for r in rows] == [("T1", "claude/default")]


def test_claude_round_after_a_codex_limit_is_labelled_same_family(repo, tmp_path):
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only")
    review_limit.record(str(repo), "T1", 0, "codex", "gpt-5.6-sol", "You've hit your usage limit.")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"))

    assert "same-family: codex limit" in _cells(_rows(repo)[0])[2]


def test_claude_round_with_an_older_codex_limit_is_not_labelled_codex_limit(repo, tmp_path):
    review_limit.record(str(repo), "T1", 5, "codex", "gpt-5.6-sol", "You've hit your usage limit.")
    scratch = tmp_path / "s"
    bundle(repo, scratch)
    _claude(repo, scratch, "--reserve-only")

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
    (frozenset({"gpt"}), "unknown", "different family unproven, author from unknown"),
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
    _claude(repo, scratch, "--reserve-only")

    _claude(repo, scratch, "--round", "1", "--output", str(scratch / "out.txt"),
            "--exit-code", "0", "--work-dir", str(tmp_path / "w"),
            "--note", "codex-probe=5")

    assert "(r1, std:none, same-family: codex limit, " in _rows(repo)[0]


@pytest.mark.parametrize("note", ["codex-probe=0", "codex-probe=6", "codex-probe=not-run", ""])
def test_a_claude_note_that_is_not_a_limit_is_not_labelled_one(monkeypatch, note):
    monkeypatch.setattr(review_metrics.crew_state, "author_families",
                        lambda root, cfg: (frozenset({"claude"}), "config"))
    monkeypatch.setattr(review_metrics, "_codex_limit_before", lambda *a: False)

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
                                 str(tmp_path / "manifest.json"))

    assert (line.startswith("review: metrics row NOT written (could not build it: "),
            os.path.exists(tmp_path / ".crew")) == (True, False)


def test_an_unresolvable_main_checkout_writes_nothing_and_quotes_the_row(monkeypatch, tmp_path):
    monkeypatch.setattr(review_metrics.crew_common, "_main_checkout",
                        lambda root: (None, "git could not name its main checkout"))
    monkeypatch.setattr(review_metrics, "family_tag", lambda *a, **k: "family unknown, author from unknown")

    line = review_metrics.record(str(tmp_path), "T1", 1, {"verdict": "CLEAN", "counts": {},
                                                          "provider": "codex"},
                                 str(tmp_path / "manifest.json"))

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
                                 str(tmp_path / "manifest.json"))

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
                                 str(tmp_path / "manifest.json"))

    assert ("\n" in line, "first line second line" in line) == (False, True)
