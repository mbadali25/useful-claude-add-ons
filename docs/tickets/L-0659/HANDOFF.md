# Cloud handoff: L-0659

**bare `/crew:autopilot` finds a running goal when there is no usable handoff**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Not buildable yet.** T-0056 and L-0541 must have merged, and L-0541 in turn needs T-0012. None of the three is on main.

- **Role:** child, split from T-0056, slice 2 of 3.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0659-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0659/direction.md`, `docs/tickets/L-0659/spec.md`
- **Size:** about 110 production lines, all in `plugin/crew/hooks/scripts/crew_autopilot.py`. No harness path: `python3 scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0056 | ready, not merged | `running_goals` and the goal file's `run` block. Must land first. |
| L-0541 | direction, not merged | Goal resume in `resume_target`, `next_goal_ticket`. Must land first. |
| T-0012 | approved, not merged | The goal file itself; required by T-0056 and L-0541. |
| T-0004 | merged | `resume_target`. |
| T-0018 | merged | `status`. |

Independent of L-0658: either order.

Coordinates with, no order forced: T-0049 (in-progress) and L-0589 (direction), in-flight markers; T-0053 (ready), sleep mode. The resumed goal goes through the same `next` checks as any run, so it re-checks both.

This ticket blocks: L-0660 (its mutations).

Family order (parent T-0056, four tickets), all after T-0012 and L-0541:

1. T-0056: run state in the goal file, `handoff_resume`, and every handoff writer that exists on main (gap 1).
2. After T-0056, in either order: L-0658 (a `--goal` handoff is checked against the goal file; gap 2) and L-0659 (bare `/crew:autopilot` finds running goals; gap 3). They are independent of each other.
3. L-0660 (sabotage mutations for all three, tooling-only PR): after T-0056, L-0658 and L-0659.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`). Re-find every line by content after T-0056 and L-0541 merge.
- No plan.md is published. The implementing session writes the plan.
- The return shape of `resume_target` for a goal after L-0541 is unknown until it merges. Read it before planning.
- New order: argument, handoff, running goal, active ticket, INDEX. An argument still wins, and a usable ticket handoff still wins.
- Three stop cases: several running goals stop and list them; an unreadable or malformed goal file stops as "could not tell" and the active ticket is not driven; a `stopped` goal is named and never resumed.
- With only `done` goals, or no `.work/autopilot/` directory, the output is exactly today's.
- Status must show the goal inside `STATUS_MAX_LINES` (12 on `155fe6d8`) and stay read-only. If a `goal:` line does not fit, fold it into the `source` line.
- `autopilot.md` section 2 states the new order in one sentence inside its line budget.
- No new pointer file, config key or hook. No edit to `crew_resume.py`, to `plugin/crew/tests/sabotage*.py` (L-0660), or to how a handoff is validated (L-0658) or written (T-0056).

## Open questions for the owner (recommended option taken)

1. A `stopped` goal and nothing else running: stop, or carry on with today's order? Taken: name it in a `fell through:` line and carry on with the active ticket, then INDEX. Stopping would make every bare run stop for as long as an old stopped goal file exists.
2. A usable ticket handoff while a goal is running. Taken: the handoff still wins, and a `disagreement:` line names the running goal.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0659/` in the final PR unless the owner wants it kept.
