"""A round the TOOL lost is refunded; a round the reviewer or the tree lost is not.

An INCOMPLETE round is classed by `review_verdict.failure_class`: the answer
never arrived intact (timeout, unknown or non-zero exit, empty output, a failed
or unreadable Codex stream) is `tool`; a bundle/webtest reason is `tree`;
anything else -- output that arrived and broke the contract -- is `reviewer`.
Only `tool` is refunded, at most `review_ledger.REFUND_LIMIT` times per plan
(T-0087; the owner chose automatic refunds, 2026-09-28).
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_verdict as rv


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
