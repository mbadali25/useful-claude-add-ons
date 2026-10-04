# Cloud handoff: L-0660

**sabotage entries for goal resume: writers, handoff validation, discovery (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Not buildable yet.** T-0056, L-0658 and L-0659 must have merged (or the PR states which mutations are deferred). They in turn wait on T-0012 and L-0541, which are not on main.

- **Role:** child, split from T-0056, slice 3 of 3.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0660-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0660/direction.md`, `docs/tickets/L-0660/spec.md`
- **Size:** 0 production lines. About 150 lines of mutation entries in `plugin/crew/tests/sabotage_autopilot.py` and `plugin/crew/tests/sabotage_resume.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a review/gate harness path, so this lands alone as a tooling-only PR. Tests and docs may ride along; feature code may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0056 | ready, not merged | Mutations (a) to (e) edit its code. Must be merged first. |
| L-0658 | direction, not merged | Mutations (f) to (i) edit its code. |
| L-0659 | direction, not merged | Mutations (j) to (l) edit its code. |
| T-0087 | merged | The tooling-PRs-land-alone rule. |

This ticket blocks nothing.

Family order (parent T-0056, four tickets), all after T-0012 and L-0541:

1. T-0056: run state in the goal file, `handoff_resume`, and every handoff writer that exists on main (gap 1).
2. After T-0056, in either order: L-0658 (a `--goal` handoff is checked against the goal file; gap 2) and L-0659 (bare `/crew:autopilot` finds running goals; gap 3). They are independent of each other.
3. L-0660 (sabotage mutations for all three, tooling-only PR): after T-0056, L-0658 and L-0659.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`). The anchor text of each mutation is taken from the merged code of T-0056, L-0658 and L-0659; each anchor must appear exactly once in its file.
- No plan.md is published. The implementing session writes the plan.
- If L-0658 or L-0659 is delayed, land the mutations for what has merged and say which are left.
- No production code, command, skill or prompt edit. If a mutation shows a rule is untested, the missing test is added here; a production fix is a new ticket.
- No edit to `plugin/crew/tests/sabotage.py` (at the module line limit) and no new mutation list name: add to `AUTOPILOT_MUTATIONS` and `RESUME_MUTATIONS`, which the runner already imports.
- A harness change runs the harness rule's suites (the tooling checker, its suite, the golden replay, the seam contracts, the canary review).
- The spec says no crew version bump unless the gate requires one for a tests-only change; say which in the PR. This differs from the usual landing paragraph below: check what the gate asks for and follow the spec.
- PR body: `Docs: none - sabotage entries only` if the code map needs no edit either.

## Open questions for the owner (recommended option taken)

None of its own in the spec. The direction took one tooling-only PR after the three feature PRs over one tooling PR per feature PR. The parent's open questions are in T-0056's handoff.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0660/` in the final PR unless the owner wants it kept.
