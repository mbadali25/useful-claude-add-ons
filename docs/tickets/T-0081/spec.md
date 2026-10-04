# T-0081 crew_tracker's vault walk matches every directory's identity, not just the vault's          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket (there was only a direction). Written against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". No plan.md exists.

Narrowed by the split rule: this spec is slice 1 of 2. It holds the guard, its tests and its docs. The sabotage mutations are **L-0672** (`children/1/`), because `plugin/crew/tests/sabotage_tracker.py` is a harness path and may not ride with `crew_tracker.py`.
## Intent
A vault write is refused when any directory between the vault and the board or note is not the directory `_vault_paths` checked. Today only the vault is matched, so a real directory inside the vault that is renamed away and replaced by another real directory in the check-to-pin window is written into. After this ticket `_vault_paths` records each real component's `(st_dev, st_ino)` and both walks (POSIX fd walk, Windows handle walk) match it; an identity that cannot be told refuses as "could not tell".
## Design (for the planner; change it only with a reason)
- `_vault_paths` adds one key per label, `<label>DirIds` (`boardDirIds`, `noteDirIds`): a list aligned with `_components(paths, label)`, built by the same function so the two cannot drift. Each entry is `(st_dev, st_ino)` from `os.lstat` of that real component, or `None` when it is absent, not a directory, or cannot be read. `_vault_paths` returns no new problem for a `None`; existing refusals (missing vault, no board) keep their text.
- One helper holds the comparison, used by both walks. It raises `OSError`:
  - `errno.EIO`, text containing "could not tell", when the recorded entry is `None`, or `st_ino` is 0 on either side;
  - `errno.ESTALE` when the two differ (`_moved` already turns ESTALE into "a directory on its path changed after the vault checks").
- POSIX (`_open_pinned`): after each `os.open(part, _DIR_FLAGS, dir_fd=fd)`, `os.fstat` the new fd and run the helper against that component's recorded entry. The vault's own `st_ino` 0 also refuses.
- Windows (`_hold_dirs`): for `index > 0`, run the helper against the recorded entry for that component. The existing reparse-point, non-directory, zero-id and `index == 0` vault checks stay as they are.
- A list whose length differs from the components walked refuses (EIO, "could not tell").
- `_pinned_check` re-walks through `_open_pinned`, so it gains the check with no edit. `_held_check` is unchanged.
- The 87 existing sabotage anchors in `sabotage_tracker.py` must each still occur exactly once in `crew_tracker.py`. In particular do not add a second line equal to `            if not seen.st_ino:\n`, `            inner = os.open(part, _DIR_FLAGS, dir_fd=fd)\n`, `        if (seen.st_dev, seen.st_ino) != paths["vaultId"]:\n` or `            if index == 0 and (seen.st_dev, seen.st_ino) != paths["vaultId"]:\n`. Putting the new comparison in the helper avoids all four.
## Exclusions
- No edit to `plugin/crew/tests/sabotage_tracker.py`, `plugin/crew/tests/sabotage.py` or any other `HARNESS` path. That is L-0672.
- No change to what `_vault_paths` refuses at check time, to its messages, or to confinement (`_inside`, `git check-ignore`).
- No change to `_held_check`, `_pinned_check`, `_atomic_update`, `_create_note_once`, the access and share masks, card ownership, lanes or statuses.
- The window between `os.path.realpath` and the `os.lstat` inside `_vault_paths` is not closed: the check itself is by path. Whatever directory is recorded is inside the vault, and the walk reaches it without following a link.
- The POSIX residual race the README names (a move between the last re-walk and the replace) stays as documented.
- No new setting, no new hook, no new command.
- Nothing from T-0071 (repo-id and board ordering), L-0530 or L-0571 (lane mapping), which edit other parts of the same file.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_tracker.py:987 `_vault_paths`; :1012 `found["vaultId"] = (seen.st_dev, seen.st_ino)`, the only identity recorded; :1019 each label's real path; :1024 `found[label]`, `found[label + "Shown"]`.
- plugin/crew/hooks/scripts/crew_tracker.py:1063-1065 `_components`: the real directory's parts relative to the vault.
- plugin/crew/hooks/scripts/crew_tracker.py:1068 `_hold_dirs` (Windows); :1086 reparse point, :1088 non-directory, :1090 zero file id, all per component; :1093 identity matched for `index == 0` only.
- plugin/crew/hooks/scripts/crew_tracker.py:1106 `_open_pinned`; :1122 vault matched; :1124-1127 components opened by name, no identity check.
- plugin/crew/hooks/scripts/crew_tracker.py:1054-1060 `_moved` maps ELOOP, ENOTDIR and ESTALE to "a directory on its path changed after the vault checks".
- plugin/crew/hooks/scripts/crew_tracker.py:1134 `_pinned_check` re-walks with `_open_pinned` (:1149); :1163 `_held_check`; :1184 `_pinned`.
- plugin/crew/hooks/scripts/crew_tracker.py:333-361 `_win_open_dir`: `os.fstat` on the wrapped handle reports the same `(st_dev, st_ino)` as `os.stat`.
- Callers of `_vault_paths`: plugin/crew/hooks/scripts/crew_tracker.py:1349, :1391, :1430. `_load_board` runs between it and the first walk (:1352, :1397), which is where the tests swap.
- plugin/crew/tests/test_crew_tracker.py:1395 `_swap_for_link` (the hook point after `_load_board`); :1447 `test_vault_replaced_after_the_checks_writes_nothing`; :1473 `test_board_dir_that_is_a_link_inside_the_vault_is_allowed`; :1677 `_fake_held`; :1693 `_held_repo`; :1731 `test_the_handle_pin_refuses_a_zero_file_id_as_could_not_tell`; :1750 `test_the_held_check_refuses_when_the_path_no_longer_reaches_the_held_directory`; :1791-1795 a hand-built `paths` dict carrying `vaultId` only.
- plugin/crew/tests/test_crew_tracker.py:894 `test_every_tracker_sabotage_anchor_is_present_exactly_once`. plugin/crew/tests/sabotage_tracker.py:422, :429, :462, :470 are the anchors named in Design.
- scripts/check-tooling-pr.py:58-87 `HARNESS`; :78 `plugin/crew/tests/sabotage*.py`. `crew_tracker.py` is in neither `HARNESS` nor `SEAM` (:89-95).
- .crew/verify.json:368-376 maps `crew_tracker.py`, `test_crew_tracker.py`, `sabotage_tracker.py` and `tracker_fixtures/**` to `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`.
- .github/workflows/pytest-crew.yml:162 and :442: `crew-shell-matrix` runs on Linux and, through its fan-in, on Windows.
- Docs that state the behaviour: plugin/crew/README.md:1715-1724; .crew/codemap/crew.md:1104-1125. `git grep -iE "FILE_SHARE_DELETE|device and inode|file id" origin/main -- plugin/crew/CONFIG.md plugin/crew/commands plugin/crew/skills 'docs/guides/crew/src/*.md'` prints nothing.
- Sizes: `crew_tracker.py` 1572 lines, `test_crew_tracker.py` 2228 lines; `.pylintrc:140` `max-module-lines=3400`.
- Version: plugin/crew/.claude-plugin/plugin.json:3 `1.0.322`; plugin/PLUGINS.md:14; CHANGELOG.md:7.
## Unknowns
- Whether any supported Windows Python reports `st_ino` 0 from `os.lstat` on a path while `os.fstat` on the handle reports a file id, or the reverse. The vault check at :1093 already depends on the two agreeing. Resolved before land by the native Windows run of `test_crew_tracker.py` (the `crew-shell-matrix (windows-latest)` check).
- Whether a POSIX file system in real use reports `st_ino` 0. Accepted as risk: it now refuses, with a "could not tell" reason that names the cause. Open question 1 in direction.md.
- The next free crew patch version is set at implement time.
## Size and split
- Estimate: about 45 added production lines, all in `plugin/crew/hooks/scripts/crew_tracker.py` (helper about 15, `_vault_paths` about 12, `_open_pinned` about 10, `_hold_dirs` about 5, docstrings the rest). Under the 300-line rule.
- One guard is extended; no new parser or state machine.
- Split for the harness rule only: L-0672 adds the sabotage mutations as a tooling-only PR after this one merges.
## Touch
- `plugin/crew/hooks/scripts/crew_tracker.py`
- `plugin/crew/tests/test_crew_tracker.py`
- `plugin/crew/README.md` - the vault-write paragraph at :1715-1724
- `.crew/codemap/crew.md` - the tracker section at :1104-1125 and its line citations
- `.crew/codemap/INDEX.md` - the anchor row, if the refresh moves it
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `docs/diagrams/**` - regenerated anchors only, no box or edge changes
- `graphify-out/**` - rebuilt by graphify update, never by hand

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting); `plugin/crew/commands/**` and `plugin/crew/skills/**` (none describes the pin); `docs/guides/crew/src/*.md` and the rebuilt guide outputs (no guide mentions the pin, so the PR body says `Docs: guides none - no guide describes vault directory pinning`); `.crew/verify.json` (the rule at :368-376 already covers these paths); `.crew/codemap/verification-harness.md` (the mutation count changes in L-0672, not here).
## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper. All map to the `.crew/verify.json` rule at :368-376 unless another is named.
- [ ] Must-block, POSIX and Windows natively: the board's directory is renamed away and replaced by a byte-identical real copy after `_load_board`; `move` exits 1, the copy and the moved original are byte-identical to before, and no `.tmp` is left in either. `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q -k test_board_dir_replaced_by_a_real_directory_after_the_checks_writes_nothing`
- [ ] Must-block: with `boardDir` `A/B`, the middle directory `A` is replaced by a copy after the checks; nothing is written. `-k test_a_middle_directory_replaced_after_the_checks_writes_nothing`
- [ ] Must-block, the note: the same swap during `create` leaves no note in the replacement and no INDEX row. `-k test_note_dir_replaced_by_a_real_directory_after_the_checks_leaves_no_note_there`
- [ ] Must-block, Windows branch on any OS (`_fake_held`): a component whose handle reports a different identity is refused. `-k test_the_handle_pin_refuses_a_different_component`
- [ ] Could not tell, POSIX walk: a component (and, separately, the vault) whose `os.fstat` reports `st_ino` 0 is refused, the reason contains "could not tell", and the board is byte-identical. `-k test_the_fd_walk_refuses_a_zero_inode_as_could_not_tell` (skipped where `_DIR_FD` is false)
- [ ] Could not tell, both branches: a component recorded as `None`, or a `<label>DirIds` list of the wrong length, is refused with "could not tell". `-k test_a_component_with_no_recorded_identity_is_could_not_tell` (parametrised over the fd walk and the handle walk)
- [ ] `_vault_paths` records one identity per real component for the board and for the note, `None` for a missing directory, and returns the same problem strings as before for a missing vault and a missing board. `-k test_vault_paths_records_every_component_identity`
- [ ] Must-allow, unchanged and green: `test_board_dir_that_is_a_link_inside_the_vault_is_allowed`, `test_the_handle_pin_writes_when_every_directory_is_the_one_checked`, `test_vault_is_symlink`, `test_vault_path_with_spaces`, and a vault-root board (`boardDir` unset, empty component list).
- [ ] The existing anchors hold: `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q -k test_every_tracker_sabotage_anchor_is_present_exactly_once`
- [ ] The whole tracker suite passes on Linux: `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`. On Windows the `crew-shell-matrix (windows-latest)` check is green on the PR, including `test_the_windows_pin_blocks_renames_while_held_and_frees_them_after` with its hand-built `paths` updated for the new key.
- [ ] Sabotage by hand, recorded in the PR body (the committed mutations are L-0672). For each of these, edit a scratch copy or run with `PYTHONDONTWRITEBYTECODE=1`, see the named test go red, restore:
  - the POSIX per-component match removed -> `test_board_dir_replaced_by_a_real_directory_after_the_checks_writes_nothing`
  - the Windows per-component match removed -> `test_the_handle_pin_refuses_a_different_component`
  - the helper's zero-inode branch removed -> `test_the_fd_walk_refuses_a_zero_inode_as_could_not_tell`
  - the helper's `None` branch removed -> `test_a_component_with_no_recorded_identity_is_could_not_tell`
- [ ] Not a tooling PR: `git diff --name-only origin/main...HEAD` lists no path matched by `HARNESS` in `scripts/check-tooling-pr.py`.
- [ ] Lint: `python3 -m pylint plugin/crew/hooks/scripts/crew_tracker.py plugin/crew/tests/test_crew_tracker.py` reports no new finding.
- [ ] Docs: `plugin/crew/README.md` says every directory from the vault down is matched by device and inode (POSIX) or volume and file id (Windows), and that an identity that cannot be told refuses; `.crew/codemap/crew.md` describes the per-component record and cites the new lines. Crew is bumped to the next free patch in `plugin.json`, `marketplace.json` and `PLUGINS.md` with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.
## Dependencies
Must land first:
- T-0077 (merged): the Windows handle pin this ticket extends.
- T-0021 (merged): `crew_tracker.py` and the POSIX pinned walk.
- T-0087 (merged): the tooling-PRs-land-alone rule that forces the split.
- T-0076 (done): the native Windows crew suite is green and required, which is what resolves the Windows unknown.

Related, same file, no order forced: T-0071 (direction), L-0530 (direction), L-0571 (direction). Whichever lands second merges main and re-reads its line numbers.

Blocks: L-0672 (its anchors do not exist until this merges).

## Split
- L-0672 (child 1 of T-0081, filed 2026-10-04): sabotage mutations for crew_tracker's per-component identity check (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
