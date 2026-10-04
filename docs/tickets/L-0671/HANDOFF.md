# Cloud handoff: L-0671

**T-0074 child 2: sabotage entries for the auto-replan policy and the successor-plan check; `review.md` names the policy (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0074, slice 2 of 2 (the family is T-0074, L-0670, L-0671).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). The direction's own status line reads "proposed 2026-10-04".
- **Branch:** `L-0671-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0671/direction.md`, `docs/tickets/L-0671/spec.md`
- **Size:** 0 production lines; about 110 lines in `plugin/crew/tests/sabotage_autopilot.py`, about 25 test lines, one sentence in `plugin/crew/commands/review.md`. **This touches review/gate harness paths** (both of those files), so it lands alone as a tooling-only PR with no feature work.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0074 | direction, spec written, not started | Must be merged first. Its guard is what entries 1 to 14 mutate. |
| L-0670 | direction, spec written, not started | Should be merged first. Entries 15 to 19 mutate its check. |
| T-0087 | merged | The tooling-PR rule and its checker. |

Blocked until T-0074 is on main.

The recorded dependency list names L-0670 as a prerequisite without qualification. The spec says it is not a hard block, and the spec wins: if L-0670 has not landed, entries 15 to 19 are left out, listed in the PR body as owed, and follow in their own tooling PR.

This ticket blocks nothing. It is the last of the family.

Family order:

1. **T-0074**: key, policy, `auto-reject`, routing. Feature PR.
2. **L-0670**: the successor-plan check. Feature PR.
3. **L-0671** (this ticket): sabotage entries and the `review.md` sentence. Tooling-only PR.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. The find and replace strings depend on the code T-0074 and L-0670 land; read the merged `crew_autopilot.py` and write each anchor so it matches exactly once.
- There is no plan.md and none is published. The implementing session writes the plan.
- No edit to `crew_autopilot.py`, `crew_state.py`, `commands/autopilot.md` or any other production or prompt file outside the harness. If a mutation needs a code change to become testable, that change is a separate feature PR first.
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint module line limit). The new tuple joins `AUTOPILOT_MUTATIONS` the way `STATUS_MUTATIONS` does. No `Tooling-seam:` trailer.
- The harness rule's commands (tooling-PR check and its suite, golden replay, seam contracts, canary review) are each named in the PR body with a result.
- The sabotage run is heavy; run it through whatever heavy-run wrapper the environment provides, one suite at a time, and quote the count. Afterwards `git status --porcelain plugin/crew/hooks` prints nothing.
- The PR body says `scripts/_test/drift-detection.sh` was not run.

## Open questions for the owner (recommended option taken)

None of its own. One tooling PR after both feature slices was taken over two tooling PRs, one per guard. The parent's questions are in T-0074's handoff; if the owner changes one (for example how the cap counts), the matching mutation changes with it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0671/` in the final PR unless the owner wants it kept.
