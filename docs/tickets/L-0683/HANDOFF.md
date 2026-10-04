# Cloud handoff: L-0683

**Sabotage rows for migrate's autopilot mapping and note (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Needs T-0105 merged first.** **Tooling PR: it edits `plugin/crew/tests/sabotage_migrate.py`, a review/gate harness path, so it lands alone with no production code.**

- **Role:** child ticket, split from T-0105, slice 1 of 1.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0683-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0683/direction.md`, `docs/tickets/L-0683/spec.md`
- **Size:** 0 production lines. About 20 lines in `plugin/crew/tests/sabotage_migrate.py` (two rows). **Touches a harness path.** Risk is marked low in the spec. One PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0105 | open, not built (direction; handed off 2026-10-04) | Adds the `MAPPING` row, the `migration_notes` line and the two tests these rows anchor on and name. Must be merged first. |

This ticket blocks nothing.

Family order:

1. T-0105: the feature PR in `crew_migrate.py`.
2. L-0683 (this ticket).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`). The anchors are lines T-0105 adds, so read them on main after T-0105 merges; each anchor must match exactly one place in `crew_migrate.py`.
- No plan.md is published. The implementing session writes the plan.
- No production code and no new test. The rows name tests T-0105 adds (`test_autopilot_key_lands_at_top_level_not_unmapped`, `test_autopilot_key_note_names_config_json`). If a named test is missing on main, stop and report; do not write it here.
- No edit to `plugin/crew/tests/sabotage.py` (at its module-line limit); it already imports `MIGRATE_FIX_MUTATIONS`.
- Removing the `MAPPING` row may also turn `test_mapping_table_in_docstring_matches_code` red. The spec expects that and calls it harmless.
- The PR body carries `Docs: none - two sabotage rows, no behaviour a document describes`.
- The heavy-run wrapper the spec names is a local tool of the original host; the cloud session uses its own equivalent.

## Open questions for the owner (recommended option taken)

1. Are two sabotage rows wanted for a change that is not a guard? Default taken: yes, as a small tooling-only PR. Alternative: no rows (the repo's sabotage rule does not strictly require them here).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0683/` in the final PR unless the owner wants it kept.
