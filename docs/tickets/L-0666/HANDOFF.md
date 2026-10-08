# Cloud handoff: L-0666

**T-0067 child 1: autopilot stop messages name only owner decisions (a contract test over every stop)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0067, slice 1 of 3 (the family is T-0067, L-0666, L-0667, L-0668).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0666-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0666/direction.md`, `docs/tickets/L-0666/spec.md`
- **Size:** about 80 production lines (`crew_autopilot.py` about 70, `commands/autopilot.md` about 10). No harness path. Both files are seam paths, which count as feature work here.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0067 | ready, not started | Must be merged first. It edits the same function, and the reworded FINDINGS stop refers to its `reviewPolicy` and `fix` phase. |
| T-0004, T-0010, T-0018 | merged | The autopilot `next`, the policy pattern and `status`. |

Blocked until T-0067 is on main. Do not start before then.

Related, no ordering: T-0073 (direction; acceptance policy), T-0070 (spec; `/crew:status --approvals`), L-0667 (edits `commands/autopilot.md` too; this ticket's `MECHANICAL` list already names `/crew:graph --refresh`), T-0043 (rewords the same FINDINGS stop; whichever lands second re-reads it and keeps this contract).

This ticket blocks L-0668 (sabotage for this contract).

Family order:

1. **T-0067**: the `reviewPolicy` key and the `fix` phase. Feature PR.
2. **L-0666** (this ticket): the stop-message contract. Feature PR.
3. **L-0668**: sabotage mutations for 1 and 2. Tooling-only PR. After both.
4. **L-0667**: `/crew:graph`. Independent of 1 to 3; waits for T-0064.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`), and T-0067 lands first and moves the lines again. Re-read before planning.
- There is no plan.md and none is published. The implementing session writes the plan.
- No behaviour change: every stop that stops today still stops, with the same `phase`. Only reason text, the new `decision` field and (for one stop) the listed artifacts change.
- A stop site the decision table does not fit gets `look`, never a new id invented in a test. If a stop site is built in a way the completeness walk does not see, extend the walk; do not exempt the site.
- `HUMAN_STOPS`, `FIXED_STOPS` and `PROCEDURE_STOPS` texts are not changed. Lines existing sabotage mutations anchor stay byte-identical. No edit to any harness path.
- `decision=` is appended after the existing fields on the `phase=` line, so a prefix reader is unaffected. The spec gives the grep that checks who parses that line.

## Open questions for the owner (recommended option taken)

1. When the auto-accept guard passes but no receipt was written, the stop names only the owner's accept. Alternative: autopilot finishes the auto-accept itself (acceptance policy, T-0073's).
2. Re-pointing the worktree at another ticket (`crew_ticket.py activate`) stays an owner decision, because it changes which approval governs the edits. Alternative: autopilot does it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0666/` in the final PR unless the owner wants it kept.
