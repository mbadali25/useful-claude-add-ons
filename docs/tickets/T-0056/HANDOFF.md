# Cloud handoff: T-0056

**a running autopilot goal is written into every handoff: goal run state and `handoff_resume`**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Not buildable yet.** There is no goal file on main. T-0012 (approved, not merged) and L-0541 (direction, split from T-0012) must land first.

- **Role:** parent of a split family. Children: L-0658, L-0659, L-0660. This ticket is the first slice only (the writers, gap 1).
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0056-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0056/direction.md`, `docs/tickets/T-0056/spec.md`
- **Size:** about 170 production lines: `plugin/crew/hooks/scripts/crew_autopilot.py` (about 135), `handoff-write.sh` (about 15), `handoff-write.ps1` (about 20). No harness path: `python3 scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0012 | approved, not merged (its handoff PR #354 was open on 2026-10-04) | The goal file `.work/autopilot/<slug>.json`, the slug and the `goal` subcommand. Must land first. |
| L-0541 | direction, not merged | Split from T-0012: the loop that drives a goal's tickets, `next_goal_ticket` and the `--goal` branch of `resume_target`. Without it nothing is "running" and there is no phase boundary to mark. Must land first. |
| T-0019 | in-progress | T-0012's own dependency (ticket minting). Whether it is fully on main: could not tell. |
| T-0010 | merged | T-0012's own dependency (policies, settings). |
| T-0018 | merged | The subcommand router and `status` that `goal` joins. |
| T-0006 | merged | The `resume:` grammar, `parse_resume`, `render`. |
| T-0004 | merged | `resume_target` and the low-context handoff in `autopilot.md`. |

Coordinates with, neither blocks:

- T-0017 (approved): the auto wrap-up writer is not on main. Whichever of T-0017 and T-0056 lands second wires that writer to `handoff_resume`.
- T-0049 (in-progress) and L-0589 (direction): in-flight markers, re-checked by a resumed goal.
- T-0053 (ready): sleep mode is re-checked on resume; no rule here. T-0053's spec lists T-0056 under "Blocks"; this ticket's spec says "coordinates, does not block". This spec wins for this ticket: T-0053 is not required first.

This ticket blocks: L-0658, L-0659, L-0660, and T-0054 (the autopilot guide carries this as a worked example).

Family order (parent T-0056, four tickets), all after T-0012 and L-0541:

1. T-0056: run state in the goal file, `handoff_resume`, and every handoff writer that exists on main (gap 1).
2. After T-0056, in either order: L-0658 (a `--goal` handoff is checked against the goal file; gap 2) and L-0659 (bare `/crew:autopilot` finds running goals; gap 3). They are independent of each other.
3. L-0660 (sabotage mutations for all three, tooling-only PR): after T-0056, L-0658 and L-0659.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- Every name that belongs to T-0012 or L-0541 (the goal file schema, `next_goal_ticket`, the `--goal` branch of `resume_target`) is not on main. Re-find each by content after they merge. If either already writes a run state or a current ticket, reuse that field; do not add a second one.
- The spec's Evidence cites the T-0012 spec and the L-0541 direction by their local ticket-folder paths. Those files are not in this branch; read them from those tickets' own handoff branches or merged code.
- The function is `handoff_resume`, not the direction's `resume_line`: `_resume_line` already exists with another meaning. The spec wins.
- When it cannot tell which goal is running (several running, or an unreadable goal file), the writer emits `resume: none` with the reason. Never the ticket form.
- `handoff-write.sh` and `handoff-write.ps1` are a matched pair: change both. The `.ps1` cases skip where PowerShell is not installed; the report must say so, and a native Windows run is asked for before merge.
- `goal-mark` writes through a temp file in the same directory and `os.replace`; every other key of the goal file is preserved byte for byte.
- Not in this slice: how a `--goal` handoff is read (L-0658), goal discovery on a bare run (L-0659), `crew_resume.py`, any `sabotage*.py` file (L-0660), T-0017's writer.
- `autopilot.md` is 109 lines on `155fe6d8` and has a line budget.
- direction.md carries two owner decisions of 2026-09-30 that still bind: catch up with main by merge (never rebase, force-push or squash), and the parallel suite shape. The wrapper path in that note is local to the owner's machine and is redacted.

## Open questions for the owner (recommended option taken)

1. A `stopped` goal on a bare resume. Taken: it is named with its stop reason and resume command, never resumed, and the run carries on with today's order.
2. Several running goals, or an unreadable goal file, when a handoff is written. Taken: the writer emits `resume: none` with the reason. The alternative (fall back to the ticket form) silently drops the goal.
3. The PreCompact skeleton gains a `resume:` line only while exactly one goal runs. Taken: yes.
4. Should auto-resume type the command for a goal handoff whose branch differs from the checkout (L-0658)? Taken: yes. The stricter option is name-only.
5. A usable ticket handoff while a goal is running (L-0659). Taken: the handoff wins and a disagreement line names the goal.
6. Build order against T-0017. Taken: whichever lands second wires the wrap-up writer; not in this Touch.
7. The function name `handoff_resume` (not `resume_line`). Confirm.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0056/` in the final PR unless the owner wants it kept.
