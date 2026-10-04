# L-0682 sabotage entries for the config leaf checks, os_error_text and the delete fixes (tooling PR)          status: spec   risk: low
Split from T-0103. Written 2026-10-04 against origin/main `155fe6d8` (crew 1.0.322). Re-read the cited lines after T-0103 merges: it edits `apply_delete` and `widening_note`.

## Intent
Every check T-0075 round 6 found unguarded has a sabotage entry that goes red for real, on every platform: the two leaf-shape branches, each `os_error_text` call site, and the two fixes T-0103 adds. The code map states the mutation count with how to re-measure it.

## Exclusions
- No production code. Nothing under `plugin/crew/hooks/scripts/` changes.
- No edit to `plugin/crew/tests/sabotage.py`: it is at the pylint line limit (3400 lines, `.pylintrc:140` `max-module-lines=3400`). Entries go in `sabotage_config.py`, which `sabotage.py:80` already imports.
- No per-platform skip mechanism in the sabotage runner. Every entry added here is red on Linux.
- No change to an existing entry's anchor or test, except a label that is wrong (see Unknowns).
- No feature work, no prompt change, nothing outside `HARNESS` plus `ALONGSIDE` (scripts/check-tooling-pr.py:58-118).

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_config.py:2788-2789 `value_allowed`: `if shape == "under":` / `return f"{dotted} - under a key that takes a value, not keys; ...`. :2796-2797 its leaf branch. :2825-2826 `_content_problem`'s `under` branch. :2827-2828 `_content_problem`: `if shape == "leaf" and isinstance(value, dict):` / `return f"= {value!r} is an object where a value belongs; ...`.
- plugin/crew/tests/sabotage_config.py:586-603 the four round-5 leaf entries: `_shape`'s `return "under"` (twice, :588 and :600), `value_allowed`'s leaf branch (:592), `_content_problem`'s `under` branch (:597, labelled "a pre-existing object at a leaf is tolerated"). None anchors :2788 or :2827. :69-109 an older entry whose span includes :2788's text as context; it does not mutate it.
- plugin/crew/tests/test_crew_config.py:2352 `test_a_path_through_a_leaf_is_refused` (ids `machine-pm.authority.a`, ...). :2391 `test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated` (`[machine]` holds `pm.authority = {"a": 1}`, which is a path under a leaf; `[repo]` holds `notify.chatId = {}`, an object at a leaf).
- plugin/crew/hooks/scripts/crew_config_files.py:82-93 `os_error_text`. Call sites: crew_config.py:2969 (`GlobalWriteRefused`), :3184 (`RepoWriteRefused`), crew_config_menu.py:908 (`apply_delete`). `git grep os_error_text origin/main -- plugin/crew/tests/test_*.py` prints nothing: no direct test.
- plugin/crew/tests/sabotage_config.py:633-650 the round-5 OS-error entries remove a whole handler or narrow it; none replaces `os_error_text(exc)` with `exc`.
- plugin/crew/tests/test_crew_config.py:2990-2999 `_unmakeable` and plugin/crew/tests/test_config_menu.py:1497-1505 `_deny_lock_files`: the fixture pattern for raising a `PermissionError` with a chosen filename.
- plugin/crew/tests/sabotage.py:3344-3380 the runner: `ANCHOR LOST`, `STILL GREEN -- TEST IS VACUOUS` and `RED BUT UNPROVEN` each fail the suite; only pytest exit 1 counts. No platform condition anywhere in the loop.
- .crew/codemap/crew.md:502-504 `98 mutations ... (CONFIG_MENU_MUTATIONS, len() at 938e3b11 ...)`; `grep -c '^    ("' plugin/crew/tests/sabotage_config.py` gives 114 at `155fe6d8`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` has `plugin/crew/tests/sabotage*.py`; :99-118 `ALONGSIDE` has `plugin/crew/tests/**`, `.crew/codemap/**`, `CHANGELOG.md`, the version files, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `docs/**`.

## Unknowns
- The backslash test is designed, not run: `PermissionError(errno.EACCES, "Permission denied", r"C:\Users\o\.claude\crew")` should give a `str()` with doubled backslashes on Linux, so the single-backslash path is absent from a `{exc}` message and present in an `os_error_text` one. Confirm with the first new test before writing the entries. If it does not hold, stop and fall back to direction option 2, which needs the owner.
- The direction says the two leaf mutations were run by hand at the T-0075 head and went red. Re-run each here; an entry that prints `STILL GREEN` means its named test needs another parameter, which is a test edit, still inside this PR.
- The existing label at sabotage_config.py:596 says "object at a leaf" but mutates the `under` branch. Relabelling it is allowed here and optional.
- T-0103's final test names and handler text. The entries for its fixes are written after it merges, against the merged lines.
- Which crew patch version is free is set at implement time.

## Touch
- plugin/crew/tests/sabotage_config.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/tests/test_config_menu.py
- plugin/crew/tests/test_config_files.py
- .crew/codemap/crew.md
- .crew/codemap/verification-harness.md
- CHANGELOG.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, command and skill files, `docs/guides/crew/**`, `docs/diagrams/` - no behaviour changes, so the PR body says `Docs: none beyond the code map - sabotage entries and tests only`.

## Acceptance checks
Commands run from the repo root; pytest and the sabotage suite go through the heavy-run wrapper on a memory-bound host. The sabotage suite maps to the `.crew/verify.json` harness rule; the tests map to the config rule at :160-175.
- [ ] New tests, red-on-every-platform proof for `os_error_text`, one per call site, each raising an `OSError` with a backslash filename and asserting the path appears in stderr exactly as written:
  - `python3 -m pytest plugin/crew/tests/test_crew_config.py -q -k test_a_refused_machine_write_names_a_backslash_path_as_written`
  - `python3 -m pytest plugin/crew/tests/test_crew_config.py -q -k test_a_refused_repo_write_names_a_backslash_path_as_written`
  - `python3 -m pytest plugin/crew/tests/test_config_menu.py -q -k test_a_refused_delete_names_a_backslash_path_as_written`
  - `python3 -m pytest plugin/crew/tests/test_config_files.py -q -k test_os_error_text_keeps_backslashes_and_both_filenames` (the unit test: one filename, two filenames, no filename, a `winerror` attribute)
- [ ] New entries in `CONFIG_MENU_MUTATIONS`, each `RED (good)` in `python3 plugin/crew/tests/sabotage.py`:
  - `_content_problem`'s leaf branch replaced by `if False:` - named test `test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated[repo]`
  - `value_allowed`'s `if shape == "under":` replaced by `if False:` - named test `test_a_path_through_a_leaf_is_refused[machine-pm.authority.a]`
  - `os_error_text(exc)` replaced by `exc` at the machine writer, the repo writer and the delete handler - one entry per site, each naming its backslash test above
  - T-0103's post-move branch put back to "left in place" with exit 2 - named test `test_delete_failure_after_the_move_names_the_backup[fsync]`
  - T-0103's pre-move branch put back to "could not be moved to a backup" - named test `test_delete_lock_failure_is_not_reported_as_a_backup_failure`
  - T-0103's could-not-tell branch collapsed into "left in place" - named test `test_delete_reports_both_paths_when_it_cannot_tell`
  - T-0103's `widening_note` put back to the written value - named test `test_a_repo_null_that_widens_is_described_by_the_value_in_force` (omit this entry, and say so in the PR body, if T-0103 found the NIT not real)
- [ ] The whole suite: `python3 plugin/crew/tests/sabotage.py` ends `SABOTAGE SUITE: PASS` with no `ANCHOR LOST`, `STILL GREEN` or `RED BUT UNPROVEN` line. `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q` passes.
- [ ] Each new entry's `find` text occurs exactly once in its target: for each, `python3 - <<'PY'` importing `sabotage_config` and asserting `open(target).read().count(find) == 1` for the entries added here (a one-off check quoted in the PR body, not a committed script).
- [ ] The config suites pass unchanged: `python3 -m pytest plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py plugin/crew/tests/test_config_files.py -q`.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` exits 0 on the branch, and `git diff --name-only origin/main...HEAD -- plugin/crew/hooks plugin/crew/commands plugin/crew/skills` prints nothing.
- [ ] The harness rule's other legs ran because a `HARNESS` path changed (`.crew/verify.json` harness rule): `python3 scripts/_test/tooling-pr.py`, the golden replay, the seam contracts and the canary review. Name each as run or not run in the PR body.
- [ ] `.crew/codemap/crew.md`'s sentence gives the count as `len(CONFIG_MENU_MUTATIONS)` at a named commit, re-measured with `python3 -c "import sys; sys.path.insert(0, 'plugin/crew/tests'); import sabotage_config as s; print(len(s.CONFIG_MENU_MUTATIONS))"`, and the module docstring of `sabotage_config.py` mentions round 6. `python3 -m pylint plugin/crew/tests/sabotage_config.py` is clean.
- [ ] Crew is bumped to the next free patch in plugin.json, marketplace.json and PLUGINS.md with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Size
0 production lines outside the harness. About 60 lines in `sabotage_config.py` (nine entries) and about 90 lines of tests. No new parser, guard or state machine. One PR.

## Dependencies
Must land first:
- T-0103 (spec; the feature PR): four of the nine entries anchor lines and name tests it adds. The other five (the two leaf entries and the three `os_error_text` entries) do not depend on it, but `apply_delete`'s handler text moves in T-0103, so the delete-site `os_error_text` entry is written against the merged code.
- T-0075 (done; PR #258): the code under test.
- T-0087 (merged): defines this PR's shape (tooling lands alone; tests, code map and version files ride along).

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
