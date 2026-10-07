# T-0103 config delete names the backup when a failure follows the move; T-0075 round-6 follow-up, part 1          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket (there was only direction.md). Written against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". No plan.md exists.

The direction's five items are split in two, because sabotage entries are review/gate harness and may not share a PR with production code (owner rule T-0087):
- **This ticket (feature PR):** direction item 2 (`apply_delete`), item 3 (the `with`-block rewrite), and round-6 NIT 2 (`widening_note`).
- **L-0682 (tooling PR, `children/1/`):** items 1 and 4, the sabotage entries for this ticket's two fixes, and the codemap mutation count.

## Intent
`crew_config_menu.py delete-repo --apply` tells the truth after an OS error. A failure before the file moved says the file is in place and names what failed (a lock, the machine file, the move). A failure after the file moved names the backup path and exits 1, never "left in place". A repo `null` that widens a ratcheted key is described by the value that ends up in force. `test_config_menu.py` reads and writes its fixtures through `with` blocks and drops its file-level pylint disable.

## Exclusions
- No edit to any `HARNESS` path (scripts/check-tooling-pr.py:58-87). In particular **no edit to `plugin/crew/tests/sabotage_config.py` or `sabotage.py`**. The new sabotage entries are L-0682.
- The three sabotage anchor lines inside `apply_delete` stay byte-identical, indentation included, so the existing entries keep working without a harness edit:
  - `            got = crew_config_files.move_aside(path, backup)` (sabotage_config.py:142, :228)
  - `            if got != plan["held"]:` (:224)
  - `                    crew_config_files.move_no_clobber(backup, path)` (:466)
  The fix therefore adds no nesting around them. It records how far the apply got in a local and the handlers read it.
- No change to `crew_config_files.py` (`move_aside`, `move_no_clobber`, `_unlink_source`, `Lock`, `os_error_text`), to `restore_repo_config`, to `plan_delete`, or to the success path's output.
- No change to which values either writer accepts. NIT 1 (`_content_problem` tolerates a block held as a scalar or `{}`) is declined: see Open questions.
- No new hook, no new config key, no new exit code. Exit 1 already exists for this command.
- The rewrite of test_config_menu.py changes no assertion and no test name. It is mechanical.
- No tests for `os_error_text`'s backslash handling here; they belong with their sabotage entries in L-0682.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_config_menu.py:852 `apply_delete`. :875-876 takes `machine_lock` then `Lock(path)`. :878 `_machine_digest`. :885 `_free_backup`. :886 `move_aside`. :887-898 the mismatch branch and its move-back (`move_no_clobber(backup, path)`, only `FileExistsError` handled). :899-901 `Busy`. :902-905 `Displaced`, whose message uses `backup`. :906-910 the catch-all: `refused: {path} could not be moved to a backup (...); left in place`, `return 2`. :863-864 the docstring's exit codes: 0 deleted, 2 refused (file in place), 1 a foreign writer interleaved.
- plugin/crew/hooks/scripts/crew_config_files.py:273-279 `machine_lock` calls `os.makedirs` and can raise `OSError` before any move. :466-493 `move_no_clobber`: `_fsync_dir(dest)` at :493 runs after the rename or link, so an `OSError` from it leaves the file at `dest`. :496-505 `_regular_bytes` re-raises an `OSError` from `open`. :508-514 `move_aside` is `move_no_clobber` then `_regular_bytes(dest)`. :71-79 `Displaced` is an `OSError` subclass.
- plugin/crew/tests/test_config_menu.py:1508 `test_delete_refuses_when_the_machine_lock_cannot_be_created` asserts exit 2, the file unchanged, no backup, and the lock path in stderr. It does not assert the wording, so "could not be moved to a backup" passes today for a lock failure. :1497-1505 `_deny_lock_files` is the fixture pattern (patch `crew_config_files.os.open`).
- plugin/crew/hooks/scripts/crew_config.py:3189-3194 `widening_note`: for a ratcheted key it returns `notes[normalise(after)]`. :3072-3073 `_widening` computes `now = crew_state.effective_ratcheted(dotted, after, global_value)` and decides `widens` from `rank(now) > rank(was)`. :3204-3207 `print_changes` passes `change["after"]`, not the effective value. :2737-2746 `null_means`: a repo `null` on a machine-settable key "inherits the machine-global value".
- plugin/crew/tests/test_config_menu.py:9-11 the comment and `# pylint: disable=consider-using-with`. The file is 1762 lines; `grep "open(" | grep -vc "with "` gives 83 non-`with` lines at this commit (the direction's 89 was at the landing commit).
- Docs that state the delete's exits: plugin/crew/skills/crew-setup/config-menu.md:152-166 ("Exit 1 means another writer interleaved with the move"), plugin/crew/README.md:1183-1189, plugin/crew/commands/config.md:68, .crew/codemap/crew.md:484-493.
- .crew/verify.json:160-175 maps `crew_config_menu.py`, `crew_config.py` and `test_config_menu.py` to `python3 -m pytest plugin/crew/tests/test_crew_config.py ... plugin/crew/tests/test_config_menu.py plugin/crew/tests/test_config_files.py -q`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` includes `plugin/crew/tests/sabotage*.py`; `crew_config_menu.py` and `crew_config.py` are in neither `HARNESS` nor `ALONGSIDE` (:99-118).
- Nothing on main fixes any of this: `git log origin/main --oneline --grep=T-0103` is empty; the last commit to crew_config_menu.py is `b044f1d7` (crew 1.0.57).

## Design
`apply_delete` keeps one `try`. A local records the stage: before the move, during `move_aside`, after it. The handlers:
- `Busy`: unchanged.
- `Displaced`: unchanged for the first move. See Unknowns for the move-back case.
- `OSError` before `move_aside` was called (locks, `os.makedirs`, `_machine_digest`, `_free_backup`): `refused: <os_error_text>; <path> left in place`, exit 2. It does not say "could not be moved to a backup".
- `OSError` from `move_aside` or after it: probe both names with `os.path.lexists`.
  - backup absent and path present: the move did not happen. Today's message, exit 2.
  - backup present: `refused: <what failed> (<os_error_text>) after <path> was moved; the original is at <backup>` plus, when path is also present, `check <path>`. Exit 1.
  - anything else, or the probe itself raising: say it could not tell and name both paths to check. Exit 1. "Could not tell" is never reported as "left in place".
- The move-back failing with an `OSError` other than `FileExistsError` falls into the same post-move branch and says the file changed since the preview and could not be moved back.
The docstring's exit-code line becomes: 1 when the file is not, or may not be, at its path; every file is kept and named.

`widening_note` gains the value in force. `_widening` already computes it (`now`); the change dict carries it and `print_changes` passes it, so the note for a repo `null` is the note for the inherited machine value. The printed `widens to` token stays the written value (`null`).

## Unknowns
- NIT 2 was read, not run. Step 1 of the plan writes the reproducing test. If it passes on origin/main unchanged, the NIT is not real: keep the test as a pin, drop the production change, and say so in the PR body.
- Where `_widening`'s result and the change dict meet (`plan_repo_write`) was not read line by line; the plan names the exact key to add. Accepted as planning work.
- A `Displaced` raised by the move-back (`move_no_clobber(backup, path)`) reaches the `Displaced` handler, whose text says "the original is at {backup}". After a move-back that may be untrue. Resolve at implement with a test (`test_delete_move_back_displaced_names_where_the_original_is`): if the text is wrong, fix it inside the same handler set; if it is right, the test pins it.
- Whether `plugin/crew/CONFIG.md` and `docs/guides/crew/src/troubleshooting.md` state the delete's exit codes. A grep for `delete-repo` found neither on 2026-10-04. They are in Touch so an edit is not blocked; if nothing needs changing the PR body says `Docs: CONFIG.md, guides - none, they do not describe delete's exits`.
- The next free crew patch version is set at implement time, one past origin/main's.
- `check-tooling-pr.py`'s exact output on a branch with no harness path was not run here; the check is its exit code.

## Touch
- plugin/crew/hooks/scripts/crew_config_menu.py
- plugin/crew/hooks/scripts/crew_config.py
- plugin/crew/tests/test_config_menu.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/skills/crew-setup/config-menu.md
- plugin/crew/commands/config.md
- plugin/crew/README.md
- plugin/crew/CONFIG.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script, only if a guide source changed
- .crew/codemap/crew.md
- CHANGELOG.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/tests/sabotage_config.py` and `sabotage.py` (harness, L-0682); `plugin/crew/hooks/scripts/crew_config_files.py` (no change needed); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact); `.crew/verify.json` (the rule at :160-175 already maps every file here).

## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the heavy-run wrapper. All new tests are in `plugin/crew/tests/test_config_menu.py` unless named otherwise; they map to the `.crew/verify.json` rule at :160-175.
- [ ] A failure after the move names the backup. With `_fsync_dir` or `_regular_bytes` patched to raise after the real move: exit 1, stderr contains the backup path, stderr does not contain "left in place", the backup holds the original bytes. `python3 -m pytest plugin/crew/tests/test_config_menu.py -q -k test_delete_failure_after_the_move_names_the_backup` (parametrised `fsync`, `read`)
- [ ] The move-back failing with an `OSError` that is not `FileExistsError` (file changed since the preview): exit 1, stderr names the backup and says the file changed, no "left in place". `-k test_delete_move_back_failure_names_the_backup`
- [ ] A lock or machine-directory failure before the move: exit 2, file bytes unchanged, no backup, stderr names the lock path and says "left in place", and does not contain "could not be moved to a backup". `-k test_delete_lock_failure_is_not_reported_as_a_backup_failure`
- [ ] The move itself failing (the link or rename raises, nothing moved): exit 2, file unchanged, no backup, "left in place". `-k test_delete_move_failure_before_the_file_moved_says_left_in_place`
- [ ] The probe failing: with `os.path.lexists` patched to raise after a post-move error, exit 1 and stderr names both the config path and the backup path. `-k test_delete_reports_both_paths_when_it_cannot_tell`
- [ ] Move-back `Displaced`: `-k test_delete_move_back_displaced_names_where_the_original_is` passes, and every path it names in stderr exists on disk.
- [ ] The widening note: a repo `null` on `pm.authority` with a wider machine value prints the note of the machine value. `python3 -m pytest plugin/crew/tests/test_crew_config.py -q -k test_a_repo_null_that_widens_is_described_by_the_value_in_force`
- [ ] The existing sabotage anchors survive. Each prints at least 1: `grep -c '^            got = crew_config_files.move_aside(path, backup)$' plugin/crew/hooks/scripts/crew_config_menu.py`, `grep -c '^            if got != plan\["held"\]:$' plugin/crew/hooks/scripts/crew_config_menu.py`, `grep -c '^                    crew_config_files.move_no_clobber(backup, path)$' plugin/crew/hooks/scripts/crew_config_menu.py`. And `python3 plugin/crew/tests/sabotage.py` prints no `ANCHOR LOST` and no `STILL GREEN` (run once, at the final head, under heavy-run).
- [ ] The `with` rewrite: `grep -c "consider-using-with" plugin/crew/tests/test_config_menu.py` prints 0; `python3 -m ruff check --select SIM115 plugin/crew/tests/test_config_menu.py` reports nothing; `python3 -m pylint plugin/crew/tests/test_config_menu.py` reports no `R1732`. A module helper that holds the `with` block (for the `open(p, "rb").read()` shape) counts. The test count of the file is unchanged apart from the tests this spec adds: compare `python3 -m pytest plugin/crew/tests/test_config_menu.py --collect-only -q | tail -1` before and after the rewrite commit.
- [ ] The rule's suite passes: `python3 -m pytest plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py plugin/crew/tests/test_config_files.py -q`.
- [ ] Not a tooling PR: `git diff --name-only origin/main...HEAD | grep -E "sabotage|review_|verify-gate|crew_ticket|scope_guard"` prints nothing, and `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Docs: config-menu.md step 3, README.md's delete paragraph, commands/config.md and `.crew/codemap/crew.md`'s `apply_delete` paragraph say that exit 1 also covers an OS error after the move and that the message names the backup. `python3 scripts/check_instructions.py` passes (BUDGETS.md updated if config-menu.md's size moved). Crew is bumped to the next free patch in plugin.json, marketplace.json and PLUGINS.md with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Size and split
- Estimate for this ticket: about 55 added production lines (`crew_config_menu.py` about 40, `crew_config.py` about 15). No new parser or guard. One small stage distinction inside an existing handler.
- Split out: L-0682 (`children/1/`), tooling-only, 0 production lines outside the sabotage table.
- Commit order inside this ticket: the mechanical `with` rewrite first, alone, so the behaviour commits that follow are readable.

## Dependencies
Must land first:
- T-0075 (done; merged as PR #258, crew 1.0.59): the code this ticket corrects.
- T-0087 (merged, crew 1.0.76): the tooling-PRs-land-alone rule that forces the split.

Related, same files, no order forced: L-0614 (direction; the menu's save path accepts values a guard's validator rejects - it edits `save`, not `apply_delete`).

Blocks: L-0682 (its entries for the `apply_delete` and `widening_note` fixes name tests and anchor lines this ticket adds).

## Open questions for the owner
Each was answered with the recommended option so the work is not held.
1. Exit code for an OS error after the move. Taken: **1** (the file is not at its path; everything is kept and named), matching the existing meaning of 1 for this command. Alternative: keep 2 and only fix the text.
2. Round-6 NIT 1 (`_content_problem` tolerates a block held as a scalar or `{}` that `value_allowed` refuses as an update). Taken: **declined**. The function's docstring records that refusing content can lock a file nothing reads the key from, and the value is discarded on read. Alternative: name it as pre-existing like the object-at-a-leaf case, as a new ticket.
3. Item 4, the `os_error_text` sabotage. Taken: **red on every platform** through a backslash-filename test (L-0682). Alternative: a Windows-evidenced record outside the tuple, as the direction first said.
4. The `with` rewrite rides in this PR as its own first commit. Alternative: a separate test-only PR.

## Split
- L-0682 (child 1 of T-0103, filed 2026-10-04): sabotage entries for the config leaf checks, os_error_text and the delete fixes (tooling PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
