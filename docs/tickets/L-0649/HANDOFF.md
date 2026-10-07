# Cloud handoff: L-0649

**autopilot's deploy phase: promote to the first nonProd GitHub environment after the merge**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it is the last slice and needs T-0011, T-0009 and L-0644 to L-0648 merged first.

- **Role:** child, split from T-0045, slice 6 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0649-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0649/direction.md`, `docs/tickets/L-0649/spec.md`
- **Size:** about 140 production lines in `plugin/crew/hooks/scripts/crew_autopilot.py`. One fail-closed state machine. No `HARNESS` path, but `crew_autopilot.py` and `commands/autopilot.md` are `SEAM` files, so this PR must change no `HARNESS` path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0011 | approved, not built on main | The ship phase that reports the PR merged; the deploy phase hooks in after it. |
| T-0009 | in progress (PR #336, open on 2026-10-04, not on main) | The classifier that gives the dispatch's class, and the guard that judges every dispatch. |
| T-0072 | merged (PR #250) | `autopilot.deploy` and `deploy_allowed`, which this phase consumes. |
| T-0045 | direction, handed off (branch `T-0045-build`, draft PR #407), not built | The `github` entry. |
| L-0644 | direction, handed off, not built | `prepare`. |
| L-0645 | direction, handed off, not built | `identify`. |
| L-0646 | direction, handed off, not built | `watch`. |
| L-0647 | direction, handed off, not built | `record` and the `/crew:promote` github sequence this phase names. |
| L-0648 | direction, handed off, not built | promote-gate's sha-input rule. |

The facts file lists T-0011, T-0009, T-0072 and "T-0045 child 1 to 5" (L-0644 to L-0648). The direction also names T-0045 itself, which those children already need.

**This ticket blocks:** Nothing in this family. The parent T-0045 blocks T-0053 and T-0051; whether those wait on this slice in particular: could not tell.

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
- T-0011 is not on main, so the hook point in `crew_autopilot.py` cannot be anchored yet. Re-read `crew_autopilot.py` on origin/main after T-0011 lands and re-anchor.
- T-0009's classifier was read from branch `T-0009-deploy-guard` at `f08ae7fb`. Re-read after PR #336 merges.
- `next` is read-only: autopilot runs no `gh` command and calls no `crew_ghdeploy.py` subcommand. It names `/crew:promote <env>`.
- Proceed only on the exact verdict `allow` from `deploy_allowed`, and print every non-empty `report`.
- `autopilot.md` is 109 lines against a tested cap of 110, and every stop slug must appear in it in backticks.
- Other open tickets edit `crew_autopilot.py` (the T-0027 handoff names T-0019/L-0611, T-0029 and T-0049). Whichever lands second merges main.
- Touch includes `docs/guides/crew/src/daily-workflow.md` and the rebuilt guide outputs. Whether the cloud environment can rebuild DOCX and PDF: could not tell.
- No edit to `plugin/crew/tests/sabotage*.py` (harness). Mutations go in `ghdeploy_mutations.py`.

## Open questions for the owner (recommended option taken)

1. T-0072's `all` can allow production; the 2026-09-26 direction said autopilot never deploys to production. Taken: follow `deploy_allowed` exactly and proceed only on `allow`, so production needs T-0072's opt-in in both config layers. Alternative: hard-code nonProd only in this phase.
2. `autopilot.md` has one line left under its tested cap of 110. Taken: reword section 4's existing "No deploy" sentence in place; all detail goes in `crew_autopilot.py` output.
3. Which sha: the reviewed HEAD, which must equal the merged PR's head. Carried from 2026-09-26.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0649/` in the final PR unless the owner wants it kept.
