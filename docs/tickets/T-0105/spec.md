# T-0105 crew migrate carries `autopilot` to crew.json's top-level `autopilot` and says which file crew reads          status: spec   risk: low
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md or plan.md. Written against origin/main `155fe6d8` (crew 1.0.322). The direction is settled in direction.md, "Direction check 2026-10-04", option 1, taken under the owner's standing authority because the owner was not available. This spec is slice 1 of 2: the sabotage rows are `children/1` (a tooling-only PR).

## Intent
`/crew:migrate` stops reporting a config's `autopilot` block as unmapped. The block lands at crew.json's top-level `autopilot`, and the preview, the apply report and crew.json `notes` each say that crew reads this key from `.crew/config.json` and does not read the crew.json copy. A user who opens crew.json to change autopilot is told where the edit takes effect.

## Exclusions
- Crew does not start reading `autopilot` from crew.json. `crew_autopilot.py` is not edited.
- No other key is remapped. `resume`, `shellRoute`, `cloud`, `environments`, `scope`, `tickets` and `route` stay under `unmapped`.
- No rewrite of a crew.json an older crew already wrote. Apply still never overwrites: a crew.json holding `unmapped.autopilot` is a CONFLICT on a re-run, as any differing target is today (`crew_migrate.py:459-461`).
- No change to the `retireable .crew/config.json` line, to `to_legacy`'s contract, to `CREW_SCHEMA` or to `LEGACY_SCHEMA_MAX`.
- No edit to `plugin/crew/tests/sabotage*.py` (harness; that is L-0683). No new verify rule (T-0038 adds the migrate rule).
- No hook, no new setting.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_migrate.py:90-117 `MAPPING`, 26 rows, none for `autopilot`. :26-37 the docstring rule ("A key this table does not name is carried whole under `unmapped.<key>`") and "Today that is one case". :39-66 the docstring table. :68 "a test asserts the two agree".
- plugin/crew/hooks/scripts/crew_migrate.py:269-292 `to_crew`; the unmapped carry is :286-288. :295-301 `migration_notes`, one note today. :126-127 `AUTOPILOT_NOTE`. :304-313 `to_legacy`. :469-473 `build_plan` refuses when the mapping does not round-trip and copies `crew["notes"]` into the plan. :535-538 `render_plan` prints `note` and `unmapped` lines.
- Measured: `to_crew({"schema": 7, "tracker": "files", "autopilot": {"mode": "off", "maxPhases": 12, "deploy": "none"}})` returns `unmapped == ["autopilot"]` and crew.json `"unmapped": {"autopilot": {...}}`.
- plugin/crew/hooks/scripts/crew_autopilot.py:791 `settings` reads `crew_config.resolve_config(top).get("autopilot")`, which is config.json. :814-818 the warning for a top-level crew.json `autopilot` with none in config.json. Measured: it fires for top-level with config.json removed, and never for `unmapped.autopilot` (table in direction.md).
- plugin/crew/hooks/scripts/crew_config.py:394 `autopilot` is a key of the 1.0 repo config template. plugin/crew/hooks/scripts/crew_state.py:179 `SCHEMA_CURRENT = 7`, so a 1.0 config.json is inside migrate's accepted range.
- plugin/crew/CONFIG.md:2610-2616 "Which file": crew.json is not read for this key. plugin/crew/README.md:917 says the same.
- plugin/crew/commands/migrate.md:21 (the `unmapped` bullet), :24-26 (the `note` bullet), :67-69 (points at the docstring table).
- plugin/crew/tests/test_migrate.py:263-274 `test_unknown_config_keys_are_preserved_and_reported`; :309-312 `test_mapping_table_in_docstring_matches_code` (regex ``^\| `(\w+)`\s+\| `([\w.]+)` `` over the docstring); :415-422 and :425-438 the note tests, the second asserting no `notes` key and no `autopilot` in the output for the fixture; :441-456 the round-trip and wording tests.
- plugin/crew/tests/migrate_fixtures/config.json has no `autopilot` key (`grep -c autopilot` prints 0), so the existing note tests keep passing unchanged.
- No sabotage row anchors on the lines this ticket edits: `git grep -n "AUTOPILOT_NOTE\|migration_notes\|MAPPING" origin/main -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS`; :79 `plugin/crew/tests/sabotage*.py`. `crew_migrate.py`, `test_migrate.py` and `commands/migrate.md` are not in it.
- .crew/verify.json names `crew_migrate.py` only in the crew-standards rule (:438); no rule runs `test_migrate.py` on its own.
- docs/handoff/cloud/T-0105.md "Cleanup (required)": delete that file and its row in docs/handoff/cloud/README.md (:27) in this ticket's PR.

## Unknowns
- Whether the owner wants crew to read `autopilot` from crew.json instead (direction.md option 3). Default taken: no.
- Whether the seven sibling keys get the same treatment. Default taken: not here; each needs its reader checked first.
- Repos migrated by an older crew keep `unmapped.autopilot`, and a re-run of `/crew:migrate` there now reports a CONFLICT on crew.json where it used to say `already migrated (identical)`. Accepted and documented in migrate.md and the CHANGELOG entry: roll back with the backup directory, or leave it. Not resolved: how many such repos exist.
- T-0038 edits the same file. Whichever lands second merges main and re-runs `test_migrate.py`; no behavioural overlap is expected (T-0038 changes `_load_legacy` and the upgrade path, not `MAPPING`).
- The crew patch version is set at implement time, one past origin/main's.

## Design
- `MAPPING` gains a last row `("autopilot", "autopilot")`. The docstring table gains the matching last row, its Note cell saying the key is read from `.crew/config.json` only.
- A new constant `AUTOPILOT_FILE_NOTE`: one line that names `autopilot`, says the copy in crew.json is not read, and names `.crew/config.json` as the file to edit.
- `migration_notes` returns the PM-authority note first when it applies, then `AUTOPILOT_FILE_NOTE` when the key `autopilot` is present in the legacy dict, whatever its value. `to_legacy` still never reads `notes`.
- The docstring sentence "Today that is one case" names both cases.
- Nothing else moves. The value is carried whole and unvalidated, as every mapped key is.

## Size and split
- Estimate: about 12 added production lines, all in `plugin/crew/hooks/scripts/crew_migrate.py`. No new parser, guard or state machine.
- Split for the harness rule only. Slice 1 is this spec (feature, tests, docs). Slice 2 is `children/1`: two sabotage rows in `plugin/crew/tests/sabotage_migrate.py`, a tooling-only PR, after this one merges.
- plan.md: none exists.

## Touch
- plugin/crew/hooks/scripts/crew_migrate.py
- plugin/crew/tests/test_migrate.py
- plugin/crew/commands/migrate.md
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json
- plugin/PLUGINS.md
- CHANGELOG.md
- .crew/codemap/crew.md
- `docs/handoff/cloud/T-0105.md` - deleted
- `docs/handoff/cloud/README.md` - the T-0105 row removed

Not in Touch, stated: `docs/guides/crew/src/*.md` and the rebuilt HTML, DOCX and PDF (no guide states the key mapping; `git grep -n unmapped origin/main -- docs/guides/crew/src` prints nothing; the PR body says `Docs: guides none - no guide describes the crew.json key table`); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact); `plugin/crew/hooks/scripts/crew_autopilot.py`; `plugin/crew/tests/sabotage_migrate.py` (L-0683); `.crew/verify.json`.

## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper.
- [ ] A config with `"autopilot": {"mode": "off", "maxPhases": 12, "deploy": "none"}` migrates to crew.json with that value at top-level `autopilot`, no `unmapped` key, and no `unmapped  config key 'autopilot'` line in the output. `python3 -m pytest plugin/crew/tests/test_migrate.py -q -k test_autopilot_key_lands_at_top_level_not_unmapped`
- [ ] The same run prints one `note` line that contains `autopilot` and `.crew/config.json`, and crew.json `notes` equals `[crew_migrate.AUTOPILOT_FILE_NOTE]`. Preview prints the same line and writes nothing. `-k test_autopilot_key_note_names_config_json`
- [ ] Round trip: `to_legacy(to_crew(cfg)[0]) == cfg` for `autopilot` values `{"mode": "plan"}`, `{}`, `"plan"`, `null` and `12`; each still gets the note. `-k test_autopilot_key_round_trips_whatever_its_value`
- [ ] A config with both `pm.authority: autonomous` and an `autopilot` key gets both notes, PM note first. `-k test_autonomous_pm_and_autopilot_key_give_both_notes_in_order`
- [ ] A config with `autopilot` and an unknown `futureKey` carries only `futureKey` under `unmapped`. `-k test_unknown_key_beside_autopilot_is_still_unmapped`
- [ ] After apply, with `.crew/config.json` then removed, `crew_autopilot.settings(repo)["warnings"]` contains the line naming `.crew/crew.json`. `-k test_migrated_autopilot_is_reported_by_settings_once_config_json_is_gone`
- [ ] A crew.json holding the old `unmapped.autopilot` shape is a CONFLICT on re-run: exit 1 and no byte changed. `-k test_crew_json_from_an_older_mapping_is_a_conflict_and_is_left_intact`
- [ ] The existing tests pass unchanged, in particular `test_mapping_table_in_docstring_matches_code`, `test_non_autonomous_pm_authority_adds_no_note`, `test_unknown_config_keys_are_preserved_and_reported` and `test_second_apply_is_a_no_op`. `python3 -m pytest plugin/crew/tests/test_migrate.py -q`
- [ ] `plugin/crew/commands/migrate.md` names the autopilot note in its `note` bullet and says a crew.json from an older crew is a conflict on re-run; `plugin/crew/CONFIG.md` "Which file" and `plugin/crew/README.md`'s autopilot settings paragraph say migrate carries the block to crew.json's top-level `autopilot` with a note. `git grep -n "AUTOPILOT_FILE_NOTE\|top-level .autopilot." -- plugin/crew/commands/migrate.md plugin/crew/CONFIG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_migrate.py`
- [ ] `docs/handoff/cloud/T-0105.md` is gone and `docs/handoff/cloud/README.md` has no T-0105 row. `test ! -e docs/handoff/cloud/T-0105.md && ! grep -q "T-0105" docs/handoff/cloud/README.md`
- [ ] The crew version is one patch past origin/main's in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a CHANGELOG entry heading in the current shape (`CHANGELOG.md:7`). Commit, then `python3 scripts/check-marketplace.py`
- [ ] The PR is feature-only. `python3 scripts/check-tooling-pr.py` exits 0 and `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- [ ] No new ruff or pylint findings against the merge-base. `python3 -m ruff check plugin/crew/hooks/scripts/crew_migrate.py plugin/crew/tests/test_migrate.py` and `python3 -m pylint plugin/crew/hooks/scripts/crew_migrate.py plugin/crew/tests/test_migrate.py`
- [ ] The full crew suite passes. `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"` then `python3 -m pytest plugin/crew/tests/ -q -m wallclock`

## Dependencies
Must land first:
- T-0004 (merged): `/crew:autopilot` and the `autopilot` config block this ticket maps.
- T-0010 (merged): `autopilot.approval` and `autopilot.questions`, and the "Which file" paragraph this ticket extends.
- T-0088 (merged): `crew_common.repo_config_file`, which the `settings` warning reads through.

Not a dependency, same file:
- T-0038 (approved, not started): folds `/crew:upgrade` into migrate and adds the migrate verify rule. Either order; the second to land merges main.
- T-0500 (approved): leaves `crew_migrate.py` alone by design.

Blocks:
- L-0683 (the sabotage rows).

Siblings from the same report, independent: T-0104 (approved), T-0106 (direction), T-0107 (done), T-0108 (direction).

## Open questions for the owner
1. Should crew read `autopilot` from crew.json after a migrate, instead of only saying it does not? Default taken: no (recommended; it changes which file arms a driver).
2. Should the seven other live keys that land under `unmapped` (`resume`, `shellRoute`, `cloud`, `environments`, `scope`, `tickets`, `route`) get rows too? Default taken: not in this ticket; recommended as one follow-up ticket that checks each key's reader first.
3. Migrate calls `.crew/config.json` "retireable" while crew still reads most settings from it. Should that line change? Default taken: untouched here; recommended as part of the two-file follow-up.
4. Is L-0683 (two sabotage rows, tooling-only PR) wanted for a non-guard change? Default taken: yes, kept small.

## Split
- L-0683 (child 1 of T-0105, filed 2026-10-04): sabotage rows for migrate's autopilot mapping and note (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
