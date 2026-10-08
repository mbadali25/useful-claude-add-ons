# L-0654 plan - sleep deploy override, nonprod only

Written by the implementing session, 2026-10-05, on `rush/g6b-goals-sleep` (T-0053 and L-0652 on the base).

## Decisions

- **Where.** `crew_autopilot.py` is at pylint's 3400-line limit, so the rule is `crew_sleep.read_deploy`
  and `crew_sleep.deploy_overlay`; `_settings_at` returns `deploy_overlay`'s answer as `deploy` (and
  `day.deploy`), with no new line there.
- **The reason.** `_decide` reads the settings once; it pins the sleep note and `deploy_allowed`
  appends it, so no anchored `return` line of `_decide` changes (sabotage anchors, harness).
- **Manual sleep outside the window** (`tightenOnly`): the override applies only where stricter;
  `all` still reads as `nonprod` (a tightening).
- **The matrix** is a hand-written table in `test_crew_autopilot_sleep.py` (state x day value x
  override x class); the 324-case deploy matrix is untouched.

## Steps
### Step 1: the key and the overlay
Files: crew_sleep.py, crew_autopilot.py, crew_state.py, crew_keys.py, crew_config_menu.py,
templates/config.template.json, skills/crew-setup/SKILL.md, the tests named in the spec.
### Step 2: docs
CONFIG.md (generated rows + section 20), README, configuration reference rebuilt, codemap, CHANGELOG.

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_sleep.py plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py -q
