# L-0641: sabotage mutations for ticket state (closed words, dependency state, next.md)          status: spec   risk: med
Split from T-0037 (2026-10-04). Tooling PR; lands after L-0639 and L-0640.
## Intent
Each fail-closed rule that L-0639 and L-0640 added is mutation-proven: a new `plugin/crew/tests/sabotage_ticket_state.py` holds one mutation per rule, each going red on a named test, and `sabotage.py` runs them. No production behaviour changes.
## Exclusions
- No production code and no command text. Only `HARNESS` and `ALONGSIDE` paths of `scripts/check-tooling-pr.py`; no `Tooling-seam:` trailer.
- No new test behaviour in `test_ticket_state.py` beyond what a mutation needs to be killed; a rule found unguarded gets a test here (tests are `ALONGSIDE`), but a production bug found is a STOP and a separate feature ticket.
- No mutation for the autopilot stops or `/crew:status --owner` (L-0550, L-0551).
- `sabotage.py` must not grow: net line change zero.
- No change to how the sabotage runner works.
## Evidence
At origin/main `155fe6d8`.
- `plugin/crew/tests/sabotage.py` is 3400 lines; `.pylintrc:140` is `max-module-lines=3400` and `.pylintrc:109` is `max-line-length=120`.
- Sibling imports at `sabotage.py:67-88`; the concatenation is `MUTATIONS += (... )` at `:3064-3071`, where `:3068` holds only `+ LIMIT_WORKTREE_MUTATIONS` and `:3069` only `+ QA_AUDIT_MUTATIONS + TOOLING_MUTATIONS`. Joining those two lines frees the one line the new import needs.
- The runner unpacks `label, target, find, replace, test` at `sabotage.py:3365`; targets are collected at `:3327`.
- A sibling's shape and docstring: `plugin/crew/tests/sabotage_autopilot.py` (anchor example at `:126`).
- The harness's own suite is `plugin/crew/tests/test_sabotage_harness.py` (verify rule at `.crew/verify.json:220-225`); the harness rule that runs `scripts/check-tooling-pr.py`, the golden replay and the canary is at `.crew/verify.json:459-473`.
- Targets exist only after L-0639 and L-0640: `plugin/crew/hooks/scripts/crew_ticket_state.py`, and the `_TABLE_DONE_WORDS` literal at `plugin/crew/hooks/scripts/crew_state.py:238-240`.
## Unknowns
- Exact `find` strings: taken from the merged children's code on the land branch. Each must occur exactly once in its target; resolved by a new test `test_every_ticket_state_sabotage_anchor_is_present_exactly_once`.
- Stale `.pyc` after an in-place mutation of equal size can hide a red. Resolved by running through the existing runner (which restores from `.bak`) and never hand-mutating; if a mutation reports green, check the `.pyc` timestamp before concluding the test is weak.
- Whether the harness rule's `paths` in `.crew/verify.json` must list the new sibling: `test_verify_rule_paths_cover_the_harness_its_seams_and_suites` decides. `sabotage*.py` is a glob in `HARNESS`, so it is probably covered; resolved by running that test.
- Version bump: `plugin/crew/tests/` ships inside the plugin, so crew is bumped one patch (the repo's "content change with no version bump" stop condition).
## Touch
- `plugin/crew/tests/sabotage_ticket_state.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/tests/test_ticket_state.py`
- `plugin/crew/tests/test_sabotage_harness.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `.crew/verify.json`
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
## Acceptance checks
- [ ] `TICKET_STATE_MUTATIONS` in `sabotage_ticket_state.py`, each red on its test: an unknown dependency reads closed (`test_unknown_dependency_blocks`); a cancelled dependency reads closed (`test_cancelled_dependency_blocks_and_names_it`); a dependency row with no status cell reads closed (`test_dependency_row_without_a_status_cell_is_unknown`); an unreadable ledger reads as no replan (`test_unreadable_ledger_is_not_read_as_no_replan`); `cancelled` dropped from `_TABLE_DONE_WORDS` (`test_cancelled_and_superseded_rows_are_closed`); needs-owner without `next:` reads as nothing asked (`test_needs_owner_without_next_says_cannot_tell`); a bad `revisit:` reads as not due (`test_bad_revisit_date_is_listed`); a bad `waiting-on:` is accepted (`test_bad_waiting_on_is_reported`). Command: `python3 plugin/crew/tests/sabotage.py` through the repo's heavy-run wrapper; every label above reported red, no `.bak` left, failures quoted verbatim.
- [ ] `test_every_ticket_state_sabotage_anchor_is_present_exactly_once` and `test_ticket_state_mutations_are_exactly_the_pinned_set` (in `test_ticket_state.py`) pass. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_ticket_state.py plugin/crew/tests/test_sabotage_harness.py -q`.
- [ ] `git show origin/main:plugin/crew/tests/sabotage.py | wc -l` equals `wc -l < plugin/crew/tests/sabotage.py` (no growth), and `python3 -m pylint plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_ticket_state.py` reports no `too-many-lines` and no `line-too-long`.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and the harness rule's other commands (`.crew/verify.json:469`) pass.
- [ ] Docs: `Docs: none - test harness only` is stated in the PR body for the guides and diagrams; the README's sabotage coverage note (if it lists sibling files) and `.crew/codemap/verification-harness.md` or `crew.md` name the new file; `crew_refresh_check.py --root . --ticket <id>` prints every line `fresh`. `.crew/verify.json` lists the new file in the ticket-state rule's paths.
- [ ] `python3 scripts/check-marketplace.py` passes after the one-patch crew bump and a CHANGELOG entry; `python3 scripts/gate-runner.py` is green, with what ran and what did not named in the PR body.
## Dependencies
- L-0639 and L-0640 (must both be merged first): the code and tests the mutations target.
- T-0037 (transitively), T-0087 (merged): the tooling-PR rule.
Blocks: nothing. L-0550 and L-0551 append their own mutations to this file later.
## Size
0 added production lines. About 60 lines of test harness (`sabotage_ticket_state.py`) and a net-zero edit to `sabotage.py`. No parser, guard or state machine.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
