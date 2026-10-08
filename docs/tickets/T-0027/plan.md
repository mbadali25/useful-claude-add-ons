# T-0027 plan: status prints no policy-value warning; approve names an unreadable config

Written by the implementing session (rush g6a, 2026-10-05) on `rush/g6a-autopilot`. Anchors re-read
there: `_settings_at`'s policy loop, `settings`' could-not-tell branch, `status`'s return and
`approve`'s unarmed branch. The sabotage anchors `    if not settings(top)["armed"]:` and the
`[self]` case of `test_route_and_status_unaffected_by_approval_policy` are untouched.

### Step 1: red tests
Files: `plugin/crew/tests/test_crew_autopilot_status.py`, `plugin/crew/tests/test_crew_autopilot_policy.py`
- `test_status_prints_no_policy_value_warning` (approval/questions x string/bool/list),
  `test_status_keeps_a_non_policy_warning`, `test_status_keeps_the_could_not_tell_warning`.
- `test_settings_still_reports_a_policy_value_warning`,
  `test_autopilot_approve_names_a_config_it_could_not_read` (not JSON, a top-level list, a
  non-object block).

### Step 2: the change
Files: `plugin/crew/hooks/scripts/crew_autopilot.py`
- `_settings_at` collects `_policy_setting`'s warnings into `policyWarnings` too (still in
  `warnings`, same position); the could-not-tell branch returns `policyWarnings: []`.
- `status` drops `policyWarnings` from the warnings it returns (`.get`, so a dict without the key
  filters nothing).
- `approve`, inside the unchanged armed check, names `_unreadable_autopilot`'s cause when there is
  one. crew_autopilot.py crosses pylint's 3,400-line module cap here; it gains a module-level
  `too-many-lines` disable, as `crew_config.py` carries.

### Step 3: docs
Files: `plugin/crew/CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`
