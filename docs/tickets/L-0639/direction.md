# L-0639 direction - cancelled and superseded close a ticket; blocked and needs-replan are derived (crew_ticket_state.py)

Split from T-0037 on 2026-10-04 (size and tooling-PR check; the owner was not available, the recommended option was taken). Not yet approved by the owner.

## Ask
The owner's 2026-09-26 request behind T-0037: crew statuses that say who and what a ticket is waiting on. The direction approved that day made `blocked` and `needs-replan` derived, never typed, and made `cancelled` / `superseded` closing statuses.

## Why a separate ticket
T-0037 now changes only `crew_ticket.py`, a `HARNESS` path in `scripts/check-tooling-pr.py`, so it lands as a tooling PR that may carry no feature code. This slice is the feature code: `crew_state.py`, `crew_autopilot.py`'s `INDEX_DONE`, a new `crew_ticket_state.py`, and the `/crew:spec` template line. It contains no `HARNESS` path, so it is an ordinary feature PR.

## Facts (origin/main 155fe6d8)
- `crew_state._TABLE_DONE_WORDS` (`plugin/crew/hooks/scripts/crew_state.py:238-240`) and `crew_autopilot.INDEX_DONE` (`plugin/crew/hooks/scripts/crew_autopilot.py:183`) hold the same six words and no `cancelled` or `superseded`.
- `crew_ticket._index_closed` (`plugin/crew/hooks/scripts/crew_ticket.py:831`) already answers closed / open / could-not-tell for one ticket's INDEX row.
- `review_ledger.status` (`plugin/crew/hooks/scripts/review_ledger.py:961`) reports `NEEDS_REPLAN` (`:154`).
- No module derives a status from another ticket's state.

## Recommendation
One read-only module, `crew_ticket_state.py`, with `dependency_state` and `view`. A dependency that is open, unknown, cancelled or superseded blocks; only `done`/`merged`-class words unblock. `cancelled` and `superseded` join both closed-word sets, pinned equal by a test.

## Depends on
T-0037 (`CLOSING_STATUSES`, `DERIVED_STATUSES`, `header_status`, `parse_depends_on`).

## Open questions for the owner
- A dependency marked `done` but not yet `merged` unblocks (kept from the approved T-0037 spec). Confirm.
- The sabotage mutations for this slice land afterwards in L-0641, because `plugin/crew/tests/sabotage*.py` is harness. Until then the must-block tests exist but are not mutation-proven. Accepted by default.
