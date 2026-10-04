# T-0053 plan            spec: docs/tickets/T-0053/spec.md

Slice 1 of the sleep-mode family only (schedule, resolver, `approval` / `questions` overrides).
Written 2026-10-04 by the implementing cloud session against origin/main `baf193aa` (crew 1.0.325
on main; the spec's anchors were checked at `155fe6d8` and re-checked here). Owner unavailable:
every open question takes the spec's recommended option (HANDOFF.md, "Open questions"). Crew
version for this PR: 1.0.394 (placeholder, re-bumped at landing). No `HARNESS` path is touched.

Anchors re-checked at `baf193aa`: `_settings_at` `crew_autopilot.py:788`, `settings` `:759`,
`deploy_allowed`'s `_decide` reading `_settings_at` `:904`, `POLICIES` `:989`, `_policy_setting`
`:995`, `_decision` `:1022`, `approval_policy` `:1034`, `question_policy` `:1075`, `approve`
`:1129`, the `settings` CLI `:1725-1729`; `AUTOPILOT_DEFAULTS` `crew_state.py:1134`;
`_KNOWN_VALUES` `crew_config_menu.py:67`; `merge_defaults` `crew_state.py:1385` (a non-dict
override of a dict default is discarded, so `autopilot.sleep: "x"` must be detected from the raw
repo file, `crew_state.load_config`, not the resolved one).

### Step 1: `crew_sleep.py`, pure
Files: plugin/crew/hooks/scripts/crew_sleep.py, plugin/crew/tests/test_crew_autopilot_sleep.py
Where: new module; no import of crew_autopilot (crew_autopilot imports it)
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k "parse_schedule or in_window or resolve"
Risk: high - the parser decides when the night values grant authority
- [ ] `KEYS = ("schedule", "approval", "questions")`, `OVERRIDES = ("approval", "questions")`
- [ ] `parse_schedule(value)` -> `(start, end, "")` or `(None, None, reason)`; full-match regex with `[0-9]` classes, hours <= 23, start == end refused, non-str refused
- [ ] `in_window(start, end, minute)`: start inclusive, end exclusive, start > end crosses midnight
- [ ] `now()` returns `datetime.datetime.now()` (the only clock; tests monkeypatch it in-process, no env var or flag)
- [ ] `resolve(block, now, policies)` -> `{"state", "schedule", "overrides", "warnings"}`: non-dict block -> unknown; unknown keys warn "not available in this crew version; it has no effect"; an override outside `policies` warns and is dropped; null schedule -> off; malformed -> unknown; a `now` that is not a datetime -> unknown
- [ ] tests: `test_parse_schedule` (3 accepted, 12 refused), `test_in_window` (10 edges), `test_resolve_*`, `test_crew_sleep_opens_nothing_for_writing`

### Step 2: the overlay in `_settings_at`, and reporting
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_sleep.py
Where: `_settings_at` after the two `_policy_setting` reads; `settings`' could-not-tell return; `_decision`; `approval_policy`, `question_policy`, `approve`; the `settings` CLI
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q
Risk: high - every policy reader, `crew_ticket.accepted` and `scope_guard.py` see the effective value
- [ ] `_settings_at` resolves sleep each call (never cached): asleep -> each valid override replaces the day value; result gains `sleep` (`state`, `schedule`, `overrides`) and `day`; a raising `resolve` -> unknown with a warning; `deploy` / `deploySaw` untouched
- [ ] could-not-tell `settings` return carries `sleep.state = unknown` and never reads sleep
- [ ] reasons end with ` (asleep <schedule>; day value <day>)` while asleep; `approve` prints it after `self-approved ...`
- [ ] `settings` CLI third line `sleep=<state> schedule=<value|none> approval=<override|-> questions=<override|->`
- [ ] tests (spec's acceptance list): must-allow `test_asleep_self_approves_a_high_risk_plan`, `test_asleep_takes_the_recommendation`; must-block one per case (outside window, null schedule, malformed schedule, bad override values, non-object sleep, allowCliApproval not true, unreadable config, raising resolve, unknown key); `test_a_run_that_crosses_the_window_end_returns_to_day_values`; `test_receipt_written_asleep_stops_standing_after_the_window`; `test_taken_line_written_asleep_is_invalid_by_day`; `test_deploy_allowed_ignores_sleep`; `test_asleep_human_refuses`; `test_settings_cli_prints_the_sleep_line`; read-only with a schedule set
- [ ] sabotage by hand (the committed mutations are L-0651, a harness PR): drop the window check, invert the end edge, let a bad override through, swallow the non-object block, cache the resolve; each must turn a named test red

### Step 3: config surface
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config_menu.py, plugin/crew/templates/config.template.json, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/tests/test_crew_config.py, plugin/crew/tests/test_config_menu.py, plugin/crew/tests/test_crew_autopilot.py
Where: `AUTOPILOT_DEFAULTS`; `_KNOWN_VALUES`; the template's and the skill's `autopilot` block
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py plugin/crew/tests/test_crew_autopilot.py -q
Risk: med
- [ ] `AUTOPILOT_DEFAULTS["sleep"] = {"schedule": None, "approval": None, "questions": None}`; `_policy_setting` keeps reading only `approval` / `questions`
- [ ] menu: `autopilot.sleep.approval` and `.questions` offer `human`, `self`, `risk`, unset
- [ ] declared-leaves test names the three leaves; the count re-measured with `leaf_paths(default_config())`

### Step 4: docs, verify rule, version
Files: plugin/crew/CONFIG.md, plugin/crew/README.md, plugin/crew/commands/autopilot.md, docs/guides/crew/src/daily-workflow-scope.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/**, .crew/codemap/crew.md, .crew/codemap/INDEX.md, .claude/rules/**, .crew/verify.json, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/BUDGETS.md
Where: CONFIG.md section 11 rows and section 20 "Sleep"; README "Approval and questions policies"; verify.json policy rule
Test: python3 scripts/check-marketplace.py; python3 plugin/crew/hooks/scripts/crew_instructions.py rules --check --root .; python3 scripts/check-tooling-pr.py
Risk: low
- [ ] autopilot.md: name the `sleep=` line in section 2's settings sentence without adding a line (budget 110)
- [ ] verify.json policy rule gains `crew_sleep.py` and `test_crew_autopilot_sleep.py`, with a measured `seconds`
- [ ] delete `docs/tickets/T-0053/` in the final content commit; the last commit is version-only (crew 1.0.394)
