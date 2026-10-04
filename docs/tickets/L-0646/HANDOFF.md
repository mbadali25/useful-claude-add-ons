# Cloud handoff: L-0646

**`crew_ghdeploy.py watch`: pass, fail or unknown from the run and its deploy job**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs L-0645 merged first.

- **Role:** child, split from T-0045, slice 3 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0646-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0646/direction.md`, `docs/tickets/L-0646/spec.md`
- **Size:** about 150 production lines in `plugin/crew/hooks/scripts/crew_ghdeploy.py`. One fail-closed state machine. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0645 | direction, handed off (branch `L-0645-build`), not built; itself waits on L-0644 | Writes the run id into the state file that `watch` follows. |

The facts file says "T-0045 child 2", which is L-0645. The spec agrees.

**This ticket blocks:** L-0647 (records the verdict `watch` writes), and through it L-0649.

**Order of the family** (parent T-0045, draft PR #407):

1. T-0045: the `github` entry in `.crew/verify.json` and `crew_ghdeploy.py check`.
2. L-0650: tooling-only PR that wires `ghdeploy_mutations.py` into the sabotage harness. Default is right after T-0045; it lands alone.
3. L-0644 `prepare`: after T-0045 and T-0009.
4. L-0645 `identify`: after L-0644.
5. L-0646 `watch`: after L-0645.
6. L-0647 `record` and the `/crew:promote` sequence: after L-0644, L-0645 and L-0646.
7. L-0648 promote-gate reads the `github` entry: after T-0045 and T-0062. It does not need L-0644 to L-0647.
8. L-0649 autopilot's deploy phase: last. After T-0011, T-0009, and L-0644 to L-0648.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- There is no plan for this ticket. The parent's plan.md (2026-09-26) is stale and is not published; the implementing session writes the plan. The direction's "kept from plan.md 'Design'" refers to text that is not available here. Where a design detail is not in this spec or the parent's files (`docs/tickets/T-0045/` on branch `T-0045-build`): could not tell, ask the owner.
- The watch command's exit code never decides the verdict. The verdict comes from `gh run view --json`.
- Never cancel, re-run or approve a run. The only `gh` calls are `run watch` and `run view`.
- One slice must end inside the Bash tool's 600000 ms foreground limit; a slice that ends before the deadline exits 75.
- The `gh run watch` timing and token behaviour were observed once, in another repository. Treat it as one data point.
- No edit to `plugin/crew/tests/sabotage*.py` (harness), promote-gate or autopilot.
- Every slice from T-0045 to L-0649 adds to `crew_ghdeploy.py`, `test_crew_ghdeploy.py` and `ghdeploy_mutations.py` (where listed in Touch). Build on what the earlier slices merged; do not start a slice on a branch that lacks them.

## Open questions for the owner (recommended option taken)

1. `watchMinutes` default 60, carried from 2026-09-26.
2. When `deployJob` is not configured: pass with the detail "deploy job not checked" (taken), or refuse to call it a pass?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0646/` in the final PR unless the owner wants it kept.
