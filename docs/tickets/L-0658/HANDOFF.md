# Cloud handoff: L-0658

**a `--goal` handoff is checked against the goal file, not the branch and head**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Not buildable yet.** T-0056 and L-0541 must have merged, and L-0541 in turn needs T-0012. None of the three is on main.

- **Role:** child, split from T-0056, slice 1 of 3.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0658-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0658/direction.md`, `docs/tickets/L-0658/spec.md`
- **Size:** about 80 production lines (`crew_autopilot.py` about 45, `crew_resume.py` about 35). No harness path: `python3 scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0056 | ready, not merged | `running_goals` and the goal file's `run` block. Must land first. |
| L-0541 | direction, not merged | The `--goal` branch of `resume_target`. Must land first. |
| T-0012 | approved, not merged | The goal file itself; required by T-0056 and L-0541. |
| T-0006 | merged | The `resume:` grammar. |
| T-0004 | merged | `resume_target`. |

Independent of L-0659: either order (stated in L-0659's spec).

This ticket blocks: L-0660 (its mutations).

Family order (parent T-0056, four tickets), all after T-0012 and L-0541:

1. T-0056: run state in the goal file, `handoff_resume`, and every handoff writer that exists on main (gap 1).
2. After T-0056, in either order: L-0658 (a `--goal` handoff is checked against the goal file; gap 2) and L-0659 (bare `/crew:autopilot` finds running goals; gap 3). They are independent of each other.
3. L-0660 (sabotage mutations for all three, tooling-only PR): after T-0056, L-0658 and L-0659.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and L-0541 rewrites the goal stop in `_handoff_ticket`. Re-find every line by content after T-0056 and L-0541 merge.
- No plan.md is published. The implementing session writes the plan.
- The branch and head check sits in three places (`_handoff_ticket`, status's `_resume_line`, `crew_resume.decide`). All three gain the goal branch through one helper, and all three keep the check unchanged for the ticket form.
- "Could not read the goal file" is its own answer, never "no goal". `decide` answers `wait`, never `run`, on each must-block case.
- A `stopped` goal is named with its reason and never resumed.
- Every other auto-resume condition still binds a goal handoff: the author record, consumed-once, the progress fingerprint, the armed setting, the manual-compact rule.
- `crew_resume.py` must not import `crew_autopilot.py` if that makes a cycle. State in the plan whether a lazy import or a shared small module is used.
- No edit to `plugin/crew/tests/sabotage*.py` (L-0660). No writer changes (T-0056). No discovery without a handoff (L-0659).

## Open questions for the owner (recommended option taken)

1. Should auto-resume (typing the command after `/clear`) be allowed for a goal handoff whose branch differs from the checkout? Taken: yes, because the author record and consumed-once rules still bind it to this session and this note. Alternative: name the command and never type it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0658/` in the final PR unless the owner wants it kept.
