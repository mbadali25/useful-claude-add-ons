# L-0639 plan (written by the implementing session, 2026-10-05, on rush/g3-contracts)

Base: origin/release/1.2.0 `e84a8bfe` (crew 1.0.351). T-0037 (#394) is merged there, but it did not
deliver what the spec expected from it: `crew_ticket.CLOSING_STATUSES`, `DERIVED_STATUSES`,
`header_status` and `parse_depends_on` do not exist, and `crew_ticket.py` is a HARNESS path. They are
defined in the new feature module instead; `CLOSING_STATUSES` is pinned equal to
`crew_tracker.CLOSED_STATUSES` by a test. T-0037 already added `cancelled`/`superseded` to
`crew_state._TABLE_DONE_WORDS` and `crew_autopilot.INDEX_DONE`, so neither production file changes;
only the spec's named tests are added.

### Step 1 - closed-word tests
Files: plugin/crew/tests/test_crew_state.py, plugin/crew/tests/test_crew_autopilot.py
Test: test_cancelled_and_superseded_rows_are_closed, test_hold_row_stays_open,
test_index_done_matches_crew_state, test_next_cancelled_index_row_is_closed

### Step 2 - crew_ticket_state.py, test first
Files: plugin/crew/hooks/scripts/crew_ticket_state.py, plugin/crew/tests/test_ticket_state.py
Test: every must-block and must-allow name in the spec, plus test_view_is_read_only

### Step 3 - /crew:spec template, docs, verify rule, codemap, version
Files: plugin/crew/commands/spec.md, plugin/crew/README.md, docs/guides/crew/src/daily-workflow.md
(and its rebuilt HTML/DOCX/PDF), .crew/verify.json, .crew/codemap/crew.md, CHANGELOG.md, version files
