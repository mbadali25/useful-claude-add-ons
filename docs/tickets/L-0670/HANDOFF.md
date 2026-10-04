# Cloud handoff: L-0670

**T-0074 child 1: autopilot approves a successor plan after an automatic reject only when it quotes every BLOCK and FIX line**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0074, slice 1 of 2 (the family is T-0074, L-0670, L-0671).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The direction's own status line reads "proposed 2026-10-04".
- **Branch:** `L-0670-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0670/direction.md`, `docs/tickets/L-0670/spec.md`
- **Size:** about 80 production lines, all in `plugin/crew/hooks/scripts/crew_autopilot.py`. One guard. No harness path (`crew_autopilot.py` and `commands/autopilot.md` are seam paths, which count as feature work here).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0074 | direction, spec written, not started | Must be merged first. This reads its `AUTO_REJECT_BY` constant and extends its test file `test_crew_autopilot_replan.py`. |
| T-0010 | merged | The approval policy and `crew_autopilot.py approve`, where the check is called. |
| L-0510 | done | Round rows carry `findings`; `check_follow_up` is the comparison this copies. |

Blocked until T-0074 is on main. Do not start before then.

This ticket blocks L-0671, which adds this check's sabotage entries. That block is soft: L-0671 may land with T-0074's mutations only if this ticket is delayed.

Family order:

1. **T-0074**: key, policy, `auto-reject`, routing. Feature PR.
2. **L-0670** (this ticket): the successor-plan check. Feature PR.
3. **L-0671**: sabotage entries for both guards and the `review.md` sentence. Tooling-only PR.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`, plus T-0074's spec. Main has moved since (this branch starts at `ce235468`), and line numbers in `crew_autopilot.py` move again when T-0074 lands. Re-read before planning.
- There is no plan.md and none is published. The implementing session writes the plan.
- The check binds only autopilot's own approval. `/crew:approve` and `crew_ticket.py approve --by` do not run it, and there is no check after an owner's reject or on a ticket's first plan.
- The comparison is verbatim, whole line, counted, split on `\n` only with one trailing `\r` dropped. NIT lines are not required. Could-not-tell is `ok` false with a reason, never a pass.
- No edit to `crew_ticket.py`, `review_ledger.py`, `scope_guard.py` or any other harness path. No sabotage entries here.
- One Unknown is resolved at plan by a fixture: whether the plan validator accepts raw `BLOCK|...` lines anywhere in a plan. If a placement is refused, the procedure text names the placement that passes.
- The PR body says the sabotage run for this guard is not done here (L-0671) and that `scripts/_test/drift-detection.sh` was not run.

## Open questions for the owner (recommended option taken)

None of its own beyond the option choice: the check lives in `crew_autopilot.py` only. Alternative: put it in `crew_ticket.validate`, which binds every approval route but is a harness path, and the owner may want to approve a plan that drops a finding on purpose. The parent's questions are in T-0074's handoff.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0670/` in the final PR unless the owner wants it kept.
