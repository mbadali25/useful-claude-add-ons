# Cloud handoff: L-0682

**Sabotage entries for the config leaf checks, `os_error_text` and the delete fixes (tooling PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Needs T-0103 merged first.** **Tooling PR: it edits `plugin/crew/tests/sabotage_config.py`, a review/gate harness path, so it lands alone with no production code.**

- **Role:** child ticket, split from T-0103, slice 1 of 1.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0682-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0682/direction.md`, `docs/tickets/L-0682/spec.md`
- **Size:** 0 production lines outside the harness. About 60 lines in `sabotage_config.py` (nine entries) and about 90 lines of tests. **Touches a harness path.** Risk is marked low in the spec. One PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0103 | open, not built (handed off 2026-10-04) | Four of the nine entries anchor lines and name tests T-0103 adds, and T-0103 moves `apply_delete`'s handler text, so the delete-site `os_error_text` entry is written against the merged code. Must be merged first. |
| T-0075 | done (merged as PR #258) | The code under test. |
| T-0087 | merged | Defines this PR's shape: tooling lands alone; tests, code map and version files ride along. |

This ticket blocks nothing.

Per the spec, five of the nine entries (the two leaf entries and the machine-writer and repo-writer `os_error_text` entries, plus the delete-site one once the handler text is final) do not need T-0103's new tests, but the ticket is one PR and waits for T-0103.

Family order:

1. T-0103: the feature PR (`apply_delete`, `widening_note`, the `with`-block rewrite).
2. L-0682 (this ticket).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and T-0103 edits `apply_delete` and `widening_note`; re-read every cited line after T-0103 merges.
- No plan.md is published. The implementing session writes the plan.
- The backslash-filename test is designed, not run. Confirm it with the first new test before writing the entries. If it does not hold, stop: the fallback (a Windows-only record outside the tuple) needs the owner.
- Re-run the two leaf mutations; an entry that prints `STILL GREEN` means its named test needs another parameter, which is a test edit inside this PR.
- If T-0103 found the `widening_note` finding not real, omit that entry and say so in the PR body.
- No edit to `plugin/crew/tests/sabotage.py` (at its module-line limit). Entries go in `sabotage_config.py`.
- No production code: nothing under `plugin/crew/hooks/scripts/` changes. Nothing outside `HARNESS` plus `ALONGSIDE` in `scripts/check-tooling-pr.py`.
- The PR body names each leg of the harness rule as run or not run, and carries `Docs: none beyond the code map - sabotage entries and tests only`.
- The heavy-run wrapper the spec names is a local tool of the original host; the cloud session uses its own equivalent.

## Open questions for the owner (recommended option taken)

1. The `os_error_text` sabotage is made red on every platform through a backslash-filename test. Alternative: keep it Windows-only and record the evidence outside the tuple, which needs a harness change or a hand-kept record.
2. Relabelling the existing entry whose label says "object at a leaf" but mutates the `under` branch: allowed here and optional. Whether to do it: could not tell from the files; left to the implementing session.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0682/` in the final PR unless the owner wants it kept.
