# L-0655 sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only PR)          status: spec   risk: med
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`. L-0651 to L-0654 must be
merged first; anchors are read from the merged code at plan time.

## Intent
Every must-block branch added by L-0652, L-0653 and L-0654 has a mutation that removes it and a
named test that goes red. The PR changes only harness and ride-along paths.

## Exclusions
- No production change.
- No edit to `plugin/crew/tests/sabotage.py`.
- No mutation for L-0656's keys (it files its own tooling follow-up when it is unblocked).

## Evidence
Read at origin/main `155fe6d8`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (`sabotage*.py` at :79); :99-118 `ALONGSIDE`.
- plugin/crew/tests/sabotage_autopilot.py:28, :170, :473, :674: the tuples and the append pattern.
  L-0651 adds `SLEEP_MUTATIONS` there.
- .crew/verify.json:348-359 (autopilot rule) and :457-468 (harness rule paths).

## Unknowns
- Which of L-0652 to L-0654 have merged when this is planned. Resolved then; the mutation list
  below is cut to match and the PR body names what is left out.

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
- [ ] Each mutation below is in `SLEEP_MUTATIONS` and goes red on its named test through
  `python3 plugin/crew/tests/sabotage.py` restricted to `AUTOPILOT_MUTATIONS`
  (`SABOTAGE SUITE: PASS`):
  - manual state (L-0652):
    - (a) `sleep` skips the `scope.allowCliApproval` check;
    - (b) `sleep` skips the armed check;
    - (c) an expired `until` is honoured;
    - (d) an `until` more than 24 hours after `at` is honoured;
    - (e) an `at` in the future is honoured;
    - (f) an unparseable state file reads `asleep`;
    - (g) a `state` outside the two words reads `asleep`;
    - (h) `wake` inside a window extends past the window end;
    - (i) `sleep` writes with no override configured;
  - log (L-0653):
    - (j) a newline in `--text` is written raw;
    - (k) a `|` in a field is written raw;
    - (l) `sleep-note` writes while awake;
    - (m) `sleep-summary` writes a marker while asleep;
    - (n) an unreadable log reads as empty;
    - (o) a failed log write fails `approve`;
  - deploy (L-0654):
    - (p) `sleep.deploy: all` is applied;
    - (q) day `all` stays `all` asleep;
    - (r) the override is applied when the state is `awake`;
    - (s) the override is applied when the state is `unknown`.
- [ ] Every anchor is present exactly once:
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_every_sleep_sabotage_anchor_is_present_exactly_once`
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q` passes.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`;
  `python3 scripts/_test/tooling-pr.py` passes; the harness rule's suites pass.
- [ ] Crew bumped with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the
  commit. PR body: `Docs: none - tests and harness only` unless a code map line changed.

## Dependencies
- T-0053 (ready; slice 1), L-0651, L-0652, L-0653, L-0654: must be merged first (or cut, and
  named as cut).
- T-0087 (merged): the rule.
Blocks: nothing.

## Size
0 production lines. About 190 lines in `sabotage_autopilot.py`.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
