# L-0687 direction - the owner list knows hold, blocked, landing and needs-owner

Status: seed (not yet approved). Split from L-0551 on 2026-10-04. Filed as L-0687.

## Problem
L-0551 builds `/crew:status --owner` and the `waiting` line from autopilot's stop phases as they are on origin/main `155fe6d8`. T-0037 (with its children L-0639 and L-0640) and L-0550 add ticket states that are parked on purpose: `hold`, `landing`, `needs-owner`, the derived `blocked`, and the closing words `cancelled` and `superseded`. Once L-0550 makes autopilot stop on them, L-0551's list shows each as a generic line, `see /crew:autopilot status <id>`, and counts a ticket on hold until next month as waiting on the owner today.

## Original text (from T-0037 plan.md Step 6, the parts L-0551 did not take)
> - Explicit needs-owner gives next.md's `next:`.
> - A hold past its revisit gives `revisit`.
> - Must-allow: `test_owner_skips_future_holds`.
> - `test_default_report_has_a_waiting_line`: `waiting  N on you (/crew:status --owner), H held, B blocked`.

## Recommendation (taken; the owner was not available)
Extend `crew_autopilot.owner_items` and the two renderers in `crew_status.py`:
- `hold` with a revisit date in the future: not listed, counted as held.
- `hold` whose revisit is due, or with no usable revisit date: listed as `revisit`, with next.md's `reason:`.
- `blocked`: not listed, counted as blocked. The owner list names what the owner can act on; a blocked ticket waits on another ticket.
- `landing`: not listed and not counted. It waits on the merge.
- `needs-owner`: listed with next.md's `next:`, or "cannot tell what is asked" when there is none.
- `cancelled` / `superseded`: already `closed`, already skipped.
- The waiting line becomes `waiting  N on you (/crew:status --owner), H held, B blocked`, the unread and could-not-tell counts following only when non-zero.

Alternative considered: list blocked tickets too, with the dependency named. Rejected for the list (it is not the owner's move) but the count stays visible.

## Dependencies
- L-0551 (the list itself).
- L-0550 (autopilot stops with these phase names).
- L-0639 (`crew_ticket_state.view`, `blocked_by`) and L-0640 (`next.md`, `revisit_due`), transitively T-0037.

## Open questions for the owner
- Should a blocked ticket appear in the `--owner` list at all? (Default taken: counted, not listed.)
- A hold with no `revisit:` line: listed as due now, or held forever? (Default taken: listed, because "could not tell when" must not read as "not yet".)
