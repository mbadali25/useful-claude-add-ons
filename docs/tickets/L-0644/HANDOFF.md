# Cloud handoff: L-0644

**`crew_ghdeploy.py prepare`: refuse or snapshot before a GitHub Actions dispatch**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs T-0045 and T-0009 (PR #336) merged first.

- **Role:** child, split from T-0045, slice 1 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0644-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0644/direction.md`, `docs/tickets/L-0644/spec.md`
- **Size:** about 140 production lines in `plugin/crew/hooks/scripts/crew_ghdeploy.py`. One fail-closed sequence. No harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0045 | direction, handed off (branch `T-0045-build`, draft PR #407), not built | The `github` entry, its validator, the canonical dispatch text and `check`, which `prepare` builds on. |
| T-0009 | in progress (PR #336, open on 2026-10-04, not on main) | The dispatch classifier (`crew_guards.dispatch_scopes`, `dispatch_environment`) that `prepare` calls read-only. |
| T-0005 | merged | The environment layer. Named in the direction; not in the facts file's list. |

The facts file lists T-0045 and T-0009. The direction adds T-0005, which is merged, so nothing changes in practice.

**This ticket blocks:** L-0645 (reads the state file `prepare` writes), and through it L-0646, L-0647 and L-0649.

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
- T-0009's function names and return shapes were read from branch `T-0009-deploy-guard` at `f08ae7fb`, not from main. Re-read `crew_guards.py` on origin/main after PR #336 merges.
- `prepare` never dispatches and makes no mutating `gh` call. `test_helper_never_dispatches` pins it.
- No copy of T-0009's classifier, and no edit to `cloud_guard.py` or `crew_guards.py`. If the merged API cannot be called read-only, stop and amend the spec first.
- Write the state file through a temp file and `os.replace` (CLAUDE.md landmine: `open(p, "w")` truncates at open time).
- No edit to `plugin/crew/tests/sabotage*.py` (harness). Mutations go in `ghdeploy_mutations.py`.
- Every slice from T-0045 to L-0649 adds to `crew_ghdeploy.py`, `test_crew_ghdeploy.py` and `ghdeploy_mutations.py` (where listed in Touch). Build on what the earlier slices merged; do not start a slice on a branch that lacks them.

## Open questions for the owner (recommended option taken)

1. If T-0009 has not merged when this is picked up: wait (taken), or land `prepare` without the two classification refusals and add them in a follow-up?
2. Carried from the parent: no correlation input is required in the consumer's workflow; `correlationInput` stays optional.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0644/` in the final PR unless the owner wants it kept.
