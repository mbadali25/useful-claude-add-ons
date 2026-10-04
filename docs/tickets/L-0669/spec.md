# L-0669: sabotage mutations for the T-0071 tracker fixes (tooling PR)          status: spec   risk: med
Split from T-0071 on 2026-10-04 (see `../../spec.md`). Written against origin/main `155fe6d8` (crew 1.0.322); the anchors below can only be fixed once T-0071 has merged, so re-read `crew_tracker.py` and `fix.md` on origin/main before planning.

## Intent
Each branch T-0071 added to `crew_tracker.py`, and its `fix.md` step-1 wording, gets one mutation in `plugin/crew/tests/sabotage_tracker.py` that reintroduces the original bug and turns exactly its named test red through `plugin/crew/tests/sabotage.py`. The PR changes the harness and nothing else.

## Exclusions
- No production code and no prompt: no edit to `crew_tracker.py`, `commands/fix.md`, `commands/brainstorm.md` or any other file outside `HARNESS` and `ALONGSIDE` (`scripts/check-tooling-pr.py:58-118`).
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint module-line limit; `TRACKER_MUTATIONS` is already imported at :78 and registered at :3066).
- No new test unless a mutation comes back green; then the missing assertion is added to `test_crew_tracker.py` or `test_lifecycle_commands.py` (both `ALONGSIDE`) and the PR body says which mutation exposed it.
- No re-anchoring of an existing mutation onto a different line. If T-0071 moved an anchored line, that is a T-0071 defect: stop and report it.
- No change to what any existing mutation claims.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/tests/sabotage_tracker.py:1-12 the header: every guard branch in `crew_tracker.py` gets one mutation, each aimed at the one test that sees that branch alone. :15-20 `TRACKER`, `BRAINSTORM`, `FIX`, `_TESTS`, `_LIFECYCLE`. :22 `TRACKER_MUTATIONS`; a mutation is `(label, file, anchor, replacement, test id)`. The file is 694 lines.
- plugin/crew/tests/sabotage.py:11-12 an anchor that no longer matches is a failure, not a skip; :78 imports `TRACKER_MUTATIONS`; :3066 registers it.
- scripts/check-tooling-pr.py:78 `plugin/crew/tests/sabotage*.py` is `HARNESS`; :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, README, BUDGETS, version files, CHANGELOG, `docs/**`, `.crew/codemap/**`, `.crew/verify.json` and `graphify-out/**` ride along.
- .crew/verify.json:368-374 the crew_tracker rule lists `sabotage_tracker.py` in its paths and states "Every mutation in sabotage_tracker.py goes red on its named test through sabotage.py".
- The tests the mutations aim at are named in T-0071's spec.md, "Acceptance checks".
- Precedent: L-0531 (merged), the same split for L-0529.

## Unknowns
- The exact anchor text: known only after T-0071 merges. Resolved at plan time by reading the merged lines; each anchor must occur exactly once in its file unless the mutation is meant to hit several.
- Whether each T-0071 test is tight enough. Resolved by running the mutation: green means the test is vacuous for that branch and is tightened here.
- The crew patch version is the next free one at implement time.

## Size and split
Production lines added: 0. About 110 lines of mutation tuples in one harness file. One PR, tooling-only. No further split.

## Touch
- `plugin/crew/tests/sabotage_tracker.py`
- `plugin/crew/tests/test_crew_tracker.py` only to tighten a test a green mutation exposes
- `plugin/crew/tests/test_lifecycle_commands.py` only for the same reason
- `.crew/verify.json` only the crew_tracker rule's why text, if the mutation count it states changes
- `.crew/codemap/verification-harness.md`
- `.crew/codemap/crew.md` only if it counts the tracker mutations
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `graphify-out/**`

Docs: none beyond the code map and CHANGELOG - no behaviour a user sees changes. Say `Docs: none - mutations only` in the PR body.

## Acceptance checks
Commands run from the repo root; heavy runs go through the heavy-run wrapper, one at a time.
- [ ] `sabotage_tracker.py` gains one mutation per branch below, each red on its named test (names from T-0071's spec; use the merged names if review renamed them):
  - (a) `normal_url` lowercases the whole URL again -> `test_origins_differing_only_in_case_are_two_repos`
  - (b) `normal_url` stops folding the host -> `test_repo_id_folds_only_scheme_and_host`
  - (c) the old-note clause is dropped from the foreign refusal -> `test_a_lowercased_old_note_is_refused_with_the_fix`
  - (d) an old lowercased note is accepted as ours -> the same test (its exit-1 and byte-identical assertions)
  - (e) a `file://` authority is kept as path text -> `test_file_url_authority_is_not_path_text`
  - (f) the slash before a drive letter is kept on Windows -> `test_file_url_drive_prefix_by_platform`
  - (g) the board half uses the lane this call asked for, not INDEX's -> `test_overlapping_moves_leave_board_and_index_agreeing`
  - (h) an unreadable or unknown INDEX status at board-write time is treated as the requested status -> `test_board_is_not_moved_when_index_cannot_be_read_at_write_time`
  - (i) a lone trailing quote is stripped from a note's `repo-id:` -> the `test_note_repo_id_quote` must-block case
  - (j) the checkbox matcher accepts a marker with no following space -> `test_checkbox_without_a_space_is_repaired`
  - (k) `fix.md` step 1 loses its Jira/SDP MCP create -> `test_fix_mints_through_mcp_under_jira_and_sdp`
- [ ] The whole sabotage run is green-by-red: `python3 plugin/crew/tests/sabotage.py` reports every mutation red, none with a missing anchor, and every file restored (`git status --porcelain` prints nothing afterwards).
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` exits 0 with a line starting `tooling-pr: OK`, and its suite `python3 scripts/_test/tooling-pr.py` passes.
- [ ] The harness rule's other suites pass as `.crew/verify.json`'s harness rule runs them (golden replay, seam contracts, canary review); name any that did not run.
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_tracker.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_sabotage_harness.py -q` passes.
- [ ] `python3 -m pylint plugin/crew/tests/sabotage_tracker.py` reports no new finding and the file stays under `.pylintrc`'s `max-module-lines`.
- [ ] crew bumped to the next free patch with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0071 (spec, this folder's parent): the code these mutations patch. Hard dependency: the anchors do not exist until it merges.
- T-0087 (merged): the rule that makes this a separate PR.
- T-0021 (merged): `sabotage_tracker.py` itself.

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
