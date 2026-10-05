# L-0639: cancelled and superseded close a ticket; blocked and needs-replan are derived (crew_ticket_state.py)          status: spec   risk: high
Split from T-0037 (2026-10-04). Feature PR; lands after T-0037.
## Intent
A `cancelled` or `superseded` INDEX row counts as closed everywhere a `done` row does. A new read-only module, `crew_ticket_state.py`, answers for one ticket: which dependencies from its `depends-on:` line are not closed (so it is `blocked`), whether the review ledger says `needs-replan`, and which gating status (`hold`, `landing`, `needs-owner`, `cancelled`, `superseded`) its INDEX cell or header carries. `/crew:spec`'s template shows the optional `depends-on:` line. Nothing acts on the answer yet; L-0550 and L-0551 are the consumers.
## Exclusions
- No `HARNESS` path of `scripts/check-tooling-pr.py`: no edit to `crew_ticket.py`, and no `plugin/crew/tests/sabotage*.py` file (the mutations are L-0641). `python3 scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.
- No `next.md`: `waiting-on`, `next`, `reason`, `revisit`, `superseded-by` are L-0640. `view` returns no such keys here.
- No autopilot stop, no `FIXED_STOPS` entry, no `autopilot.md` edit (L-0550). The only `crew_autopilot.py` change is the `INDEX_DONE` tuple.
- No `/crew:status` change and no `owner_items` (L-0551).
- `hold` stays an open word: `crew_state.read_work` still returns a `hold` row as the open ticket.
- `crew_ticket_state.py` writes no file and runs no subprocess.
- No Obsidian lane, no `crew_tracker.py` edit, no migration of INDEX prose dependencies.
## Evidence
All at origin/main `155fe6d8`.
- `_TABLE_DONE_WORDS = frozenset({"done", "closed", "merged", "shipped", "complete", "completed"})` at `plugin/crew/hooks/scripts/crew_state.py:238-240`, read by `_table_status` (`:243-263`) and `read_work` (`:370`).
- `INDEX_DONE` at `plugin/crew/hooks/scripts/crew_autopilot.py:183`, read at `:433` (the `closed` stop) and `:1446`. `_index_status` is at `:254-263`, `_is_open` at `:266-270`, `open_index_tickets` at `:273-281`.
- `crew_ticket._index_closed` (`plugin/crew/hooks/scripts/crew_ticket.py:831`) returns `(True | False | None, why)` and reads `crew_state._TABLE_DONE_WORDS` at `:860`. After this ticket it returns True for a `cancelled` row, so it cannot be the only read for a dependency.
- `review_ledger.status(root, ticket)` at `plugin/crew/hooks/scripts/review_ledger.py:961`; `NEEDS_REPLAN = "NEEDS_REPLAN"` at `:154`.
- Sabotage anchors that must keep matching exactly once: `"    if status in INDEX_DONE:\n"` (`plugin/crew/tests/sabotage_autopilot.py:126`) and the `:616` anchor. Changing the tuple's contents does not move them.
- `test_table_row_marked_done_is_skipped` at `plugin/crew/tests/test_crew_state.py:350`; `test_next_index_status_that_does_not_say_approved_stops` at `plugin/crew/tests/test_crew_autopilot.py:618`.
- `/crew:spec`'s template is `plugin/crew/commands/spec.md:20-36`; the file is 68 lines against `MAX_LINES = 120` (`plugin/crew/tests/test_lifecycle_commands.py:28`).
- verify: the `crew_state.py` rule is at `.crew/verify.json:179-201`, the autopilot rule at `:348-359`. No rule names `crew_ticket_state.py`.
- From T-0037 (not on main until it lands): `crew_ticket.CLOSING_STATUSES`, `DERIVED_STATUSES`, `header_status`, `parse_depends_on`.
## Unknowns
- An unknown must not read as the safe value. `dependency_state(top, dep)` returns one of `closed`, `open`, `unknown`, `cancelled`, `superseded`, with a reason. Order: read the dependency's INDEX status cell; a closing word returns `cancelled`/`superseded` before any closed-word test; then `_index_closed`; `None` returns `unknown` with its `why`; no row falls back to the dependency's spec header (`done`/`merged` closed, a closing word named, anything else or no spec `unknown` "cannot tell"). Every non-`closed` state blocks. Each has a must-block test.
- Unreadable ledger: `needs_replan` is tri-state (`True`, `False`, `None` with a `problems` entry), never False on a read error. Resolved by a must-block test with an unparsable ledger file.
- A typed `blocked` or `needs-replan` in the INDEX cell is reported in `problems`, not obeyed.
- Who else reads `_TABLE_DONE_WORDS`? At 155fe6d8: `crew_state._table_status` and `crew_ticket._index_closed` only. Re-grep on the land branch; a new reader is reviewed for what a cancelled row now does there.
- `done` counts as closed (approved 2026-09-26). Stated in the README; accepted as risk.
- Import direction: `crew_ticket_state` imports `crew_ticket`, `crew_state`, `review_ledger`; none of them imports it. Resolved by `plugin/crew/tests/test_module_split.py` staying green.
- Version: one patch above origin/main's at land time.
## Touch
- `plugin/crew/hooks/scripts/crew_ticket_state.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/spec.md`
- `plugin/crew/tests/test_ticket_state.py`
- `plugin/crew/tests/test_crew_state.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/**` - guide sources and the rebuilt HTML, DOCX and PDF
- `docs/diagrams/**`
- `.crew/verify.json`
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
## Acceptance checks
- [ ] Closed words: `test_cancelled_and_superseded_rows_are_closed` (parametrised; `read_work` skips the row) and must-allow `test_hold_row_stays_open` in `test_crew_state.py`; `test_index_done_matches_crew_state` in `test_crew_autopilot.py` asserts `set(crew_autopilot.INDEX_DONE) == crew_state._TABLE_DONE_WORDS`; `test_next_cancelled_index_row_is_closed` asserts `next` returns phase `closed`, stop true. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_state.py plugin/crew/tests/test_crew_autopilot.py -q` (verify rules at `.crew/verify.json:179` and `:348`).
- [ ] `test_ticket_state.py` must-block: `test_open_dependency_blocks`, `test_unknown_dependency_blocks` (reason contains "cannot tell"), `test_cancelled_dependency_blocks_and_names_it`, `test_superseded_dependency_blocks_and_names_it`, `test_dependency_row_without_a_status_cell_is_unknown`, `test_needs_replan_is_derived_from_the_ledger`, `test_unreadable_ledger_is_not_read_as_no_replan`, `test_typed_derived_status_in_index_is_reported`. Must-allow: `test_all_dependencies_closed_is_not_blocked` (rows `done`, `merged`), `test_dependency_closed_by_its_spec_header_without_a_row`, `test_no_depends_on_is_not_blocked`, `test_gate_reads_index_first_then_header`. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_ticket_state.py -q`.
- [ ] `test_view_is_read_only` snapshots every file's mtime under the fixture repo before and after `view` and finds no change.
- [ ] `.crew/verify.json` gains a rule: paths `plugin/crew/hooks/scripts/crew_ticket_state.py` and `plugin/crew/tests/test_ticket_state.py`, run `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_ticket_state.py -q`, `reach: local`, a measured `seconds`, and a `why` without any host name. `python3 scripts/check-marketplace.py` passes.
- [ ] `plugin/crew/commands/spec.md` shows `depends-on: [T-####, ...]` as an optional line under the header, says it is hashed (a changed dependency needs `/crew:approve` again), and stays at 120 lines or fewer. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_lifecycle_commands.py -q`.
- [ ] Docs: README's Ticket statuses table (added by T-0037) now says how `blocked` and `needs-replan` are derived, that `cancelled`/`superseded` rows are closed, the could-not-tell rule, and "done counts as closed". The guide source that describes INDEX statuses is updated and `python3 docs/guides/crew/src/build.py` re-run. `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket <id>` prints every line `fresh`.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`. Crew is bumped one patch in the three version files with a CHANGELOG entry; `python3 scripts/gate-runner.py` is green and the PR body names what ran and that `drift-detection.sh` did not.
## Dependencies
- T-0037 (ready; must be merged first): the status tuples, `header_status`, `parse_depends_on`.
- T-0026, T-0021, T-0087 (merged): context.
Blocks: L-0640, L-0641, L-0550, L-0551, T-0052, T-0059.
## Size
About 130 added production lines: `crew_ticket_state.py` about 120 (`dependency_state` 45, `view` 45, constants and docstring 30), `crew_state.py` 1, `crew_autopilot.py` 1, `spec.md` 3 prompt lines. One fail-closed derivation, no parser.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
