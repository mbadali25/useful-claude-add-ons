# Cloud handoff: T-0045

**crew runs GitHub Actions deployments, slice 1: the `github` entry in `.crew/verify.json` and `crew_ghdeploy.py check`**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent of a split family. T-0045 itself is now slice 1 only. Its children are L-0644, L-0645, L-0646, L-0647, L-0648, L-0649 and L-0650, each published on its own branch (`<id>-build`) with its own draft PR. The spec's `children/` folder is not published; the children's own PRs carry their files.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority high.
- **Branch:** `T-0045-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0045/direction.md`, `docs/tickets/T-0045/spec.md`
- **Size:** about 170 production lines, all in the new `plugin/crew/hooks/scripts/crew_ghdeploy.py`. No harness path. Mutations go in the new, unwired `plugin/crew/tests/ghdeploy_mutations.py`; wiring them into `sabotage.py` is L-0650.

## Dependencies and work order

Slice 1 (this ticket) needs nothing that is not already on main. It can be worked at any time.

| Ticket | State | Why |
|---|---|---|
| T-0005 | merged | The environment layer (`environments.nonProd`, `prodUnattended`) the later slices classify against. No code dependency for slice 1. |
| T-0505 | merged (PR #296) | promote-gate judges the tree the deploy runs from and requires a literal sha to be HEAD. Slice 1's printed dispatch relies on that match. |
| T-0072 | merged (PR #250) | `autopilot.deploy` and `deploy_allowed` are already on main, so this ticket no longer adds the key. Consumed by L-0649. |

Needed by children, not by this ticket:

| Ticket | State | Needed by | Why |
|---|---|---|---|
| T-0009 | in progress (PR #336, open on 2026-10-04) | L-0644, L-0649 | The dispatch classifier and the `deployWorkflow` guard. Not on main. |
| T-0011 | approved, not built on main | L-0649 | Autopilot's ship phase. |
| T-0062 | ready, handed off (branch `T-0062-build`), itself blocked on T-0009 | L-0648 | Edits the same two promote-gate files; L-0648 lands after it. |
| L-0564 | direction | L-0648, L-0650 | Same files. Ordering only: whichever lands second merges main. |

T-0062's spec lists T-0045 among the tickets it blocks ("`/crew:promote` dispatching workflow runs relies on the gate recognising a dispatch"). This ticket's own spec says slice 1 has no unmerged dependency: `check` dispatches nothing. This spec wins for slice 1; inside this family T-0062 is an ordering constraint on L-0648 only.

**This ticket blocks:** every child (L-0644 to L-0650), and T-0053 and T-0051.

**Order of the family:**

1. T-0045 (this ticket): the `github` entry and `check`.
2. L-0650: tooling-only PR that wires `ghdeploy_mutations.py` into the sabotage harness. Default is right after this ticket; it lands alone.
3. L-0644 `prepare`: after T-0045 and T-0009.
4. L-0645 `identify`: after L-0644.
5. L-0646 `watch`: after L-0645.
6. L-0647 `record` and the `/crew:promote` sequence: after L-0644, L-0645 and L-0646.
7. L-0648 promote-gate reads the `github` entry: after T-0045 and T-0062. It does not need L-0644 to L-0647, so it can land any time after those two.
8. L-0649 autopilot's deploy phase: last. After T-0011, T-0009, and L-0644 to L-0648.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A plan.md from 2026-09-26 exists locally and is stale: it does not match the refreshed spec and is not published. The implementing session writes the plan. The spec says "re-plan this slice from plan.md Step 1" and "the design decisions in plan.md 'Design' are kept"; that text is not available here. What the spec, the direction and the children's specs restate of the design is what you have. Where a design detail is not in those files: could not tell, ask the owner.
- `check` calls no `gh` command and writes nothing. `test_check_calls_no_gh` pins it.
- Do not edit `plugin/crew/commands/promote.md` (at its 380-line allowance; the sequence prose lands with L-0647), any `plugin/crew/tests/sabotage*.py` (harness, L-0650), `crew_config.py`, the config templates or `autopilot.*`.
- The pre-existing part of direction.md named the first consumer repository, its local path and its workflow file. Those were replaced with generic wording for publication; nothing else in the text was changed.
- The direction's two "Owner decision 2026-09-30" sections describe the owner's local host (a wrapper script, a worker cap). A cloud session follows the merge-not-rebase rule and the repo's own `.crew/verify.json` commands; the local wrapper does not exist there.
- No pytest, sabotage or gate was run when the spec was refreshed. The evidence is `path:line` reads plus gh 2.46.0 help text.

## Open questions for the owner (recommended option taken)

1. Is cutting T-0045 into eight landings (this ticket plus seven children) acceptable? Taken: yes.
2. Fold L-0648 (promote-gate reads the `github` entry) into T-0062, which edits the same two gate files? Taken: keep it separate, land it after T-0062.
3. `promote.md` is at its 380-line allowance. Taken: the github sequence goes in a new crew-verification sibling file (`github-deploy.md`) and promote.md points to it with no net growth. Alternative: raise the allowance, as was done for T-0505.
4. T-0072's `autopilot.deploy: all` can allow production, but the 2026-09-26 direction says autopilot never deploys to production. Taken: L-0649 follows `deploy_allowed` exactly, so production runs only under T-0072's two-layer opt-in.
5. `autopilot.md` is 109 lines against a tested cap of 110. Taken: L-0649 rewords the existing "No deploy" sentence in place and puts detail in `crew_autopilot.py` output.
6. If T-0009 (PR #336) has not merged when L-0644 is picked up: wait (taken), or land `prepare` without the two classification refusals and add them later?
7. Land L-0650 (tooling-only mutation wiring) right after slice 1 (taken) or after the last child? `sabotage.py` is at the 3400-line pylint limit, so the edit must be net-zero lines.
8. `github` as one object or a list. Taken: either, normalised to a list.
9. Carried from 2026-09-26 with defaults unchanged: no correlation input is added to the consumer repository; rollback is not automated; `watchMinutes` 60 and `identifySeconds` 120; a pass with no `deployJob` configured is recorded as "deploy job not checked".

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0045/` in the final PR unless the owner wants it kept.
