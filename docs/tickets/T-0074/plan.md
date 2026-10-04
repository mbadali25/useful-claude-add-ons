# T-0074 plan            spec: docs/tickets/T-0074/spec.md

Slice 1 of the T-0074 family only: the `autopilot.maxAutoReplans` opt-in key, `auto_replan_policy`,
the `crew_autopilot.py auto-reject` subcommand, the routing in `next`, and the docs. L-0670 (the
check that a successor plan quotes every BLOCK and FIX line) and L-0671 (sabotage entries and the
`review.md` sentence, tooling-only) are separate PRs. Written 2026-10-04 by the implementing cloud
session against origin/main `baf193aa` (crew 1.0.325). Owner unavailable: each open question takes
the spec's recommended option. Crew version for this PR: 1.0.402 (placeholder, re-bumped at
landing). No `HARNESS` path is touched.

Anchors re-checked at `baf193aa` (unchanged from the spec's `155fe6d8` unless named):
`FIXED_STOPS` `crew_autopilot.py:186`, `HUMAN_STOPS` `:208-220`, `_phase` `:406`, its last line
`return _review_phase(...)` `:480`, `_current_rounds` `:483`, `_review_phase` `:491` (NEEDS_REPLAN
`:497-501`, FINDINGS without a standing receipt `:515-524`), `settings` `:759`, `_settings_at`
`:788`, `approval_policy` `:1034`, `approve` `:1129`, `stops` `:1283`, `WAITING` `:1350`,
`_policy_main` `:1602`, `main` `:1662` (the settings text `:1725-1729`); `AUTOPILOT_DEFAULTS`
`crew_state.py:1134`; `review_ledger.reject` `:803`, `_family_problem` `:475`, `summary` `:946`
(no `rejected` key: the routing reads the raw ledger through `review_ledger.load`).
Dependencies re-read against origin/main `baf193aa`: T-0010, L-0510, T-0004, T-0018 are on main;
T-0029's never-list is still not on main (`scope_guard.py:59-64,118-121` name only `approve`).

Design choices for the spec's Unknowns:
- Reviewer family: call `review_ledger._family_problem(row)` with the same protected-access waiver
  the module uses for `crew_ticket._read_json`, so the two cannot drift; a test compares verdicts
  against `review_ledger.auto_accept_refusal` on a 0-BLOCK copy of each row.
- Routing: `_review_phase` is left as it is. `_phase` passes its answer through one new function,
  `_auto_replan_route`, only when `policy=True`; `status` (`policy=False`) reads today's stops, as
  it already does for the approve phase. This keeps the edit to the functions the spec names.

### Step 1: the setting
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/templates/config.template.json, plugin/crew/tests/test_crew_autopilot_replan.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_deploy.py, plugin/crew/tests/test_crew_config.py
Where: `AUTOPILOT_DEFAULTS`; `_settings_at` after the `maxPhases` read; `settings`' could-not-tell return; the `settings` CLI second line
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py -q -k "setting or unreadable or default"
Risk: med - the key is the switch; anything not a non-negative int must read 0
- [ ] `AUTOPILOT_DEFAULTS["maxAutoReplans"] = 0`, its comment line; template gains the key
- [ ] `_settings_at`: bool, str, float, negative, null -> 0 with a warning naming the value
- [ ] could-not-tell `settings` return carries `maxAutoReplans: 0`
- [ ] settings CLI second line gains `maxAutoReplans=<n>`; `--json` carries the key
- [ ] tests: `test_setting_garbage_reads_zero_with_warning` (5 values), `test_unreadable_config_reads_zero`, defaults dict, declared-key count re-measured by running the test

### Step 2: `auto_replan_policy`, pure
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_replan.py
Where: new function after `approval_policy`; constant `AUTO_REJECT_BY`
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py -q -k "policy or family or refusal"
Risk: high - a guard: it decides when autopilot rejects a review
- [ ] returns `{"allow", "reason", "used", "cap", "round", "blocks"}`; the spec's nine conditions, in order, each with its own reason; anything that raises is "could not tell"
- [ ] tests: must-allow (codex and kimi rounds, `self` and `risk: low`); must-block one per condition (the spec's parametrised list); `test_family_rule_matches_review_ledger`
- [ ] sabotage by hand (committed mutations are L-0671): drop each condition in turn, invert the cap comparison, accept a bool BLOCK count; each must turn a named test red

### Step 3: the `auto-reject` writer
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_replan.py, plugin/crew/tests/test_crew_autopilot_policy.py
Where: new `auto_reject(root, ticket)`; `_policy_main`; `main`'s parser loop and `--ticket` list
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py -q
Risk: high - the module's second writer
- [ ] exit 0 prints `auto-rejected <id>: round <n>, <b> BLOCK / <f> FIX, replan <used+1> of <cap>` then every BLOCK and FIX line verbatim; exit 2 `refused: <reason>` writes nothing; `LedgerError` -> exit 2 with its text; a crash -> exit 1 `refused:`
- [ ] `test_approve_is_the_only_writing_subcommand` replaced by a test naming exactly two writers, `approve` and `auto-reject`; module docstring states the second writer

### Step 4: routing in `next`, stops, status map
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_replan.py, plugin/crew/tests/test_crew_autopilot_status.py
Where: `_phase`'s last line through new `_auto_replan_route`; `FIXED_STOPS`; `HUMAN_STOPS` `review-acceptance`; `WAITING`; the module docstring's phase table
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py -q
Risk: high - a wrong route skips the owner
- [ ] `accept-review` + policy allows -> `auto-replan`, stop false, the `auto-reject` command; cap refusal -> `accept-review` stop with `autopilot.maxAutoReplans (<cap>) reached` and each successor row; any other refusal unchanged
- [ ] `replan` -> stop false `/crew:plan <id>` only when `rejected.by == AUTO_REJECT_BY`, `rejected.round` is the latest round, armed, key >= 1, under the cap, and `approval_policy` allows; else today's stop byte for byte
- [ ] `FIXED_STOPS` gains `auto-replan-cap`; `WAITING` gains `auto-replan`
- [ ] tests: the spec's routing list, including `test_full_cycle_reject_plan_approve_opens_fresh_rounds`

### Step 5: docs, verify rule, version
Files: plugin/crew/commands/autopilot.md, plugin/crew/README.md, plugin/crew/CONFIG.md, plugin/crew/skills/crew-setup/SKILL.md, plugin/PLUGINS.md, docs/guides/crew/src/daily-workflow.md, docs/guides/crew/src/daily-workflow-scope.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/**, docs/diagrams/**, .crew/codemap/**, .crew/verify.json, .claude/rules/**, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/crew/BUDGETS.md
Where: autopilot.md sections 3 and 4 edited in place (110-line budget, 109 used); README "One writer", phase table, Stops, Settings; CONFIG.md key count and section 20
Test: python3 scripts/check-marketplace.py; python3 plugin/crew/hooks/scripts/crew_instructions.py rules --check --root .; python3 scripts/check-tooling-pr.py
Risk: low
- [ ] autopilot.md names `auto-replan`, `auto-replan-cap` and the successor-plan procedure without growing past 110 lines
- [ ] verify.json policy rule gains `test_crew_autopilot_replan.py`, with a measured `seconds`
- [ ] delete `docs/tickets/T-0074/` in the final content commit; the last commit is version-only (crew 1.0.402)
