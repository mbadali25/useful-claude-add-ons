# Cloud handoff: L-0635

**Sabotage mutations for cross-session contracts and dependencies (tooling PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: cannot start until T-0031, L-0633 and L-0634 are merged to main** (and, through them, T-0030 and T-0029). The source lines the mutations anchor on do not exist yet.

- **Role:** child ticket, split from T-0031, slice 3 of 3 (the other children are L-0633 and L-0634).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0635-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0635/direction.md`, `docs/tickets/L-0635/spec.md`
- **Size:** 0 production lines. About 170 lines of mutations in a new `plugin/crew/tests/sabotage_contract.py` and 2 lines in `plugin/crew/tests/sabotage.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a harness path, so this lands alone as a tooling-only PR: tests, docs and version files may ride along, production code and prompts may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0031 | ready (PR in this hand-off) | `crew_contract.py` and its must-block tests. |
| L-0633 | direction (PR in this hand-off) | The dependency parser in `crew_wave.py`. |
| L-0634 | direction (PR in this hand-off) | `check_bindings` and the wave refusal. |
| T-0030 | in-progress, not on main, not in this hand-off | Needed through the three above. |
| T-0029 | in-progress, not on main, not in this hand-off | Needed through the three above. |

This ticket blocks nothing. T-0032 does not wait for it.

Order of the whole family:

1. T-0030 and T-0029 land on main (neither is part of this hand-off).
2. T-0031: the contract record and its freeze rule.
3. L-0633: `<channel>:<id>` dependencies in the wave.
4. L-0634: the wave refuses a built-against hash mismatch.
5. L-0635 (this ticket): the sabotage mutations for all three. Last.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan, after the three feature PRs merge. Each mutation is anchored on a line of the landed feature code, not on this spec.
- No production code and no prompt: nothing under `plugin/crew/hooks/`, `plugin/crew/commands/`, `plugin/crew/agents/`, `scripts/` or `skills/`. If a mutation shows a guard does not hold, the fix is a new feature ticket, not an edit here.
- In `sabotage.py`, only the import and the `MUTATIONS +=` registration line change. `.pylintrc` caps a module at 3400 lines. The spec for L-0638 measured `sabotage.py` at exactly 3400 lines; this spec says only "over 3000". Measure it on main before adding a line.
- A mutation that stays green is a finding, not a pass. The count of red mutations must equal the count registered.
- Running the sabotage suite is heavy. The spec sends it through the gate runner's heavy-run path, never as several copies at once. Whether the cloud session has that path: could not tell.
- Whether the harness rule's own suite needs the new module listed is not known; the spec resolves it by running `python3 scripts/check-tooling-pr.py` and `python3 scripts/_test/tooling-pr.py` on the branch.

## Open questions for the owner (recommended option taken)

1. One tooling PR after all three slices, or one after each? Taken: one.
2. May this PR add a missing must-block test to the three feature test files, as Touch allows, or should every gap go back to its slice as a new ticket? The spec records no taken answer. The facts recorded for this hand-off say "taken: it may add the test", which matches the spec's Touch list and Exclusions. The spec wins, so treat this one as open and ask the owner if it comes up.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0635/` in the final PR unless the owner wants it kept.
