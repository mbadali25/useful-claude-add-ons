# Cloud handoff: L-0663

**T-0057 child 3: sabotage mutations for the wave, split, sleep and wake routing rows (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0057, slice 3 of 3 (the family is T-0057, L-0661, L-0662, L-0663).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The direction says the split is "not yet approved as a ticket".
- **Branch:** `L-0663-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0663/direction.md`, `docs/tickets/L-0663/spec.md`
- **Size:** 0 production lines; about 30 lines in `plugin/crew/tests/sabotage_route.py`. **This touches a review/gate harness path**, so it lands alone as a tooling-only PR with no feature work.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0662 | direction, spec written, not started | Must be merged first. Every anchor here is a string L-0662 writes, and every mutation names an L-0662 test. |
| L-0661 | direction, spec written, not started | Must be merged first: it edits the same file, `sabotage_route.py`. |
| T-0057 | ready, not started | Through those two. |
| T-0087 | merged | The tooling-PR rule. |

Blocked until L-0662 and L-0661 are on main. This is the last ticket of the family; it blocks nothing.

Family order:

1. **T-0057**: gate and five rows. Feature PR.
2. **L-0661**: sabotage mutations for T-0057. Tooling-only PR.
3. **L-0662**: rows for wave, split, sleep, wake. Feature PR.
4. **L-0663** (this ticket): sabotage mutations for L-0662. Tooling-only PR.

One shortcut from the direction: if L-0661 has not started when L-0662 merges, the two tooling PRs may be done as one; say so in the PR body.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. The anchor strings do not exist until L-0662 merges; read `crew_route.py` on main then.
- There is no plan.md and none is published. The implementing session writes the plan.
- No edit to `crew_route.py` or any other production file, command, skill or prompt. An anchor that cannot be unique without a production edit is a stop.
- No edit to `plugin/crew/tests/sabotage.py` (at the 3400-line pylint limit).
- The harness rule's commands in `.crew/verify.json` must run and be named in the PR body with results.
- After the sabotage run, `git status --porcelain plugin/crew/hooks/scripts/` must be empty.

## Open questions for the owner (recommended option taken)

None of its own. If the owner changes a phrase decision in L-0662 (bare "this is too big", the wake greetings), the matching mutation changes with it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0663/` in the final PR unless the owner wants it kept.
