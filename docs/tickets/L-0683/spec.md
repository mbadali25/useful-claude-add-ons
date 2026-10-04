# L-0683 sabotage rows for migrate's autopilot mapping and note          status: spec   risk: low
Split from T-0105. Written 2026-10-04 against origin/main `155fe6d8` (crew 1.0.322); the anchors below are lines T-0105 adds, so re-read them on main after T-0105 merges.

## Intent
`plugin/crew/tests/sabotage.py` proves that T-0105's tests catch the two regressions that would bring the report back: the `autopilot` key falling under `unmapped` again, and the note that names `.crew/config.json` going missing.

## Exclusions
- No production code. `crew_migrate.py`, `crew_autopilot.py` and every command file are not edited.
- No new test in `test_migrate.py`; the rows name tests T-0105 already added. If a named test is missing on main, stop and report, do not write it here.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140` `max-module-lines=3400`); it already imports `MIGRATE_FIX_MUTATIONS` (`sabotage.py:68`, used at `:3064`).
- No verify rule, no hook, no setting.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/tests/sabotage_migrate.py:13 `MIGRATE_FIX_MUTATIONS`, a tuple of `(label, file, anchor text, replacement text, test id)` rows; 120 lines; :9 `MIGRATE` is the path of `crew_migrate.py`. Row shape example at :16-24.
- plugin/crew/tests/sabotage.py:68 imports the tuple; :3064 appends it to `MUTATIONS`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (:79 `plugin/crew/tests/sabotage*.py`); :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, README, BUDGETS, the version files, `CHANGELOG.md`, `docs/**` and `.crew/codemap/**` ride along.
- No existing row anchors on `MAPPING`, `migration_notes` or `AUTOPILOT_NOTE`: `git grep -n "AUTOPILOT_NOTE\|migration_notes\|MAPPING" origin/main -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- T-0105's spec names the tests: `test_autopilot_key_lands_at_top_level_not_unmapped` and `test_autopilot_key_note_names_config_json`.

## Unknowns
- The exact anchor text. It is whatever T-0105 merged: the `("autopilot", "autopilot"),` row of `MAPPING` and the line in `migration_notes` that appends `AUTOPILOT_FILE_NOTE`. Each anchor must match exactly one place in `crew_migrate.py`.
- Whether removing the `MAPPING` row also turns `test_mapping_table_in_docstring_matches_code` red. Expected and harmless; the row still names the autopilot test.
- The crew patch version, set at implement time.

## Size and split
- 0 production lines. About 20 lines in `plugin/crew/tests/sabotage_migrate.py`. No further split.

## Touch
- plugin/crew/tests/sabotage_migrate.py
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json
- plugin/PLUGINS.md
- plugin/crew/BUDGETS.md
- .crew/codemap/crew.md
- .crew/codemap/verification-harness.md

Not in Touch, stated: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `docs/guides/crew/**`, `docs/diagrams/` (the PR body says `Docs: none - two sabotage rows, no behaviour a document describes`).

## Acceptance checks
Commands run from the repo root, through the heavy-run wrapper on a memory-bound host.
- [ ] `MIGRATE_FIX_MUTATIONS` has two more rows than on origin/main, each with an anchor that occurs exactly once in `crew_migrate.py`. `python3 - <<'PY'` importing `sabotage_migrate` from `plugin/crew/tests` and asserting `open(row[1]).read().count(row[2]) == 1` for the two new rows.
- [ ] Row 1 (the `MAPPING` row removed) turns `tests/test_migrate.py::test_autopilot_key_lands_at_top_level_not_unmapped` red, and the tree is restored byte-identical afterwards. `python3 plugin/crew/tests/sabotage.py` reports the row as caught; `git status --porcelain plugin/crew/hooks/scripts/crew_migrate.py` prints nothing.
- [ ] Row 2 (the note no longer returned) turns `tests/test_migrate.py::test_autopilot_key_note_names_config_json` red, same restore check.
- [ ] Every earlier mutation is still caught. `python3 plugin/crew/tests/sabotage.py` exits 0.
- [ ] The PR is tooling-only. `python3 scripts/check-tooling-pr.py` exits 0 and `python3 scripts/_test/tooling-pr.py` passes; `.crew/verify.json`'s harness rule runs (golden replay, seam contracts, canary review).
- [ ] The crew version is one patch past origin/main's in the three version files, with a CHANGELOG entry. Commit, then `python3 scripts/check-marketplace.py`
- [ ] No new ruff or pylint findings against the merge-base. `python3 -m ruff check plugin/crew/tests/sabotage_migrate.py` and `python3 -m pylint plugin/crew/tests/sabotage_migrate.py`

## Dependencies
Must land first:
- T-0105 (direction, spec written 2026-10-04): adds the lines and tests these rows name.

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
