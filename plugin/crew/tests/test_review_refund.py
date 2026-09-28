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

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
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
