# L-0550 plan: autopilot stops on hold, landing, needs-owner, cancelled/superseded and blocked

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, against
`crew_ticket_state.py` as merged (L-0639, L-0640) and T-0037 as merged.

Diffed against merged T-0037 first. Already there, so dropped: INDEX `cancelled`/`superseded` in
`INDEX_DONE`, a header `cancelled`/`superseded` read as `closed` quoting a `split-into:` /
`superseded-by:` line, `_closed` reading them, and an INDEX `needs-owner` stop with `WAITING` owner.
What is left: `hold` and `landing`, the header gates as `view` reads them, `next.md`'s reason,
revisit, `next:` and `superseded-by:`, the `blocked` stop, and the status lines.

Deviation for the coordinator's line rule: `crew_autopilot.py` is over pylint's 3,400-line cap
(C-0034), so the logic lives in a new module, `plugin/crew/hooks/scripts/crew_autopilot_gates.py`
(`gate`, `blocked`, `successor`, `FIXED_STOPS`, `WAITING`). `crew_autopilot.py` shrinks: the
INDEX `needs-owner` branch and `_successor` move there. The sabotage anchors named in the HANDOFF
(`if status in INDEX_DONE:`, `if status not in DIRECTION_APPROVED:`, `_closed`'s, `WAITING.get`)
are unchanged.

Open question 5 (header `hold`/`landing`/`needs-owner`): `view` reads them from the header, so
autopilot stops on them (fail-closed); `STATUS_VALUES` is unchanged, so such an edit stales the
approval, which the gate stop precedes. An INDEX `needs-owner` with open questions but no `next:`
names the questions (merged T-0037's behaviour); with neither it says it cannot tell what is asked.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot.py`, `plugin/crew/tests/test_crew_autopilot_status.py`
- Must-block and must-allow cases from the spec's acceptance list; 23 fail on the old code.

### Step 2: the gate read and the blocked stop
Files: `plugin/crew/hooks/scripts/crew_autopilot_gates.py`, `plugin/crew/hooks/scripts/crew_autopilot.py`,
`plugin/crew/commands/autopilot.md`

### Step 3: docs and verify
Files: `plugin/crew/README.md`, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`
