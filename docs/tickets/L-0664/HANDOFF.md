# Cloud handoff: L-0664

**promote-gate.ps1 treats a workflow dispatch of a declared deploy workflow as that deploy**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs T-0062 merged first, and T-0062 is itself blocked on T-0009 (PR #336, open on 2026-10-04).

- **Role:** child, split from T-0062, slice 1 of 2.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0664-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0664/direction.md`, `docs/tickets/L-0664/spec.md`
- **Size:** about 100 production lines in `plugin/crew/hooks/scripts/promote-gate.ps1` (about 60 are the `Resolve-CrewPython` copy). No new parser. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0062 | ready, handed off (branch `T-0062-build`), not built | Hard blocker. Supplies `_promote_dispatch.py` and `test_promote_gate_dispatch.py`, which this ticket calls and extends. |
| T-0009 | in progress (PR #336, open on 2026-10-04, not on main) | Needed through T-0062: the dispatch reader. |
| T-0505 | merged (PR #296) | The effective-tree promote-gate. |

The facts file and the spec agree on these three.

**This ticket blocks:** nothing. The spec says T-0045 benefits.

**Order of the family:**

1. L-0665 (first-row fix): independent. Needs nothing unmerged; it can land now.
2. T-0062 (shared reader and the Bash flavour): after T-0009 (PR #336) merges.
3. L-0664 (PowerShell twin): after T-0062.

All three edit `promote-gate.sh` or `promote-gate.ps1`, as do L-0564 (direction) and L-0648 (split from T-0045, draft PR #445, lands after T-0062). Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor, and re-read `promote-gate.ps1` after T-0062 lands.
- There is no plan.md for this ticket. The implementing session writes the plan.
- Port the call, not the reader: `promote-gate.ps1` calls T-0062's `_promote_dispatch.py` with `shell=powershell`. No native PowerShell parser.
- `Resolve-CrewPython` must be byte-identical to the other crew `.ps1` copies (`test_ps1_python_probe.py`). U1: whether that test finds `.ps1` files by glob or by a list was not checked.
- `promote-gate.sh` must be unchanged in this PR.
- This is a hook that can block: must-block and must-allow cases, sabotage-tested. Mutations go in `promote_tree_mutations.py`; do not edit `plugin/crew/tests/sabotage*.py`.
- The `ps1` cases skip without PowerShell 7 and must never fail for that reason. The spec asks for a native Windows run before landing; a cloud session cannot do that, so report it as NOT RUN.
- A bare `pwsh` is not on PATH in every shell (CLAUDE.md landmine): name it absolutely or resolve it.
- Touch includes `docs/guides/crew/**` rebuilt outputs (HTML, DOCX, PDF). Whether the cloud environment can rebuild DOCX and PDF: could not tell.

## Open questions for the owner (recommended option taken)

1. No python on the PowerShell side: block dispatch-looking commands (taken) or stand down as the Bash flavour does at `promote-gate.sh:79`?
2. Windows-native proof (U3): the pwsh cases run on Linux with PowerShell 7 and a native Windows run is requested before landing. Accepted in the spec; listed here because the cloud session cannot produce it.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0664/` in the final PR unless the owner wants it kept.
