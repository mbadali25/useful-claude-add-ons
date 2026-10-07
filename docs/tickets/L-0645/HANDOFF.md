# Cloud handoff: L-0645

**`crew_ghdeploy.py identify`: exactly one new workflow run, or could-not-tell**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs L-0644 merged first.

- **Role:** child, split from T-0045, slice 2 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0645-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0645/direction.md`, `docs/tickets/L-0645/spec.md`
- **Size:** about 110 production lines in `plugin/crew/hooks/scripts/crew_ghdeploy.py`. One fail-closed state machine. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0644 | direction, handed off (branch `L-0644-build`), not built; itself waits on T-0045 and T-0009 | Writes the state file `.crew/.ghdeploy/<env>-<N>.json` (snapshot, `t0`, correlation id) that `identify` reads. |

The facts file says "T-0045 child 1", which is L-0644. The spec agrees.

**This ticket blocks:** L-0646 (needs the run id), and through it L-0647 and L-0649.

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
- Never pick among candidates: no "newest", no "closest to t0". With a correlation id there is no fallback to the time rule.
- The only `gh` call is `run list`. Re-check its JSON field list (`gh run list --json` with no argument prints it) at plan; the field list in the spec is from a 2026-09-26 measurement.
- The "about 2 seconds" timing was observed once, in another repository. Treat it as one data point.
- No edit to `plugin/crew/tests/sabotage*.py` (harness), promote-gate or autopilot.
- Every slice from T-0045 to L-0649 adds to `crew_ghdeploy.py`, `test_crew_ghdeploy.py` and `ghdeploy_mutations.py` (where listed in Touch). Build on what the earlier slices merged; do not start a slice on a branch that lacks them.

## Open questions for the owner (recommended option taken)

1. None new. `identifySeconds` default 120 is carried from 2026-09-26.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0645/` in the final PR unless the owner wants it kept.
