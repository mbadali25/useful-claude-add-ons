# L-0658 plan - a `--goal` handoff is checked against the goal file

Written by the implementing session, 2026-10-05, after L-0541 and T-0056 on `rush/g6b-goals-sleep`.

## Decisions on the spec's Unknowns

- **L-0541's shape.** `_handoff_ticket` answers a goal line through `crew_autopilot_backlog.handoff_pick`
  (`next_goal_ticket`), and `resume_target` carries `goal`. The goal branch moves above the branch and
  head comparison; the ticket form's comparison is unchanged, in all three sites.
- **No import cycle.** The run-state reader is a new standalone module, `crew_goal_state.py` (json and
  os only). `crew_resume` imports it at the top; `crew_autopilot_backlog` and status use the same one.
- **`decide`.** The goal form skips the two comparisons and checks the goal file instead; the rest of
  `decide` (installed command, author record, consumed-once, fingerprint) is one shared tail,
  `_decide_rest`, so nothing else changes for either form. Every sabotage anchor line is kept.
- **`resume_target`.** Missing, not started, done: fall through with the reason (the next source is
  tried). Unreadable or an unlisted state: stop, could-not-tell. Stopped: stop, naming its recorded
  reason and `/crew:autopilot --goal <slug>`. Status prints the fixed reasons only (`echo=False`).

## Steps

### Step 1: the reader and the three sites
Files: crew_goal_state.py, crew_resume.py, crew_autopilot.py, crew_autopilot_backlog.py,
test_crew_resume.py, test_crew_autopilot_goal_resume.py, test_crew_autopilot_status.py

### Step 2: docs
autopilot.md section 2, crew-context skill, README, CONFIG.md, auto-cycle.md (troubleshooting guide
rebuilt), codemap, CHANGELOG, BUDGETS, verify.json (the new module).

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_goal_resume.py plugin/crew/tests/test_crew_resume.py plugin/crew/tests/test_crew_autopilot_status.py -q
