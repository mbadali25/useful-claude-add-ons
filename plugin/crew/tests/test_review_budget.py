"""L-0717: one review budget per ticket, counted across successor plans.

The budget is `review_ledger.BUDGET` (three rounds), a constant counted across
every plan the ticket ever ran under. A successor plan does not reopen it; the
owner's recorded `--grant-round` (one extra round per grant) is the one way
past it. These cases hold: the count, the grant verb and each of its refusals,
the malformed-`grants` ledgers (could not tell, never `BUDGET`), every printed
budget string following the ledger, and the documents stating the cap.

Every case builds a throwaway repository under tmp_path.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_status
import review_fixtures
import review_ledger as rl
import review_run
from review_fixtures import init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_LEDGER = os.path.join(_SCRIPTS, "review_ledger.py")
T = "T1"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def _cli(repo, *args):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", T, *args],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)


def _spend(repo, count=None):
    for _ in range(rl.BUDGET if count is None else count):
        rl.reserve(str(repo), T, "codex")


def _bytes(repo):
    with open(rl.ledger_path(str(repo), T), "rb") as handle:
        return handle.read()


def _write_ledger(repo, **extra):
    path = rl.ledger_path(str(repo), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rounds = [{"round": n, "status": "completed", "verdict": "FINDINGS"}
              for n in range(1, rl.BUDGET + 1)]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(dict({"state": "REVIEWED", "rounds": rounds}, **extra)))
    return path


def _grant(repo, by="the owner", reason="one more round"):
    return rl.grant_round(str(repo), T, by, reason)


# --- the count -----------------------------------------------------------------

def test_the_budget_is_three():
    assert rl.BUDGET == 3


def test_round_three_is_reachable_without_reject_or_successor(repo):
    for number in (1, 2, 3):
        ok, got, message = rl.reserve(str(repo), T, "codex")
        assert (ok, got) == (True, number), message
        if number < 3:
            rl.record(str(repo), T, number, {
                "verdict": "FINDINGS", "counts": {}, "bundle_sha256": "0" * 64, "base": "HEAD",
                "head": "HEAD", "provider": "codex", "model": None, "model_family": "gpt"})

    status = rl.status(str(repo), T)

    assert (status["rounds_left"], status["state"] != rl.NEEDS_REPLAN) == (0, True)


def test_a_legacy_successor_row_still_resets(repo):
    """A successor row written before L-0717 has no `carry_over` and keeps
    resetting the count at its `after_round`: the ledger is history."""
    _write_ledger(repo, successors=[{"after_round": rl.BUDGET, "plan_sha256": "a" * 64}])

    status = rl.status(str(repo), T)

    assert (status["rounds_spent"], status["rounds_left"]) == (0, rl.BUDGET)


def test_a_carry_over_successor_row_does_not_reset(repo):
    _write_ledger(repo, successors=[{"after_round": rl.BUDGET, "plan_sha256": "a" * 64,
                                     "carry_over": True}])

    status = rl.status(str(repo), T)

    assert (status["rounds_spent"], status["rounds_left"]) == (rl.BUDGET, 0)


def test_a_new_successor_after_a_legacy_one_counts_from_the_legacy_boundary(repo):
    rows = [{"round": n, "status": "completed", "verdict": "FINDINGS"} for n in range(1, 6)]
    path = _write_ledger(repo, successors=[
        {"after_round": 2, "plan_sha256": "a" * 64},
        {"after_round": 4, "plan_sha256": "b" * 64, "carry_over": True}])
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data["rounds"] = rows
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))

    status = rl.status(str(repo), T)

    assert (status["rounds_spent"], status["rounds_left"]) == (3, 0)


# --- the grant verb ---------------------------------------------------------------

def test_grant_round_adds_one_round_and_changes_nothing_else(repo):
    _spend(repo)
    before = rl.status(str(repo), T)

    row = _grant(repo)

    after = rl.status(str(repo), T)
    assert (after["budget"], after["rounds_left"], after["state"], after["rounds"],
            after["receipt"]) == (rl.BUDGET + 1, 1, before["state"], before["rounds"],
                                  before["receipt"])
    assert [(g["by"], g["reason"], g["round"]) for g in after["grants"]] == [
        ("the owner", "one more round", rl.BUDGET + 1)]
    assert set(row) >= {"at", "by", "reason", "round"}


def test_a_grant_never_reopens_needs_replan(repo):
    _spend(repo, rl.BUDGET + 1)
    _grant(repo)

    first = rl.reserve(str(repo), T, "codex")

    assert (first[0], rl.status(str(repo), T)["state"]) == (False, rl.NEEDS_REPLAN)


def test_a_grant_before_the_refusal_lets_the_next_reserve_run(repo):
    _spend(repo)
    _grant(repo)

    first = rl.reserve(str(repo), T, "codex")
    second = rl.reserve(str(repo), T, "codex")

    assert (first[:2], second[0]) == ((True, rl.BUDGET + 1), False)


def test_grant_round_is_refused_while_rounds_remain(repo):
    _spend(repo, rl.BUDGET - 1)
    before = _bytes(repo)

    with pytest.raises(rl.LedgerError, match="remain"):
        _grant(repo)

    assert _bytes(repo) == before


def test_grant_round_is_refused_on_a_fresh_ticket(repo):
    with pytest.raises(rl.LedgerError, match="absent"):
        _grant(repo)

    assert not os.path.exists(rl.ledger_path(str(repo), T))


@pytest.mark.parametrize("by", [
    "auto: policy", "AUTO:x", "ａｕｔｏ:x", "​auto:x", "  auto: x",
    crew_autopilot.AUTO_REJECT_BY, "Autopilot", "autopilot:self"])
def test_grant_round_refuses_an_automatic_name(repo, by):
    _spend(repo)
    before = _bytes(repo)

    with pytest.raises(rl.LedgerError, match="never an automatic"):
        _grant(repo, by=by)

    assert _bytes(repo) == before


def test_the_autopilot_reject_name_starts_with_the_refused_prefix():
    assert crew_autopilot.AUTO_REJECT_BY.casefold().startswith(rl.AUTOPILOT_NAME)


@pytest.mark.parametrize("by, reason", [
    ("", "why"), ("   ", "why"), (None, "why"), ("a\nb", "why"), ("a b", "why"),
    ("owner", ""), ("owner", "  "), ("owner", None), ("owner", "a\nb"), ("owner", "a\rb"),
    ("owner", "a\u0085b"), ("ow\udc80ner", "why"), ("owner", "wh\udc80y")])
def test_grant_round_refuses_a_missing_or_multi_line_name_or_reason(repo, by, reason):
    _spend(repo)
    before = _bytes(repo)

    with pytest.raises(rl.LedgerError):
        rl.grant_round(str(repo), T, by, reason)

    assert _bytes(repo) == before


def test_grant_round_refuses_an_unreadable_ledger(repo):
    path = rl.ledger_path(str(repo), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")

    with pytest.raises(rl.LedgerError, match="corrupt"):
        _grant(repo)

    assert _bytes(repo) == b"{not json"


def test_grant_round_cli_records_and_prints(repo):
    _spend(repo)

    done = _cli(repo, "--grant-round", "--by", "Matthew", "--reason", "owner pick 2026-10-26")

    assert (done.returncode, "budget now 4" in done.stdout) == (0, True), done.stderr
    assert rl.status(str(repo), T)["grants"][0]["by"] == "Matthew"


@pytest.mark.parametrize("extra", [[], ["--by", "Matthew"], ["--reason", "why"],
                                   ["--by", "auto: x", "--reason", "why"]])
def test_grant_round_cli_needs_both_a_by_and_a_reason(repo, extra):
    _spend(repo)
    before = _bytes(repo)

    done = _cli(repo, "--grant-round", *extra)

    assert (done.returncode != 0, _bytes(repo)) == (True, before)


def test_the_flag_cannot_be_abbreviated_on_the_ledger_cli(repo):
    _spend(repo)

    done = _cli(repo, "--g", "--by", "Matthew", "--reason", "why")

    assert (done.returncode, rl.status(str(repo), T)["grants"]) == (2, [])


# --- a malformed `grants` is could-not-tell, never BUDGET ---------------------------

_GOOD_ROW = {"at": "t", "by": "owner", "reason": "why", "round": 4}
_BAD_GRANTS = {
    "string": "none", "dict": {"by": "owner"}, "null": None, "number": 1,
    "row-not-object": ["owner"], "row-missing-by": [{"reason": "why", "round": 4}],
    "row-missing-reason": [{"by": "owner", "round": 4}],
    "row-empty-by": [dict(_GOOD_ROW, by="")], "row-blank-reason": [dict(_GOOD_ROW, reason="  ")],
    "row-by-not-string": [dict(_GOOD_ROW, by=7)],
    "row-round-bool": [dict(_GOOD_ROW, round=True)], "row-round-string": [dict(_GOOD_ROW, round="4")],
    "row-round-missing": [{"by": "owner", "reason": "why"}],
    "one-good-one-bad": [_GOOD_ROW, "x"],
}


@pytest.mark.parametrize("grants", list(_BAD_GRANTS.values()), ids=list(_BAD_GRANTS))
def test_a_malformed_grants_value_makes_the_ledger_unreadable(repo, grants):
    path = _write_ledger(repo, grants=grants)
    with open(path, "rb") as handle:
        before = handle.read()

    reserved = rl.reserve(str(repo), T, "codex")
    status = rl.status(str(repo), T)

    assert (reserved[:2], "UNKNOWN" in reserved[2], status["state"], "rounds_left" in status) == (
        (False, None), True, rl.UNKNOWN, False)
    with pytest.raises(rl.LedgerError):
        _grant(repo)
    with open(path, "rb") as handle:
        assert handle.read() == before


def test_a_well_formed_grants_list_still_reads(repo):
    _write_ledger(repo, grants=[_GOOD_ROW])

    status = rl.status(str(repo), T)

    assert (status["budget"], status["rounds_left"]) == (rl.BUDGET + 1, 1)


# --- every printed budget string follows the ledger -----------------------------------

def _run_round(repo, tmp_path, name):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / f"s-{name}", tmp_path / f"w-{name}"
    review_fixtures.bundle(repo, scratch)
    fakes = review_fixtures.fake_reviewer_bin(tmp_path / f"b-{name}")
    return review_fixtures.run_review(repo, scratch, fakes, "findings", "--work-dir", str(work))


def _printed(repo, tmp_path, name):
    """Every place a budget number is printed: `--status`, the review_run
    round lines, `/crew:status`, the ledger's reserve message."""
    status = _cli(repo, "--status")
    run = _run_round(repo, tmp_path, name)
    lines = "\n".join(crew_status._review_lines(str(repo)))  # pylint: disable=protected-access
    return status.stdout + "\n" + run.stdout + run.stderr + "\n" + lines


def test_every_printed_budget_string_follows_the_ledger(repo, tmp_path):
    fresh = _printed(repo, tmp_path, "fresh")

    assert ("of 3" in fresh, "/3 rounds used" in fresh, '"budget": 3' in fresh) == (
        True, True, True)
    assert not re.search(r"\bof 2\b|/2 rounds|\"budget\": 2", fresh), fresh


def test_every_printed_budget_string_follows_a_grant(repo, tmp_path):
    _spend(repo)
    _grant(repo)

    granted = _printed(repo, tmp_path, "granted")

    assert ("of 4" in granted, "/4 rounds used" in granted, '"budget": 4' in granted) == (
        True, True, True)
    assert not re.search(r"\bof 3\b|/3 rounds|\"budget\": 3", granted), granted


def test_the_final_round_text_is_round_number_free(repo):
    refused = " ".join(str(text) for text in review_run.NEXT_CODES.values())
    _spend(repo, rl.BUDGET + 1)

    message = rl.reserve(str(repo), T, "codex")[2]

    assert not re.search(r"\bthird\b|\btwo\b|\bof 2\b", refused + " " + message), refused + message
    assert "--grant-round" in message and "--grant-round" in review_run.NEXT_CODES[
        review_run.EXIT_REFUSED]


def test_the_refund_limit_is_twice_the_budget_at_most():
    assert rl.BUDGET + rl.REFUND_LIMIT <= 2 * rl.BUDGET


# --- the documents state the ledger's budget --------------------------------------

_REPO = os.path.dirname(os.path.dirname(context._ROOT))  # pylint: disable=protected-access
_GUIDES = "docs/guides/crew/src/"
_DOCS = (
    "plugin/crew/commands/review.md", "plugin/crew/README.md", "docs/crew/review.md",
    "docs/crew/reference/10-the-daily-loop.md",
    "plugin/crew/skills/crew-qa-standards/references/review.md",
    _GUIDES + "guide.md", _GUIDES + "quickstart.md", _GUIDES + "troubleshooting.md",
    _GUIDES + "daily-workflow.md", _GUIDES + "daily-workflow-scope.md", _GUIDES + "autopilot.md")
_MARKER = "<!-- review-budget-doc -->"
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
_STALE = re.compile(
    r"two rounds|two-round|two fresh|budget of two|fresh budget|\bof 2\b|crew: 2|"
    r"round 2 is the last|no third round|third round", re.IGNORECASE)


def _read(rel):
    with open(os.path.join(_REPO, *rel.split("/")), encoding="utf-8") as handle:
        return handle.read().splitlines()


@pytest.mark.parametrize("rel", _DOCS)
def test_docs_state_the_ledger_budget(rel):
    word = _WORDS[rl.BUDGET]
    lines = _read(rel)
    marked = [i for i, line in enumerate(lines) if _MARKER in line]

    stated = [i for i in marked
              if any(re.search(rf"\b{word}\b", text, re.IGNORECASE) for text in lines[i:i + 13])]

    assert marked, f"{rel} states no review-budget number (no {_MARKER} marker)"
    assert stated == marked, f"{rel}: a marker at line(s) {[i + 1 for i in marked if i not in stated]} has no '{word}' within 12 lines"


@pytest.mark.parametrize("rel", _DOCS + (_GUIDES + "working-with-codex.md",))
def test_docs_carry_no_stale_budget_phrase(rel):
    stale = [(n, line.strip()[:100]) for n, line in enumerate(_read(rel), 1) if _STALE.search(line)]

    assert stale == [], f"{rel} still states the old budget: {stale}"


@pytest.mark.parametrize("rel", [_GUIDES + "guide.md", _GUIDES + "troubleshooting.md",
                                 _GUIDES + "daily-workflow-scope.md",
                                 "docs/crew/reference/10-the-daily-loop.md"])
def test_the_successor_plan_paragraphs_name_the_grant(rel):
    text = "\n".join(_read(rel))

    assert "--grant-round" in text and "does not reopen the budget" in text.replace("\n", " ")
