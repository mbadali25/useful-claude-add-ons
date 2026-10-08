# L-0670 plan: a successor plan after an automatic reject quotes every BLOCK and FIX line

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, where T-0074
(rush G2) is merged.

Deviation for the line cap: `crew_autopilot.py` is over pylint's 3,400 lines (C-0034), so
`replan_check` and the `replan-check` action live in a new module,
`plugin/crew/hooks/scripts/crew_autopilot_replan.py`, registered through `EXTRA_ACTIONS`;
`approve` calls it after `approval_policy` allows and before `crew_ticket.approve`, keeping the
sabotage-anchored `if not got["allow"]:` line as it is.

Unknowns resolved: `crew_ticket.validate` accepts raw `BLOCK|...` lines in a plan's body (the
tests write them after the plan's steps and approve). T-0074's own full-cycle test wrote a successor
that quoted the BLOCK line inline and not the FIX line; it now quotes both as whole lines.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot_replan.py`

### Step 2: replan_check, the approve refusal, replan-check
Files: `plugin/crew/hooks/scripts/crew_autopilot_replan.py`, `crew_autopilot.py`,
`plugin/crew/commands/autopilot.md`

### Step 3: docs
Files: `plugin/crew/README.md`, `docs/guides/crew/src/troubleshooting.md`,
`docs/guides/crew/src/daily-workflow.md` and the builds, `.crew/codemap/crew.md`,
`.crew/verify.json`, `CHANGELOG.md`
