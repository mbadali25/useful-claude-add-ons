# L-0683 direction - sabotage rows for migrate's autopilot mapping and note

Split from T-0105. Status: direction, taken under the owner's standing authority on 2026-10-04 (owner not available).

## Why this is its own ticket
T-0105 adds a `MAPPING` row and a note to `plugin/crew/hooks/scripts/crew_migrate.py`, with tests in `plugin/crew/tests/test_migrate.py`. The mutations that prove those tests bite belong in `plugin/crew/tests/sabotage_migrate.py`, which matches `plugin/crew/tests/sabotage*.py` in `HARNESS` (`scripts/check-tooling-pr.py:79` at origin/main `155fe6d8`). A harness change lands alone, with no feature work in the same PR, so the rows cannot ride in T-0105's PR.

## Direction
Two rows appended to `MIGRATE_FIX_MUTATIONS`, each turning one of T-0105's named tests red through `plugin/crew/tests/sabotage.py`'s runner:
1. The `autopilot` row removed from `MAPPING`, so the key falls back under `unmapped`.
2. `migration_notes` no longer returning the autopilot file note.

## Options considered
1. **Recommended, taken: two rows, tooling-only PR after T-0105 merges.**
2. No rows. The change is not a guard, so the repo's sabotage rule does not strictly require them. Rejected as the default: the note is the only thing that tells a user which file is read, and a silent regression there reproduces the original report.
3. Rows in T-0105's own PR. Not allowed by the harness rule.

## Depends on
T-0105 merged. The anchors are lines T-0105 writes.
