# L-0654 sleep deploy override, nonprod only          status: spec   risk: high
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`. T-0053 must be merged first;
re-read `deploy_allowed` before planning.

## Intent
While asleep, `deploy_allowed` answers as if `autopilot.deploy` were `nonprod` when the repo sets
`autopilot.sleep.deploy: "nonprod"`, and it never allows production: a day value of `all` reads as
`nonprod` for as long as the sleep state lasts.

## Design
- `autopilot.sleep.deploy`: `null` (default) or the exact string `nonprod`. `none` is accepted and
  lowers a day `nonprod` to `none` asleep. `all`, or anything else, is refused: the key keeps the
  day value, with a warning that production is never unattended asleep.
- In the settings overlay, when the state is `asleep`:
  1. apply a valid `sleep.deploy`;
  2. then, if the effective value is `all`, it becomes `nonprod`.
  The result keeps `deploy` (effective) and gains `day.deploy`.
- `deploy_allowed` is otherwise unchanged: the incident check, the one-root rule, the per-layer
  probes and the `ask` on any could-not-tell all run before the settings are read.
- Its `reason` names the sleep state when that changed the answer, for example
  `autopilot.deploy is nonprod (asleep 22:00-07:00; day value none)`.
- State `unknown` applies neither rule: the day value stands. That includes day `all`, which is
  what main does today; the stricter reading would need "could not tell" to lower authority, and
  the warning already says the schedule is unreadable.

## Exclusions
- No dispatch, no workflow run, no consumer: that is T-0045.
- No change to `environments.prodUnattended`, `guards.cloudGuard` or the classifier.
- No log entry for a deploy (arrives with T-0045's consumer and L-0653's `sleep-note`).
- No "deploy failure pings at once" (L-0656, after T-0051).
- No edit to a harness path; no sabotage mutations (L-0655).

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/hooks/scripts/crew_autopilot.py:162 `DEPLOY_VALUES`; :805-815 `_settings_at` reads
  `deploy` and warns when it is not `none`; :880-928 `_decide`, which reads `_settings_at(top)` at
  :904 after its layer checks; :957-986 `deploy_allowed`; :1631-1659 `_cli_deploy`.
- crew_autopilot.py module docstring, "deploy-allowed" section (:124-140): first match wins, and
  `prod` allows only under `all` with both layers and `guards.cloudGuard: block`.
- plugin/crew/tests/test_crew_autopilot_deploy.py: the must-block, must-allow and 324-case matrix
  for the policy (`.crew/verify.json:359`'s rule text).
- plugin/crew/CONFIG.md:2591 section 20 and the `autopilot.deploy` rows at :846 and :2606.

## Unknowns
- Whether T-0045 has landed by then. If it has, its consumer already calls `deploy_allowed`
  before each dispatch and inherits this with no edit; confirm with one end-to-end test there.
- The matrix test's size: adding a sleep dimension multiplies it. Resolved at implement: a
  separate, smaller matrix (state x day value x override x class) in the sleep test file.

## Touch
- plugin/crew/hooks/scripts/crew_sleep.py
- plugin/crew/hooks/scripts/crew_autopilot.py
- plugin/crew/hooks/scripts/crew_state.py
- plugin/crew/hooks/scripts/crew_config_menu.py
- plugin/crew/templates/config.template.json
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_autopilot_deploy.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/tests/test_config_menu.py
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/skills/crew-setup/SKILL.md
- plugin/crew/BUDGETS.md
- plugin/PLUGINS.md
- `docs/guides/crew/**` - guide sources that state the deploy policy, and rebuilt outputs
- .crew/codemap/crew.md
- .crew/verify.json
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

## Acceptance checks
New tests go in `plugin/crew/tests/test_crew_autopilot_sleep.py`; the verify rule is the autopilot
rule that runs `test_crew_autopilot_deploy.py`.
- [ ] Must-allow: day `none`, `sleep.deploy: nonprod`, asleep, class `nonProd`: `verdict=allow`.
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_asleep_allows_nonprod`
- [ ] Must-block, one test each:
  - the same config, awake: `ask`;
  - the same config, state `unknown` (malformed schedule): `ask`;
  - asleep, class `prod`, day `all` with every production condition met: `ask`, never `allow`;
  - `sleep.deploy: "all"`: warning, day value stands, class `prod` asks;
  - `sleep.deploy: true` or a list: warning, day value stands;
  - asleep with an incident file present: `refuse`, as awake;
  - asleep with a config layer could-not-tell: `ask`, as awake.
- [ ] Day `all`, awake, every production condition met: still `allow` (unchanged from main).
  `-k test_awake_production_is_unchanged`
- [ ] The small matrix (state x day value x override x class) matches a table written in the
  test, cell by cell. `-k test_sleep_deploy_matrix`
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_autopilot_deploy.py -q` passes unchanged with
  no schedule set.
- [ ] `settings` no longer reports `autopilot.sleep.deploy` as "not available"; it still does for
  `reviewPolicy`.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; no `HARNESS` path in the diff.
- [ ] Docs: CONFIG.md has the `autopilot.sleep.deploy` row and re-measured leaf counts, and
  section 20 states "production never runs unattended asleep"; README and guides updated and
  rebuilt. Crew bumped with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after
  the commit.

## Dependencies
- T-0053 (ready; slice 1): must be merged first.
- T-0072 (merged): the policy this overlays.
- T-0005 (merged): the environment classifier, unchanged. T-0009 (in-progress): the deploy guard hook; not required first, since `allow` here is necessary and never sufficient.
Coordinates with T-0045 (direction): the consumer. Not required first.
Blocks: L-0655.

## Size
About 50 added production lines. No new parser or state machine.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
