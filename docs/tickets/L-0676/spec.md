# L-0676: sabotage mutations prove the recall project tests (tooling-only)          status: spec   risk: low
Split from T-0083 (2026-10-04). Not approved. Written against origin/main `155fe6d8` (crew 1.0.322). It cannot be planned in detail until L-0675 has merged, because each mutation is anchored on a line L-0675 writes.

## Intent
Each behaviour L-0675 added to `crew_recall.py` has a mutation in crew's sabotage table that puts the bug back and turns one named test red. The PR is tooling-only, so it passes the tooling-PR check.

## Exclusions
- No production code. `crew_recall.py`, `crew_context.py` and `crew_config.py` are not edited; if a mutation needs a different anchor, the mutation changes, not the code.
- No new test in `test_crew_recall_project.py` beyond an anchor-presence test. A behaviour gap found here is a finding for a new ticket, not a quiet addition.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140` `max-module-lines=3400`). The mutations go in `sabotage_context.py`.
- No obsidian-vault change. Slice 1's sabotage is by hand, recorded in its own ticket.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- scripts/check-tooling-pr.py:78 `"plugin/crew/tests/sabotage*.py"` is in `HARNESS`. :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, README, BUDGETS, version files, CHANGELOG, `docs/**` and `.crew/codemap/**` ride along.
- plugin/crew/tests/sabotage_context.py (203 lines): :13 `RECALL` is the path to `crew_recall.py`. :174-181 the shape of a mutation: description, file, the exact original line, the replacement, and the test id that must go red.
- plugin/crew/tests/sabotage_context.py:129-153 the two existing recall mutations for vault labels, the pattern to follow.
- `.pylintrc:140` `max-module-lines=3400`.

## Unknowns
- The exact anchor lines. Resolved when L-0675 merges: read `crew_recall.py` on origin/main and copy each line byte for byte.
- Whether the sabotage runner needs a restart of the interpreter between mutations (a stale `.pyc` after a same-size, same-second edit can hide a mutation). Resolved at implement: if a mutation reads green, check the `.pyc` timestamp before changing the mutation.
- Whether a crew version bump is needed for a tests-only change. Tests ship inside the plugin directory, so content changes; default taken: bump the patch version.

## Touch
- `plugin/crew/tests/sabotage_context.py`
- `plugin/crew/tests/test_crew_recall_project.py` - the anchor-presence test only
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`

## Acceptance checks
Commands run from the repo root, through the heavy-run wrapper on a memory-bound host.
- [ ] `python3 plugin/crew/tests/sabotage.py` reports every mutation red, the new ones included. The new mutations, each naming its test in `plugin/crew/tests/test_crew_recall_project.py`:
  - (a) the project is never added to the argv -> `test_the_main_checkout_name_is_sent_as_the_project`
  - (b) the project is taken from the worktree's own directory -> `test_a_linked_worktree_sends_the_main_checkout_name`
  - (c) the config list is ignored -> `test_the_config_list_wins_over_the_directory_name`
  - (d) a name with a comma or control character is passed through -> `test_unusable_project_names_are_dropped`
  - (e) an exit 2 is not retried -> `test_an_older_cli_is_asked_again_without_the_project`
  - (f) every non-zero exit is retried -> `test_only_exit_2_is_retried`
  - (g) the retry gets a fresh time budget -> `test_the_retry_shares_one_time_budget`
  - (h) the retry's answer is reported as `projectUsed` true -> `test_an_older_cli_is_asked_again_without_the_project`
- [ ] `test_every_recall_project_sabotage_anchor_is_present_exactly_once` passes: each new mutation's original line occurs once in `crew_recall.py`.
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_recall_project.py plugin/crew/tests/test_crew_context.py -q` passes on the unmutated tree, and `git status --porcelain plugin/crew/hooks/scripts` is empty after the sabotage run (every mutation restored).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` on this branch.
- [ ] `python3 -m pylint plugin/crew/tests/sabotage_context.py` reports no new message.
- [ ] crew is bumped to the next free patch with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit. PR body carries `Docs: none - tests-only harness change, no behaviour or setting changes`.

## Size
No production lines. About 60 lines in `sabotage_context.py` and about 15 in the test file.

## Dependencies
Must land first:
- L-0675 (spec): writes the code and the tests these mutations name.
- T-0083 (spec, slice 1): L-0675 depends on it.
- T-0087 (merged): the rule that makes this a separate PR.

Blocks: nothing.

## Open questions for the owner
1. Bump crew for a tests-only change (taken: yes, patch), or land with no bump?

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
