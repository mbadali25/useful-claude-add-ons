# L-0651 sabotage mutations for the sleep schedule overlay (tooling-only PR)          status: spec   risk: med
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`; T-0053 must be merged before
this is planned, and its line numbers are re-read then.

## Intent
Every must-block branch T-0053 added has a mutation that removes it and a named test that goes red.
The PR changes only harness and ride-along paths, so it lands alone under the tooling-PR rule.

## Exclusions
- No production change: nothing under `plugin/crew/hooks/scripts/` or `plugin/crew/commands/`.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140`'s limit).
- No new behaviour test beyond what a mutation needs to be caught. If a mutation survives, the
  missing test is added here in `test_crew_autopilot_sleep.py` (an `ALONGSIDE` path) and the gap is
  named in the PR body.
- Nothing for manual sleep, the log or deploy (L-0655 covers L-0652 to L-0654).

## Evidence
Read at origin/main `155fe6d8`.
- scripts/check-tooling-pr.py:58-87 `HARNESS`, `plugin/crew/tests/sabotage*.py` at :79; :99-118
  `ALONGSIDE` (`plugin/crew/tests/**`, version files, CHANGELOG, `docs/**`, `.crew/codemap/**`,
  `.crew/verify.json`, `graphify-out/**`).
- plugin/crew/tests/sabotage_autopilot.py:28 `AUTOPILOT_MUTATIONS`, :170 `DEPLOY_MUTATIONS`, :473
  and :674 the append pattern; :17-26 the path and test-id constants. 1118 lines.
- plugin/crew/tests/test_crew_autopilot.py asserts each `sabotage_autopilot.py` tuple reaches
  `sabotage.MUTATIONS` (stated in `sabotage_autopilot.py:10-13`).
- .crew/verify.json:348-359 maps `sabotage_autopilot.py` to the autopilot rule; the harness rule
  (:457-468) runs `scripts/check-tooling-pr.py`, its suite, the golden replay, the seam contracts
  and the canary review whenever a harness path changes.

## Unknowns
- The exact anchors: they are lines of `crew_sleep.py` and `crew_autopilot.py` as T-0053 lands
  them. Resolved at plan time by reading the merged code.
- Whether `SLEEP_MUTATIONS` targets a new file constant (`SLEEP = os.path.join(SCRIPTS,
  "crew_sleep.py")`). Expected yes.

## Touch
- plugin/crew/tests/sabotage_autopilot.py
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_autopilot.py
- .crew/verify.json
- .crew/codemap/verification-harness.md
- .crew/codemap/crew.md
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- plugin/crew/BUDGETS.md
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

## Acceptance checks
- [ ] `SLEEP_MUTATIONS` exists in `sabotage_autopilot.py`, is appended to `AUTOPILOT_MUTATIONS`,
  and each entry goes red on its named test through
  `python3 plugin/crew/tests/sabotage.py` restricted to `AUTOPILOT_MUTATIONS`
  (`SABOTAGE SUITE: PASS`). At least these mutations:
  - (a) `in_window` treats the end minute as inside;
  - (b) `in_window` ignores the midnight crossing;
  - (c) `parse_schedule` accepts start equal to end;
  - (d) `parse_schedule` matches a prefix, not the whole string;
  - (e) `parse_schedule` accepts hour 24;
  - (f) an override outside `POLICIES` is applied;
  - (g) a malformed schedule reads `asleep`;
  - (h) a raising `resolve` reads `asleep`;
  - (i) a non-object `autopilot.sleep` reads `asleep`;
  - (j) the overlay is applied when the state is `awake`;
  - (k) the overlay writes `deploy`;
  - (l) `approval_policy` skips the `scope.allowCliApproval` check when asleep;
  - (m) an unknown key under `autopilot.sleep` is applied as an override.
- [ ] Every anchor is present exactly once in the file it mutates:
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_every_sleep_sabotage_anchor_is_present_exactly_once`
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q` passes: each new mutation
  reaches `sabotage.MUTATIONS`.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and
  `python3 scripts/_test/tooling-pr.py` passes.
- [ ] The harness rule's suites pass (golden replay, seam contracts, canary), as
  `.crew/verify.json`'s harness rule runs them.
- [ ] `.crew/verify.json`'s autopilot rule text states the new mutation count's source ("count them
  in `sabotage_autopilot.py`"), not a number. Crew is bumped with a CHANGELOG entry;
  `python3 scripts/check-marketplace.py` passes after the commit. PR body: `Docs: none - tests and
  harness only` unless a code map line changed.

## Dependencies
- T-0053 (ready; slice 1): must be merged first.
- T-0087 (merged): the rule.
Blocks: nothing. L-0655 follows the same pattern for the later slices.

## Size
0 production lines. About 130 lines in `sabotage_autopilot.py`.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
