"""L-0717 mutations: one review budget of three per ticket, counted across
successor plans, and the owner-only `--grant-round`. Same tuple shape as
`sabotage.py`'s MUTATIONS -- (label, target, find, replace, test) -- appended
to it there; `sabotage.py` sits at `.pylintrc`'s max-module-lines, so this list
lives apart. Run `sabotage.py`, not this file.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
LEDGER = os.path.join(_S, "review_ledger.py")
GUARD = os.path.join(_S, "scope_guard.py")
AUTOPILOT = os.path.join(_S, "crew_autopilot.py")

_B = "tests/test_review_budget.py::"
_L = "tests/test_review_ledger.py::"
_T = "tests/test_crew_ticket.py::"
_R = "tests/test_review_refund.py::"
_W = "tests/test_scope_guard_wave.py::"
_P = "tests/test_crew_autopilot_replan.py::"

_GRANT_BRANCH = 'r"|g(?:r(?:a(?:n(?:t(?:-(?:r(?:o(?:u(?:nd?)?)?)?)?)?)?)?)?)?)(?![\\w-])",\n'

BUDGET_MUTATIONS = (
    ("the review budget is lowered to two rounds again", LEDGER,
     "BUDGET = 3\n", "BUDGET = 2\n",
     _B + "test_round_three_is_reachable_without_reject_or_successor"),
    ("the review budget is raised to four rounds", LEDGER,
     "BUDGET = 3\n", "BUDGET = 4\n",
     _L + "test_reserve_fourth_round_is_refused_and_state_is_needs_replan"),
    ("the charged count restarts at the latest successor plan again", LEDGER,
     '    return len(data.get("rounds", [])) - _count_start(data) - _refunded(data)\n',
     '    return _spent(data) - _refunded(data)\n',
     _T + "test_a_successor_gets_the_rounds_the_ticket_has_left_and_no_more"),
    ("the refund count restarts at the latest successor plan again", LEDGER,
     '    return sum(1 for r in data.get("rounds", [])[_count_start(data):]\n',
     '    return sum(1 for r in data.get("rounds", [])[_boundary(data):]\n',
     _R + "test_refunds_are_ticket_wide_across_a_successor"),
    ("a legacy successor row no longer resets the count", LEDGER,
     '        if row.get("carry_over") is not True:\n',
     '        if False:\n',
     _B + "test_a_legacy_successor_row_still_resets"),
    ("a grant does not raise the allowance", LEDGER,
     '    return BUDGET + len(data.get("grants") or [])\n', '    return BUDGET\n',
     _B + "test_a_grant_before_the_refusal_lets_the_next_reserve_run"),
    ("--grant-round accepts an automatic name", LEDGER,
     '    if folded.startswith(AUTO_PREFIX) or folded.startswith(AUTOPILOT_NAME):\n',
     '    if False:\n',
     _B + "test_grant_round_refuses_an_automatic_name"),
    ("--grant-round is allowed while rounds remain", LEDGER,
     '        if left > 0:\n            raise LedgerError(f"{left} review round(s) remain',
     '        if False:\n            raise LedgerError(f"{left} review round(s) remain',
     _B + "test_grant_round_is_refused_while_rounds_remain"),
    ("a malformed grants list reads as the plain budget", LEDGER,
     '    if not isinstance(grants, list):\n        return False\n',
     '    return True\n',
     _B + "test_a_malformed_grants_value_makes_the_ledger_unreadable"),
    ("a successor plan with no round left is still recorded", LEDGER,
     '        if left < 1:\n', '        if False:\n',
     _T + "test_a_successor_plan_does_not_reopen_the_budget"),
    ("the scope guard lets a subagent run --grant-round", GUARD,
     _GRANT_BRANCH, 'r")(?![\\w-])",\n',
     _W + "test_subagent_grant_round_and_abbreviations_are_refused[--grant-round]"),
    ("the autopilot policy approves a successor with no round to run", AUTOPILOT,
     '    if no_round:\n', '    if False:\n',
     _P + "test_auto_replan_refuses_when_no_round_would_remain"),
)
