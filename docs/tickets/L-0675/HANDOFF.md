# Cloud handoff: L-0675

**T-0083 child 1: crew passes the repo's project to vault recall and falls back cleanly on an older CLI**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until T-0083 has merged: T-0083 adds the `--project` option this ticket passes.

- **Role:** child ticket, split from T-0083, slice 1 of 2 children (slice 2 of the family's 3, counting the parent's own slice).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0675-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0675/direction.md`, `docs/tickets/L-0675/spec.md`
- **Size:** about 70 production lines (`crew_recall.py` about 55, `crew_context.py` about 10, `crew_config.py` and the config template about 5).
- **Harness:** no. This is a feature PR and must contain no harness path. The sabotage mutations for it are L-0676, a separate tooling-only PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0083 | direction, spec ready, not built | Must merge first. It adds `--project` to the obsidian-vault CLI. Without it this slice ships only the fallback path and the end-to-end test skips. |
| T-0088 | merged | Linked worktrees read the main checkout's repo config, where `memory.recall.projects` lives. |
| T-0087 | merged | The rule that keeps the sabotage mutations out of this PR. |

The ticket facts and the spec agree on these three.

This ticket blocks L-0676.

Family order:
1. T-0083 (parent, feature PR, obsidian-vault only)
2. L-0675 (this ticket), after T-0083 has merged
3. L-0676 (tooling-only PR), after this ticket has merged

## Read before writing code

- Read T-0083's spec.md first: it defines `--project` in the CLI.
- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. The implementing session writes the plan.
- The spec was not approved by the owner in person; the recommended options were taken.
- No ranking, filtering or scoring in crew, and no file under `plugin/obsidian-vault/` changes.
- Do not edit `plugin/crew/tests/sabotage_context.py` or any other harness path. Keep the existing sabotage anchors in `crew_recall.py` unchanged (the sort line and the `label` line the spec cites at :209 and :215).
- `test_a_broken_cli_is_a_logged_miss_not_a_failure` compares the whole recall record with `==`; the two new keys change that expectation, in the same commit.
- A new config leaf changes the pinned leaf counts (130 and 58 at the spec's base) in `test_crew_config.py` and `CONFIG.md`. Use the measured values, not the spec's.
- Both runs of the retry share one time budget; only exit 2 is retried.

## Open questions for the owner (recommended option taken)

1. Default project name: the main checkout's directory name (taken), or nothing until the repo sets `memory.recall.projects`?
2. On an older CLI that rejects `--project`: retry once without it (taken), or log the miss and inject nothing?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0675/` in the final PR unless the owner wants it kept.
