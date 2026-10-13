"""A round the TOOL lost is refunded; a round the reviewer or the tree lost is not.

An INCOMPLETE round is classed by `review_verdict.failure_class`: the answer
never arrived intact (timeout, unknown or non-zero exit, empty output, a failed
or unreadable Codex stream) is `tool`; a bundle/webtest reason is `tree`;
anything else -- output that arrived and broke the contract -- is `reviewer`.
Only `tool` is refunded, at most `review_ledger.REFUND_LIMIT` times per plan
(T-0087; the owner chose automatic refunds, 2026-09-28).
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import review_fixtures
import review_ledger as rl
import review_verdict as rv
from review_fixtures import init_repo
from scope_fixtures import make_repo, ready


@pytest.mark.parametrize("text, exit_code, timed_out, delivered", [
    ("CLEAN\n", 0, False, True),
    ("CLEAN\n", 0, True, False),
    ("CLEAN\n", None, False, False),
    ("CLEAN\n", 1, False, False),
    ("  \n", 0, False, False),
    ("prose\n", 0, False, True),
])
def test_parse_reports_whether_the_answer_was_delivered(text, exit_code, timed_out, delivered):
    assert rv.parse(text, exit_code, timed_out)["delivered"] is delivered


@pytest.mark.parametrize("verdict, delivered, tree, expected", [
    ("INCOMPLETE", False, True, "tree"),
    ("INCOMPLETE", True, True, "tree"),
    ("INCOMPLETE", False, False, "tool"),
    ("INCOMPLETE", True, False, "reviewer"),
    ("FINDINGS", False, True, None),
    ("CLEAN", True, False, None),
])
def test_failure_class_precedence(verdict, delivered, tree, expected):
    assert rv.failure_class(verdict, delivered, tree) == expected


def test_verdict_and_codex_vocabularies_are_declared():
    assert rv.VERDICTS == ("CLEAN", "FINDINGS", "INCOMPLETE")
    assert (rv.TOOL, rv.REVIEWER, rv.TREE) == ("tool", "reviewer", "tree")
    assert "turn.failed" in rv.CODEX_EVENT_TYPES
    assert "agent_message" in rv.CODEX_ITEM_TYPES
    assert rv.FINDING_FORM == "SEVERITY|file:line|what breaks|how to reproduce"


# --- Step 2: the ledger refunds a tool-failure round, up to REFUND_LIMIT per plan ----

def _review(verdict, failure_class=None, provider="codex", bundle="b" * 64, base="c" * 40):
    """The minimal review.json dict `review_ledger.record` reads."""
    return {"verdict": verdict, "counts": {"BLOCK": 0, "FIX": 0, "NIT": 0},
            "bundle_sha256": bundle, "base": base, "head": base, "model_family": "gpt",
            "provider": provider, "model": None, "failure_class": failure_class}


def _round(root, ticket, verdict, failure_class=None, **kw):
    ok, number, message = rl.reserve(str(root), ticket, "codex")
    assert ok, message
    rl.record(str(root), ticket, number, _review(verdict, failure_class, **kw))
    return number


def _rows(root, ticket="T1"):
    return rl.status(str(root), ticket)["rounds"]


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def test_ledger_refunds_a_tool_failure_round(repo):
    _round(repo, "T1", "INCOMPLETE", "tool")

    status = rl.status(str(repo), "T1")
    row = status["rounds"][0]
    assert (row["refunded"], row["failure_class"]) == (True, "tool")
    assert (status["rounds_left"], status["rounds_spent"], status["rounds_refunded"],
            status["rounds_used"]) == (2, 0, 1, 1)


@pytest.mark.parametrize("failure", ["reviewer", "tree", None])
def test_ledger_does_not_refund_a_reviewer_or_tree_round(repo, failure):
    _round(repo, "T1", "INCOMPLETE", failure)

    status = rl.status(str(repo), "T1")
    assert (status["rounds"][0]["refunded"], status["rounds_left"]) == (False, 1)


def test_refunded_rounds_do_not_exhaust_the_budget(repo):
    _round(repo, "T1", "INCOMPLETE", "tool")
    _round(repo, "T1", "INCOMPLETE", "tool")

    ok, number, message = rl.reserve(str(repo), "T1", "codex")

    assert (ok, number, rl.status(str(repo), "T1")["state"]) == (True, 3, rl.IN_REVIEW), message


def test_refund_limit_is_two_per_plan(repo):
    for _ in range(3):
        _round(repo, "T1", "INCOMPLETE", "tool")

    rows = _rows(repo)
    assert [r["refunded"] for r in rows] == [True, True, False]
    assert "refund limit 2" in rows[2]["refund_refused"]
    assert rl.status(str(repo), "T1")["rounds_left"] == 1


def test_budget_still_refuses_after_refunds(repo):
    _round(repo, "T1", "INCOMPLETE", "tool")
    _round(repo, "T1", "INCOMPLETE", "tool")
    _round(repo, "T1", "FINDINGS")
    _round(repo, "T1", "FINDINGS")

    ok, number, _ = rl.reserve(str(repo), "T1", "codex")

    assert (ok, number, rl.status(str(repo), "T1")["state"]) == (False, None, rl.NEEDS_REPLAN)


def test_legacy_rows_without_failure_class_count_as_spent(repo):
    path = rl.ledger_path(str(repo), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": "T1", "budget": 2, "state": "REVIEWED", "refused": [],
                   "receipt": None,
                   "rounds": [{"round": 1, "status": "completed", "verdict": "INCOMPLETE",
                               "provider": "codex", "model": None}]}, fh)

    status = rl.status(str(repo), "T1")

    assert (status["rounds_left"], status["rounds_refunded"]) == (1, 0)


# Successor-plan cases: a ticket with an approved plan, as test_crew_ticket.py builds it.

def _plan(repo, text):
    (repo / ".work" / "tickets" / "T-1" / "plan.md").write_text(text, encoding="utf-8")


def _successor(repo, n):
    _plan(repo, f"## Step 1\nFiles: src/app.py\nTest: new {n}\nRisk: new\n")
    crew_ticket.approve(str(repo), "T-1", by="owner", via=crew_ticket.USER_PROMPT)
    assert rl.status(str(repo), "T-1")["state"] == rl.IN_REVIEW


@pytest.fixture(name="ticket_repo")
def _ticket_repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    ready(root)
    return root


def test_refunds_reset_with_a_successor_plan(ticket_repo):
    repo = ticket_repo
    for verdict, failure in (("INCOMPLETE", "tool"), ("INCOMPLETE", "tool"),
                             ("FINDINGS", None), ("FINDINGS", None)):
        _round(repo, "T-1", verdict, failure)
    assert rl.reserve(str(repo), "T-1", "codex")[0] is False
    assert rl.status(str(repo), "T-1")["state"] == rl.NEEDS_REPLAN
    _successor(repo, 2)

    _round(repo, "T-1", "INCOMPLETE", "tool")
    _round(repo, "T-1", "INCOMPLETE", "tool")

    assert [r["refunded"] for r in _rows(repo, "T-1")[4:]] == [True, True]


def test_record_after_a_refund_still_refuses_a_round_from_a_replaced_plan(ticket_repo):
    repo = ticket_repo
    _round(repo, "T-1", "INCOMPLETE", "tool")
    assert rl.reserve(str(repo), "T-1", "codex")[:2] == (True, 2)
    rl.reject(str(repo), "T-1", "owner")
    _successor(repo, 2)

    with pytest.raises(rl.LedgerError, match="a successor replaced"):
        rl.record(str(repo), "T-1", 2, _review("CLEAN"))


def test_accept_after_a_refund_still_refuses_a_round_from_a_replaced_plan(ticket_repo):
    repo = ticket_repo
    _round(repo, "T-1", "INCOMPLETE", "tool")
    _round(repo, "T-1", "FINDINGS")
    rl.reject(str(repo), "T-1", "owner")
    _successor(repo, 2)

    with pytest.raises(rl.LedgerError, match="a successor replaced"):
        rl.accept(str(repo), "T-1", "owner")


# --- Step 3: review_run records the class and the refund, end to end ------------

def _run(repo, tmp_path, mode, *extra):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    review_fixtures.bundle(repo, scratch)
    fakes = review_fixtures.fake_reviewer_bin(tmp_path / "bin")
    result = review_fixtures.run_review(repo, scratch, fakes, mode, "--work-dir", str(work),
                                        *extra)
    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    return result, review


def _assert_refunded_tool_failure(repo, result, review):
    """Round 1 is refunded. A timeout ends there; any other tool failure is
    retried once (L-0514), and the retry fails the same way and is refunded too."""
    status = rl.status(str(repo), "T1")
    assert result.returncode == 3, result.stdout + result.stderr
    assert (review["failure_class"], review["refunded"]) == ("tool", True)
    assert (_rows(repo)[0]["failure_class"], _rows(repo)[0]["refunded"]) == ("tool", True)
    assert (status["rounds_left"], status["rounds_refunded"]) == (2, len(_rows(repo)))
    assert any(ln.startswith("review: round 1 was a tool failure") and "refunded" in ln
               for ln in result.stdout.splitlines()), result.stdout


def test_turn_failed_round_is_refunded(repo, tmp_path):
    _assert_refunded_tool_failure(repo, *_run(repo, tmp_path, "turnfail"))


def test_timed_out_round_is_refunded(repo, tmp_path):
    _assert_refunded_tool_failure(repo, *_run(repo, tmp_path, "hang", "--timeout", "2"))


def test_nonzero_exit_round_is_refunded(repo, tmp_path):
    _assert_refunded_tool_failure(repo, *_run(repo, tmp_path, "fail"))


def test_contract_broken_round_is_not_refunded(repo, tmp_path):
    result, review = _run(repo, tmp_path, "prose")

    assert result.returncode == 3, result.stdout + result.stderr
    assert (review["failure_class"], review["refunded"]) == ("reviewer", False)
    assert rl.status(str(repo), "T1")["rounds_left"] == 1


def test_tree_changed_round_is_not_refunded(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    review_fixtures.bundle(repo, scratch)
    first = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"][0]
    with open(first["path"], "ab") as fh:
        fh.write(b"x")
    fakes = review_fixtures.fake_reviewer_bin(tmp_path / "bin")

    result = review_fixtures.run_review(repo, scratch, fakes, "clean", "--work-dir", str(work))

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    assert result.returncode == 3, result.stdout + result.stderr
    assert (review["failure_class"], review["refunded"]) == ("tree", False)
    assert rl.status(str(repo), "T1")["rounds_left"] == 1


@pytest.mark.parametrize("mode", ["clean", "findings"])
def test_clean_and_findings_rounds_carry_no_failure_class(repo, tmp_path, mode):
    _, review = _run(repo, tmp_path, mode)

    assert (review["failure_class"], review["refunded"]) == (None, False)


def _finish_claude(repo, tmp_path, body, before=None, exit_code="0"):
    """Reserve a claude round and record `body` (after a READ line per part)
    through the subagent path, as /crew:review step 2c does."""
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    review_fixtures.bundle(repo, scratch)
    parts = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['path']}\n" for p in parts) + body, encoding="utf-8")
    if before:
        before(parts)
    common = [sys.executable, os.path.join(os.path.dirname(rv.__file__), "review_run.py"),
              "--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
              "--provider", "claude"]
    subprocess.run(common + ["--reserve-only", "--authors", "gpt"], capture_output=True,
                   stdin=subprocess.DEVNULL, check=True, timeout=120)
    result = subprocess.run(common + ["--round", "1", "--output", str(scratch / "out.txt"),
                                      "--exit-code", exit_code, "--work-dir", str(work)],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL,
                            check=False, timeout=120)
    return result, json.loads((work / "review.json").read_text(encoding="utf-8"))


def test_finish_reports_ignored_lines(repo, tmp_path):
    """L-0576: a FINDINGS round recovered despite a stray prose line keeps
    that line in review.json and names it on a `review:` line."""
    prose = "The sabotage entries need --run-slow; sabotage.py passes it."

    result, review = _finish_claude(repo, tmp_path, f"FIX|a.py:1|breaks|run it\n{prose}\n")

    kept = [ln for ln in result.stdout.splitlines() if ln.startswith("review: FINDINGS kept; 1 ")]
    assert (result.returncode, review["verdict"], review["ignored_lines"], review["ignored_text"],
            review["failure_class"], len(kept)) == (1, "FINDINGS", 1, [prose], None, 1), (
        result.stdout + result.stderr)


def test_ledger_row_counts_the_ignored_lines(repo, tmp_path):
    _finish_claude(repo, tmp_path, "FIX|a.py:1|breaks|run it\nA closing remark.\n")

    assert rl.status(str(repo), "T1")["rounds"][-1]["ignored_lines"] == 1


_MISSING = object()


@pytest.mark.parametrize("value", [_MISSING, None, "3", 2.0, True, False, -1, [], ["x"]],
                         ids=["missing", "null", "str", "float", "true", "false", "negative",
                              "empty-list", "list"])
def test_ledger_row_records_an_unknown_ignored_count_as_null_never_0(repo, value):
    """L-0510 lane: unknown never becomes 0. A review.json whose `ignored_lines`
    is missing or not a non-negative int leaves the ledger row's count null."""
    ok, number, message = rl.reserve(str(repo), "T1", "codex")
    assert ok, message
    review = _review("FINDINGS")
    if value is not _MISSING:
        review["ignored_lines"] = value

    rl.record(str(repo), "T1", number, review)

    assert _rows(repo)[-1]["ignored_lines"] is None


@pytest.mark.parametrize("value", [0, 1, 7])
def test_ledger_row_keeps_a_valid_ignored_count(repo, value):
    ok, number, message = rl.reserve(str(repo), "T1", "codex")
    assert ok, message

    rl.record(str(repo), "T1", number, dict(_review("FINDINGS"), ignored_lines=value))

    assert _rows(repo)[-1]["ignored_lines"] == value


def test_finish_recovers_nothing_when_the_bundle_changed(repo, tmp_path):
    """A tree reason found by `finish` itself rules recovery out: the round is
    INCOMPLETE, the stray line is a reason, and nothing says FINDINGS kept."""
    def damage(parts):
        with open(parts[0]["path"], "ab") as fh:
            fh.write(b"x")

    result, review = _finish_claude(repo, tmp_path, "FIX|a.py:1|breaks|run it\nA remark.\n",
                                    before=damage)

    assert (result.returncode, review["verdict"], review["failure_class"],
            review["ignored_lines"], review["ignored_text"], " kept; " in result.stdout,
            any("match no part of the contract" in r for r in review["reasons"])) == (
        3, "INCOMPLETE", "tree", 0, [], False, True), result.stdout + result.stderr


def test_finish_records_no_ignored_lines_on_a_strict_round(repo, tmp_path):
    result, review = _finish_claude(repo, tmp_path, "FIX|a.py:1|breaks|run it\n")

    assert (result.returncode, review["ignored_lines"], review["ignored_text"],
            " kept; " in result.stdout) == (1, 0, [], False), result.stdout + result.stderr
    assert isinstance(review["ignored_lines"], int) and not isinstance(
        review["ignored_lines"], bool)  # L-0510 reads it as an int


def test_refund_limit_holds_through_review_run(repo, tmp_path):
    """Two invocations: the first's round and its retry take both refunds, so
    the second's round is NOT refunded, counts, and is not retried."""
    outs = []
    for n in range(2):
        result, _ = _run(repo, tmp_path / str(n), "turnfail")
        outs.append(result.stdout)

    assert "NOT refunded" in outs[1], outs[1]
    assert (len(_rows(repo)), rl.status(str(repo), "T1")["rounds_left"]) == (3, 1)


def test_summary_line_after_refunds_is_never_over_budget(repo, tmp_path):
    _run(repo, tmp_path / "0", "turnfail")  # round 1 and its retry, both refunded

    result, _ = _run(repo, tmp_path / "2", "findings")

    first = result.stdout.splitlines()[0]
    assert (first.startswith("review: FINDINGS round 3, 1 of 2 budget rounds used, "
                             "2 refunded ("), "3/2" in result.stdout) == (True, False), first


# --- L-0514: a refunded tool round is retried once, in-process -----------------------

def _retry_lines(result):
    return [ln for ln in result.stdout.splitlines() if ln.startswith("review: retry:")]


def _calls(tmp_path):
    state = tmp_path / "bin" / "calls.txt"
    return int(state.read_text(encoding="utf-8")) if state.exists() else 0


def _not_retried(repo, tmp_path, result, rounds, why):
    """Nothing reserved after the last round; one not-retried line naming
    `why`, then the options line; exit 3."""
    lines = _retry_lines(result)
    refusals = [ln for ln in lines if ln.startswith("review: retry: not retried - ")]
    assert (result.returncode, len(_rows(repo)), len(refusals),
            lines and lines[-1].startswith("review: retry: not retried - ")
            and why in lines[-1],
            "review: options: " in result.stdout) == (3, rounds, 1, True, True), (
        result.stdout + result.stderr)
    return lines


def test_refunded_tool_round_retries_once_and_clean_wins(repo, tmp_path):
    result, review = _run(repo, tmp_path, "turnfail,clean")

    rows = _rows(repo)
    assert (result.returncode, [(r["verdict"], r["refunded"]) for r in rows],
            _retry_lines(result), review["round"], review["verdict"], _calls(tmp_path)) == (
        0, [("INCOMPLETE", True), ("CLEAN", False)],
        ["review: retry: round 1 was a tool failure; retrying once"], 2, "CLEAN", 2), (
        result.stdout + result.stderr)
    first = json.loads((tmp_path / "work" / "review.json.round1").read_text(encoding="utf-8"))
    assert review["prereview"] == dict(first["prereview"], round=2)


def test_retry_limit_is_one_per_invocation(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "turnfail,turnfail")

    lines = _not_retried(repo, tmp_path, result, 2, "retry limit 1 per invocation")
    assert (lines[0], _calls(tmp_path)) == (
        "review: retry: round 1 was a tool failure; retrying once", 2)


def test_no_retry_for_reviewer_class(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "prose,clean")

    _not_retried(repo, tmp_path, result, 1, "round 1 is a reviewer INCOMPLETE")


def test_no_retry_for_tree_class(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    review_fixtures.bundle(repo, scratch)
    first = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"][0]
    with open(first["path"], "ab") as fh:
        fh.write(b"x")
    fakes = review_fixtures.fake_reviewer_bin(tmp_path / "bin")

    result = review_fixtures.run_review(repo, scratch, fakes, "clean", "--work-dir", str(work))

    _not_retried(repo, tmp_path, result, 1, "round 1 is a tree INCOMPLETE")


def test_no_retry_when_refund_refused(repo, tmp_path):
    for _ in range(rl.REFUND_LIMIT):
        _round(repo, "T1", "INCOMPLETE", "tool")

    result, _ = _run(repo, tmp_path, "turnfail,clean")

    _not_retried(repo, tmp_path, result, rl.REFUND_LIMIT + 1,
                 f"refund was refused (refund limit {rl.REFUND_LIMIT} per plan reached)")
    assert _calls(tmp_path) == 1


def test_no_retry_on_usage_limit(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "limit,clean")

    _not_retried(repo, tmp_path, result, 1, "a usage limit is not retried")
    assert "review: codex usage limit in round 1: " in result.stdout, result.stdout


def test_no_retry_on_timeout(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "hang", "--timeout", "2")

    _not_retried(repo, tmp_path, result, 1, "round 1 timed out")


@pytest.mark.parametrize("mode, code", [("clean", 0), ("findings", 1)])
def test_clean_and_findings_rounds_are_not_retried(repo, tmp_path, mode, code):
    result, _ = _run(repo, tmp_path, mode)

    assert (result.returncode, len(_rows(repo)), _retry_lines(result),
            "review: options:" in result.stdout) == (code, 1, [], False), result.stdout


def test_failed_round_files_are_kept(repo, tmp_path):
    result, review = _run(repo, tmp_path, "turnfail,clean")

    scratch, work = tmp_path / "scratch", tmp_path / "work"
    kept = json.loads((work / "review.json.round1").read_text(encoding="utf-8"))
    assert (result.returncode, review["round"], kept["round"], kept["failure_class"],
            "turn.failed" in (scratch / "codex-events.jsonl.round1").read_text(encoding="utf-8"),
            "turn.failed" in (scratch / "codex-events.jsonl").read_text(encoding="utf-8"),
            (scratch / "out.txt.round1").exists(), (scratch / "stderr.txt.round1").exists()) == (
        0, 2, 1, "tool", True, False, True, True), result.stdout + result.stderr


def test_claude_fallback_never_retries_in_process(repo, tmp_path):
    """Step 2c records a round in two calls; a subagent that failed (non-zero
    exit) is a refunded tool round, and the second call still ends there."""
    result, review = _finish_claude(repo, tmp_path, "", exit_code="1")

    assert (result.returncode, review["failure_class"], review["refunded"], len(_rows(repo)),
            _retry_lines(result)) == (3, "tool", True, 1, []), result.stdout + result.stderr


def _in_process(repo, tmp_path, monkeypatch, mode, sleep):
    """review_run.main in this process, so its sleep and reserve can be seen."""
    import review_run  # pylint: disable=import-outside-toplevel
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    review_fixtures.bundle(repo, scratch)
    fakes = review_fixtures.fake_reviewer_bin(tmp_path / "bin")
    for key, value in review_fixtures.env_with_path(
            fakes, FAKE_REVIEWER_MODE=mode,
            FAKE_REVIEWER_STATE=str(fakes / "calls.txt")).items():
        monkeypatch.setenv(key, value)
    events = []
    real_reserve = review_run.review_ledger.reserve

    def reserve(*args, **kwargs):
        events.append("reserve")
        return real_reserve(*args, **kwargs)

    real_sleep = review_run.time.sleep

    def fake_sleep(seconds):
        # `time` is one module: only the backoff is the retry's; a poll loop's
        # short waits (the standards gate's tools, asked again) really wait.
        if seconds != review_run.RETRY_BACKOFF_SECONDS:
            real_sleep(seconds)
            return
        events.append(("sleep", seconds))
        sleep(scratch)

    monkeypatch.setattr(review_run.review_ledger, "reserve", reserve)
    monkeypatch.setattr(review_run.time, "sleep", fake_sleep)
    code = review_run.main(["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
                            "--provider", "codex", "--work-dir", str(work)])
    return code, events


def test_backoff_precedes_the_retry_reservation(repo, tmp_path, monkeypatch, capsys):
    import review_run  # pylint: disable=import-outside-toplevel
    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean", lambda _: None)

    assert (code, events) == (0, ["reserve", ("sleep", review_run.RETRY_BACKOFF_SECONDS),
                                  "reserve"]), capsys.readouterr()


def test_no_retry_when_tree_changed(repo, tmp_path, monkeypatch, capsys):
    def damage(scratch):
        part = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"][0]
        with open(part["path"], "ab") as fh:
            fh.write(b"x")

    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean", damage)

    out = capsys.readouterr().out
    assert (code, events.count("reserve"), len(_rows(repo)),
            "review: retry: not retried - the tree changed: " in out,
            "review: options: " in out) == (3, 1, 1, True, True), out


def test_no_retry_when_the_gate_changed(repo, tmp_path, monkeypatch, capsys):
    """`preflight` is asked again after the backoff: a gate that no longer
    accepts the tree stops the retry before anything is reserved."""
    import review_gate  # pylint: disable=import-outside-toplevel
    real = review_gate.accepted_state
    moved = []
    monkeypatch.setattr(review_gate, "accepted_state", lambda root: (
        (review_gate.UNVERIFIED, "the tree moved") if moved else real(root)))

    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean",
                               lambda _: moved.append(True))

    captured = capsys.readouterr()
    assert (code, events.count("reserve"), len(_rows(repo)),
            "review: retry: not retried - the gate or the review receipt changed" in captured.out,
            "gate UNVERIFIED: the tree moved" in captured.err) == (3, 1, 1, True, True), (
        captured.out + captured.err)


def test_no_retry_when_the_self_check_went_stale(repo, tmp_path, monkeypatch, capsys):
    """Group review of #540: the standards self-check is asked again after
    the backoff; one that went stale (it lives under .work/, outside the
    bundle and the gate) stops the retry before anything is reserved."""
    import review_run  # pylint: disable=import-outside-toplevel
    real = review_run.crew_standards.review_gate
    moved = []
    monkeypatch.setattr(review_run.crew_standards, "review_gate", lambda *a: (
        (["the self-check is stale"], None) if moved else real(*a)))

    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean",
                               lambda _: moved.append(True))

    captured = capsys.readouterr()
    assert (code, events.count("reserve"), len(_rows(repo)),
            "review: retry: not retried - the standards self-check no longer passes"
            in captured.out,
            "self-check: the self-check is stale" in captured.err) == (3, 1, 1, True, True), (
        captured.out + captured.err)


def test_no_retry_when_a_source_file_changed(repo, tmp_path, monkeypatch, capsys):
    """L-0514 review: the saved parts still match their manifest when a SOURCE
    file moves during the backoff; the bundle is rebuilt from the tree, so the
    retry never reviews the old patch."""
    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean",
                               lambda _: (repo / "change.txt").write_text(
                                   "changed during the backoff\n", encoding="utf-8"))

    out = capsys.readouterr().out
    assert (code, events.count("reserve"), len(_rows(repo)),
            "review: retry: not retried - the tree changed: it now builds bundle" in out) == (
        3, 1, 1, True), out


def test_a_retry_whose_preflight_read_a_spent_budget_never_reserves_gated(
        repo, tmp_path, monkeypatch, capsys):
    """H1 group review r4 (must-block): the retry's preflight reads the
    budget as spent, so it skips the merge train; the ledger, read again
    under the reservation's lock, is not spent. The retry must reserve on
    preflight's decision (ungated), so the lock refuses it (GATE_CHANGED) and
    no second round starts without the train."""
    import review_run  # pylint: disable=import-outside-toplevel
    spent = []
    real = review_run._budget_spent  # pylint: disable=protected-access
    monkeypatch.setattr(review_run, "_budget_spent", lambda args: bool(spent) or real(args))

    code, events = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean",
                               lambda _: spent.append(True))

    captured = capsys.readouterr()
    assert (code, events.count("reserve"), len(_rows(repo)),
            "review: retry: not retried - the ledger refused the retry's reservation"
            in captured.out, rl.GATE_CHANGED in captured.err) == (3, 2, 1, True, True), (
        captured.out + captured.err)


def test_a_refused_retry_keeps_review_json_canonical(repo, tmp_path, monkeypatch, capsys):
    """L-0514 review: the failed round's review.json is moved aside only once
    the retry holds a round; a refused reservation leaves it in place."""
    import review_run  # pylint: disable=import-outside-toplevel
    real = review_run.review_ledger.reserve
    calls = []

    def refuse_the_second(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs) if len(calls) == 1 else (False, None, "refused")

    monkeypatch.setattr(review_run.review_ledger, "reserve", refuse_the_second)
    code, _ = _in_process(repo, tmp_path, monkeypatch, "turnfail,clean", lambda _: None)

    out = capsys.readouterr().out
    review = json.loads((tmp_path / "work" / "review.json").read_text(encoding="utf-8"))
    assert (code, review["round"], (tmp_path / "work" / "review.json.round1").exists(),
            "the ledger refused the retry's reservation" in out) == (3, 1, False, True), out
