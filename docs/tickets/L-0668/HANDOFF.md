# Cloud handoff: L-0668

**T-0067 child 3: sabotage mutations for the review policy, the fix phase and the stop contract (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0067, slice 3 of 3 (the family is T-0067, L-0666, L-0667, L-0668).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0668-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0668/direction.md`, `docs/tickets/L-0668/spec.md`
- **Size:** 0 production lines; about 60 lines of mutation tuples in `plugin/crew/tests/sabotage_autopilot.py`, plus any missing tests. **This touches a review/gate harness path**, so it lands alone as a tooling-only PR with no feature work.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0067 | ready, not started | Must be merged first. Mutations (a) to (l) break rules it adds. |
| L-0666 | direction, spec written, not started | Must be merged first. Mutations (m) to (o) break its contract. |
| T-0087 | merged | The tooling-PR rule and its checker. |

Blocked until T-0067 and L-0666 are on main. Anchors are taken from the code they land, not from this spec.

One fallback from the spec and direction: if L-0666 is delayed, land mutations (a) to (l) alone and move (m) to (o) to a follow-up.

This ticket blocks nothing. The spec adds that T-0073 should not start before this lands, so it builds on mutated-and-proven rules.

Family order:

1. **T-0067**: the `reviewPolicy` key and the `fix` phase. Feature PR.
2. **L-0666**: the stop-message contract. Feature PR.
3. **L-0668** (this ticket): sabotage mutations for 1 and 2. Tooling-only PR.
4. **L-0667**: `/crew:graph`. Independent; waits for T-0064. Not a dependency of this ticket.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. An anchor must be one line, present exactly once, taken from the merged code.
- There is no plan.md and none is published. The implementing session writes the plan.
- The spec says the rules to mutate are in T-0067's spec (Design, "Fail closed") and in a `children/1/spec.md` under T-0067's local ticket folder. That second file is published as `docs/tickets/L-0666/spec.md` on branch `L-0666-build`.
- No production code and no prompt: not `crew_autopilot.py`, not `crew_state.py`, not `commands/autopilot.md`. A mutation that stays green means a missing test (add the test here) or a production bug (stop, file it, fix it in its own feature PR).
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint line limit), to existing mutations, to `review_*.py`, `commands/review.md` or `scripts/check-tooling-pr.py`. No `Tooling-seam:` trailer.
- The harness rule's checks (tooling-PR check and its suite, golden replay, seam contracts, canary review) are each named in the PR body as run or not run.
- The sabotage run is heavy; run it once, through whatever heavy-run wrapper the environment provides.

## Open questions for the owner (recommended option taken)

None of its own. One tooling-only PR after both feature PRs was taken over two tooling PRs. If the owner changes an answer in T-0067 or L-0666 (for example whether a round-1 BLOCK is fixed unattended), the matching mutation changes with it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0668/` in the final PR unless the owner wants it kept.
