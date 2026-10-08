# Cloud handoff: L-0636

**Cross-session messaging: an unanswered doorbell reads `could not tell` and is surfaced to the owner**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0030 and T-0032 are merged to main.** T-0030 is only on a local branch that is not on the shared remote, and `crew_bridge.py` (T-0032) is not written yet.

- **Role:** child ticket, split from T-0032, slice 1 of 3 (the other children are L-0637 and L-0638).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0636-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0636/direction.md`, `docs/tickets/L-0636/spec.md`
- **Size:** about 150 production lines, in `plugin/crew/hooks/scripts/crew_bridge.py`. No harness path. `plugin/crew/commands/autopilot.md` is a `SEAM` path, which matters only beside a harness change. The sabotage mutations are L-0638.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0030 | in-progress, not on main, not in this hand-off | The no-force write path and the channel log this slice appends to. |
| T-0032 | ready (PR in this hand-off) | `crew_bridge.py`, which this slice extends. |
| T-0031 | ready (PR in this hand-off) | Ordering only. |

This ticket blocks: L-0638. L-0637 is independent of it, but both edit `crew_bridge.py` and `autopilot.md`, so L-0637's spec asks for this ticket to land first.

Order of the whole family:

1. T-0030 lands on main (not part of this hand-off). T-0029 must also be on main before L-0637.
2. T-0031 (PR in this hand-off): ordering only, the owner's order is T-0030, T-0031, T-0032.
3. T-0032: the doorbell grammar (`ring`, `receive`) and the untrusted-data rules.
4. L-0636: an unanswered doorbell reads `could not tell`.
5. L-0637: the hub rule, lanes never ring a peer. After L-0636, because both edit `crew_bridge.py` and `autopilot.md`.
6. L-0638: the sabotage mutations for the bridge script, as a tooling-only PR. Last.

## Read before writing code

- The spec's evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- The `crew_coord.py` anchors are from the unmerged branch `T-0030-coord` at `ec9a28a2`, which is not on the shared remote. Re-check after T-0030 merges.
- No plan.md is published. The implementing session writes the plan, after T-0030 and T-0032 land.
- `rang` must be a new log event that T-0030's `status` prints or ignores safely. If the landed `crew_coord.py` refuses unknown events, stop and return to the owner: changing it is outside Touch.
- Nothing turns a pending ring into consent: no timeout, no retry count, no "delivered" state, no re-ring. A failed fetch is `unknown`, never `no pending doorbells`.
- Known limit, to be stated in the README: any later log line from a different holder clears a ring, so a third session on the channel also clears it.
- No change to `crew_autopilot.py`, `crew_status.py` or `crew_resume.py` (`SEAM` paths) and no new autopilot stop reason. No force push, no hook, no config key, no `sabotage*.py` file.
- direction.md and spec.md refer to `.work/tickets/T-0030/direction.md` (part 6 and "Facts this rests on"). That file is not published here.

## Open questions for the owner (recommended option taken)

1. Should a pending doorbell also be an autopilot stop reason when the active ticket waits on a `<channel>:<id>` dependency? Taken: no. It is printed by status and by the resume step only, because `crew_autopilot.py` is a seam of the review harness and the wave owns dependency stops.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0636/` in the final PR unless the owner wants it kept.
