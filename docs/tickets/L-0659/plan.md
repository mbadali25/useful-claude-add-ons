# L-0659 plan - bare `/crew:autopilot` finds a running goal

Written by the implementing session, 2026-10-05, after L-0541, T-0056 and L-0658 on `rush/g6b-goals-sleep`.

## Decisions on the spec's Unknowns

- **`resume_target`'s shape.** It carries `goal` (L-0541). Discovery shares L-0541's argument path:
  `crew_autopilot_backlog.goal_source(top, goal, fallthrough, why, source)` runs whenever no ticket is
  known yet, so `crew_autopilot.py` (at pylint's 3400-line limit) gains no net lines.
- **A stopped goal** is a `fell through:` line (its recorded reason and `/crew:autopilot --goal <slug>`),
  and the run carries on with the active ticket, then INDEX (the owner question's default).
- **Status.** The goal folds into the ticket line, `ticket: <id> (from goal-file, goal <slug>)`, so the
  12-line cap is untouched.
- **A usable ticket handoff** still wins; its `disagreement:` line names the running goal.
- **The context handoff** of a goal run leaves the goal `running` (`autopilot.md` section 5), so the
  next session's handoff, or discovery, resumes it.

## Steps

### Step 1: discovery
Files: crew_autopilot.py (`resume_target`, status's ticket line), crew_autopilot_backlog.py
(`goal_source`, `running_goal_note`), test_crew_autopilot_goal_resume.py, test_crew_autopilot.py

### Step 2: docs
autopilot.md section 2 (one sentence), README "Which ticket", auto-cycle.md and troubleshooting.md
(troubleshooting guide rebuilt), codemap, CHANGELOG, BUDGETS.

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_goal_resume.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py -q
