# Cloud handoff: L-0661

**T-0057 child 1: sabotage mutations for the autopilot routing rows (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0057, slice 1 of 3 (the family is T-0057, L-0661, L-0662, L-0663).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The direction says the split is "not yet approved as a ticket".
- **Branch:** `L-0661-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0661/direction.md`, `docs/tickets/L-0661/spec.md`
- **Size:** 0 production lines; about 45 lines in `plugin/crew/tests/sabotage_route.py`. **This touches a review/gate harness path**, so it lands alone as a tooling-only PR with no feature work.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0057 | ready, not started | Must be merged first. Every anchor here is a string T-0057 writes in `crew_route.py`. |
| T-0087 | merged | The tooling-PR rule this ticket exists to satisfy. |

Blocked until T-0057 is on main. Do not start before then.

This ticket blocks L-0663 (it edits the same file, and L-0663's direction asks for L-0661 to be merged first). The spec's Dependencies section says "Blocks: nothing"; L-0663's own spec and direction name L-0661 as a prerequisite, so L-0663 is listed here.

Family order:

1. **T-0057**: gate and five rows. Feature PR.
2. **L-0661** (this ticket): sabotage mutations for T-0057. Tooling-only PR.
3. **L-0662**: rows for wave, split, sleep, wake. Feature PR. After T-0057; independent of this ticket.
4. **L-0663**: sabotage mutations for L-0662. Tooling-only PR. After L-0662 and L-0661.

L-0663's direction allows one shortcut: if this ticket has not started when L-0662 merges, the two tooling PRs may be done as one; say so in the PR body.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. The anchor strings themselves do not exist until T-0057 merges; read `crew_route.py` on main then.
- There is no plan.md and none is published. The implementing session writes the plan.
- No edit to `crew_route.py`, `crew_context.py`, `crew_autopilot.py` or any command, skill or prompt. If an anchor cannot be made unique without changing `crew_route.py`, stop: that is a feature PR first, then this one.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at the pylint module limit). `ROUTE_MUTATIONS` is already imported and registered there.
- The harness rule in `.crew/verify.json` must run in full (tooling-PR check, its suite, golden replay, seam contracts, canary review). Each is named in the PR body with its result.
- After the sabotage run, `git status --porcelain plugin/crew/hooks/scripts/` must be empty.

## Open questions for the owner (recommended option taken)

None of its own. The parent's questions that shape these mutations (the soft ask line, the pronoun guard, explicit ids for `focus`) are listed in T-0057's handoff; if the owner changes one, the matching mutation changes with it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0661/` in the final PR unless the owner wants it kept.
