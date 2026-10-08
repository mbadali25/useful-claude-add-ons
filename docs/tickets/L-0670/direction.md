# L-0670 direction: a successor plan written after an automatic reject must quote every BLOCK and FIX line

status: proposed 2026-10-04 (split from T-0074; filed as L-0670)
risk: high

Split from T-0074.

## Request
T-0074 lets autopilot reject an out-of-rounds review that has a BLOCK and continue with a successor plan it approves itself. T-0074 states "the plan addresses every BLOCK and FIX verbatim" only as procedure text in `commands/autopilot.md`. Nothing checks it. A successor plan that leaves a BLOCK out is approved, spends two fresh review rounds and one of the capped replans, and finds the same BLOCK again.

## What exists (origin/main 155fe6d8, plus T-0074)
- The rejected round's finding lines are in the ledger row (`findings`, plugin/crew/hooks/scripts/review_ledger.py:399).
- `review_ledger.check_follow_up` (:757-800) is the model: every line verbatim, as a whole line, counted, split on `\n` only, CRLF tolerated, could-not-tell on anything unreadable.
- `crew_autopilot.approve` (plugin/crew/hooks/scripts/crew_autopilot.py:1129-1151) is the only route by which autopilot approves a plan.
- T-0074 adds `AUTO_REJECT_BY` and the ledger's `rejected.by` tells an automatic reject from an owner's.

## Recommendation
A read-only check, `crew_autopilot.py replan-check --root . --ticket <id>`, and the same check inside `crew_autopilot.approve`: when the ledger is NEEDS_REPLAN and `rejected.by` is `AUTO_REJECT_BY`, the plan is approved by autopilot only if `plan.md` holds every `BLOCK|` and `FIX|` line of the rejected round verbatim as a whole line, as many times as the round carries it. NIT lines are not required. An owner's `/crew:approve` is not affected, and neither is a successor plan after an owner's reject.

## Options considered
1. Check in `crew_autopilot.py` only (recommended): no harness file changes, the rule binds only autopilot's own approval.
2. Check in `crew_ticket.validate`: binds every approval route, but `crew_ticket.py` is a harness path and the owner may want to approve a plan that drops a finding on purpose.
3. No check, rely on the next review rounds and the cap: cheapest, but each miss costs two rounds and one replan.

## Depends on / order
T-0074 (must be merged). Lands before L-0671, which adds this check's sabotage entries.
