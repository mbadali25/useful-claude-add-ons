# Cloud handoff: L-0650

**wire the GitHub-deploy mutations into the sabotage harness (tooling only)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable yet: it needs T-0045 merged first. This is a harness change: it lands alone as a tooling-only PR.

- **Role:** child, split from T-0045, slice 7 of 7 (T-0045 itself is the first landing, so the family has eight).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0650-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0650/direction.md`, `docs/tickets/L-0650/spec.md`
- **Size:** zero production lines. Two edited lines in `plugin/crew/tests/sabotage.py`, net growth zero. **Touches a review/gate harness path** (`plugin/crew/tests/sabotage*.py`), so it lands alone as a tooling-only PR: no feature, no production code, no prompt.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0045 | direction, handed off (branch `T-0045-build`, draft PR #407), not built | Creates `plugin/crew/tests/ghdeploy_mutations.py` and `GHDEPLOY_MUTATIONS`, which this ticket imports. |

The facts file lists T-0045 only, and the spec agrees. Children that have landed by then add entries to the same tuple; this ticket imports it by name, so it lands once and later entries are picked up.

**This ticket blocks:** Nothing. Until it lands, the full `sabotage.py` run does not include the ghdeploy mutations.

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
- `sabotage.py` is 3400 lines and `.pylintrc` sets `max-module-lines=3400`. The import and the tuple term are joined onto existing lines so the count does not grow.
- A harness change runs the harness rule in `.crew/verify.json`: `scripts/check-tooling-pr.py`, its suite, the golden replay, the seam contracts and the canary review. The PR body names which of those ran and which did not.
- No new or changed mutation entries, no rename of `ghdeploy_mutations.py`, no wiring of `promote_tree_mutations.py` (that is L-0564's).
- A full `sabotage.py` run is heavy and has been killed part-way on the owner's host. Run the ghdeploy family alone for the acceptance check and report whether the full run was attempted.
- The PR body states `Docs: none - test harness wiring, no behaviour a document describes`.

## Open questions for the owner (recommended option taken)

1. Land it right after T-0045 (taken, so every later child's mutations are in the full run from the start) or after the last child?
2. `sabotage.py` is at the 3400-line pylint limit. Taken: the import and the tuple are joined onto existing lines so the count does not grow.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0650/` in the final PR unless the owner wants it kept.
