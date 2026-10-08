# T-0056 plan - a running goal is written into every handoff

Written by the implementing session, 2026-10-05, on `rush/g6b-goals-sleep` after L-0541.

## Decisions on the spec's Unknowns

- **Shape.** L-0541 writes `runs` (per-session ticket lists, the ticket cap) and no run state, so this
  ticket adds the `run` block beside it; no schema change (`read_goal` ignores keys it does not check).
- **Where.** `crew_autopilot.py` is at pylint's 3400-line limit, so `goal_mark`, `running_goals`,
  `handoff_resume` and their CLI live in `crew_autopilot_handoff.py`, dispatched through
  `EXTRA_ACTIONS` (`goal-mark`, `handoff-resume`). The spec's `crew_autopilot.handoff_resume` is
  `crew_autopilot_handoff.handoff_resume`.
- **Phase boundary.** L-0541 drives the loop from `goal-run`, so `goal-run` marks `running` (its pick),
  `done` and `stopped` itself; the command marks `running` at each phase start and `stopped` at each
  other stop of a goal run (`autopilot.md` sections 3 and 5).
- **Lock.** Every goal-file write holds L-0541's `goal_lock`.

## Steps

### Step 1: run state and the decider
Files: crew_autopilot_handoff.py, crew_autopilot_backlog.py (`_marked`), crew_autopilot.py (`EXTRA_ACTIONS`),
test_crew_autopilot_goal_resume.py

### Step 2: the writers
Files: commands/autopilot.md, commands/handoff.md, skills/crew-context/SKILL.md, handoff-write.sh,
handoff-write.ps1, test_crew_resume_hook.py, test_lifecycle_commands.py

### Step 3: docs
README, CONFIG.md, auto-cycle.md (troubleshooting guide rebuilt), codemap, CHANGELOG, BUDGETS, verify.json.

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_goal_resume.py plugin/crew/tests/test_crew_resume_hook.py plugin/crew/tests/test_lifecycle_commands.py -q
