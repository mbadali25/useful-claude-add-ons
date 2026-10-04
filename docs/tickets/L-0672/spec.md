# L-0672 sabotage mutations for crew_tracker's per-component identity check          status: spec   risk: low
Split from T-0081. Written 2026-10-04 against origin/main `155fe6d8`; the lines it mutates are added by T-0081, so re-read `crew_tracker.py` on main after T-0081 merges before planning.
## Intent
Each guard branch T-0081 adds to `crew_tracker.py` has a committed mutation in `plugin/crew/tests/sabotage_tracker.py` that turns one named test red through `plugin/crew/tests/sabotage.py`. The PR is tooling-only: it changes no production code.
## Exclusions
- No edit to `plugin/crew/hooks/scripts/crew_tracker.py` or any other production file. If an anchor is not unique, that is found here and fixed in a separate feature PR, not in this one.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140` `max-module-lines=3400`). `TRACKER_MUTATIONS` is already imported and appended there.
- No new test behaviour in `test_crew_tracker.py` beyond what a mutation needs to be seen alone. No change to existing mutations.
- No change to the sabotage harness itself, the review tools or the verify gate.
## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/tests/sabotage_tracker.py:22 `TRACKER_MUTATIONS`, a tuple of `(label, target, find, replace, test)`; 87 entries. :426-432 the POSIX vault-identity mutation; :459-473 the Windows vault-identity and zero-file-id mutations: the shapes to copy.
- plugin/crew/tests/sabotage.py:78 imports `TRACKER_MUTATIONS`; :3066 appends it.
- plugin/crew/tests/test_crew_tracker.py:894 `test_every_tracker_sabotage_anchor_is_present_exactly_once`.
- scripts/check-tooling-pr.py:78 `plugin/crew/tests/sabotage*.py` in `HARNESS`; :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, the version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `docs/**`, `.crew/codemap/**` and `graphify-out/**` ride along.
- The mutation count is stated at .crew/codemap/crew.md:1158 and .crew/codemap/verification-harness.md:293 ("87 by `len()`").
- The tests the mutations aim at are named in T-0081's spec, Acceptance checks.
## Unknowns
- The exact anchor lines: they exist only once T-0081 has merged. Resolved at plan time by reading `crew_tracker.py` on main.
- Whether each new branch can be seen by one test alone. If the POSIX and Windows walks share one helper, removing the helper's comparison turns both platforms' tests red; that is one mutation with one named test, plus one mutation per call site. Resolved at plan time.
- The next free crew patch version is set at implement time.
## Size and split
- 0 production lines. About 40 lines in `sabotage_tracker.py` (5 mutations of about 8 lines). No split.
## Touch
- `plugin/crew/tests/sabotage_tracker.py`
- `plugin/crew/tests/test_crew_tracker.py` - only if a mutation needs a narrower test to be seen alone
- `.crew/codemap/crew.md` - the mutation count at :1158
- `.crew/codemap/verification-harness.md` - the mutation count at :293
- `.crew/codemap/INDEX.md` - the anchor rows, if the refresh moves them
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `graphify-out/**` - rebuilt by graphify update, never by hand

Not in Touch, stated: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, the guides and `docs/diagrams/` (no behaviour changes; the PR body says `Docs: none - test-harness mutations only, no behaviour change`, the code maps aside).
## Acceptance checks
Commands run from the repo root. On a memory-bound host the sabotage run goes through the repo's heavy-run wrapper.
- [ ] `TRACKER_MUTATIONS` gains one mutation for each of these, each with the test it turns red:
  - the POSIX walk skips the per-component identity match -> `test_board_dir_replaced_by_a_real_directory_after_the_checks_writes_nothing`
  - the Windows walk skips the per-component identity match -> `test_the_handle_pin_refuses_a_different_component`
  - a zero inode on the fd walk reads as the same directory -> `test_the_fd_walk_refuses_a_zero_inode_as_could_not_tell`
  - a component with no recorded identity reads as the same directory -> `test_a_component_with_no_recorded_identity_is_could_not_tell`
  - `_vault_paths` records the vault's identity for every component (or none) -> `test_vault_paths_records_every_component_identity`
- [ ] Every anchor occurs exactly once: `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q -k test_every_tracker_sabotage_anchor_is_present_exactly_once`
- [ ] Each new mutation goes RED on its named test and the tree is restored: `python3 plugin/crew/tests/sabotage.py` (the tracker entries; quote the harness's own lines for the five).
- [ ] The tracker suite is green with no mutation applied: `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and its suite passes: `python3 scripts/_test/tooling-pr.py`
- [ ] Both code maps state the new count, read from `len(TRACKER_MUTATIONS)`. Crew is bumped to the next free patch with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.
## Dependencies
Must land first:
- T-0081 (spec, this split's first slice): adds the lines these mutations anchor on and the tests they aim at.
- T-0087 (merged): the tooling-PR rule and `scripts/check-tooling-pr.py`.
- T-0077 (merged), T-0021 (merged): the existing tracker mutations this follows.

Related, no order forced: T-0080 (direction; sabotage harness memory bounds, a different sabotage file).

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
