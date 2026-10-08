# L-0687 plan: the owner list knows hold, blocked, landing and needs-owner

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, straight after
L-0551 and L-0550, both on this branch.

Refreshed against what landed (the spec's Unknowns):
- L-0550's phase names are `hold`, `landing`, `needs-owner`, `blocked` and `closed`, as the spec
  assumed; L-0550 already added all four to `WAITING`, so this ticket adds none.
- `crew_ticket_state.view` carries `revisit_due` (True, False, None) and `next` (the next.md
  fields), so a `hold` stop reads `view(top, ticket, today)` for its date and reason.
- A `needs-owner` ticket with no `next:` falls back to the first open question before "cannot
  tell", because merged T-0037 records the owner's question under `## Open questions`.
- L-0551's review round 1 already left `landing` and `blocked` out of the list; this ticket counts
  `blocked` instead of dropping it.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot_status.py`, `plugin/crew/tests/test_status.py`

### Step 2: held, blocked, revisit and needs-owner
Files: `plugin/crew/hooks/scripts/crew_autopilot_owner.py`, `plugin/crew/hooks/scripts/crew_status.py`,
`plugin/crew/commands/status.md`

### Step 3: docs
Files: `plugin/crew/README.md`, `docs/guides/crew/src/daily-workflow.md` and its build,
`.crew/codemap/crew.md`, `CHANGELOG.md`
