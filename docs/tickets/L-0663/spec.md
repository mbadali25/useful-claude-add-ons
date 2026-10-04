# L-0663: sabotage mutations for the wave, split, sleep and wake routing rows (tooling-only PR)          status: spec   risk: low
Split from T-0057. Written 2026-10-04 against origin/main `155fe6d8`. Every anchor is a string L-0662 writes; read `crew_route.py` on main after it merges.

## Intent
Each guard L-0662 adds has a mutation that removes it and a named L-0662 test that goes red. The PR changes `sabotage_route.py` and no feature code.

## Exclusions
- No edit to `crew_route.py` or any other production file, command, skill or prompt. An anchor that cannot be unique without a production edit is a stop.
- No edit to `plugin/crew/tests/sabotage.py` (at the `.pylintrc:140` 3400-line limit).
- No mutation for T-0057's own rows (L-0661).

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/tests/sabotage_route.py:20-138 `ROUTE_MUTATIONS`, the tuple shape `(label, target, find, replace, test)`.
- plugin/crew/tests/test_crew_route.py:554-560 the anchor-uniqueness test.
- plugin/crew/tests/sabotage.py:79, :3066 import and registration.
- scripts/check-tooling-pr.py:58-87 `HARNESS`, :99-118 `ALONGSIDE`.
- .crew/verify.json:469-471 the harness rule's commands.

## Unknowns
- The anchor strings (written by L-0662). Resolved at plan.

## Dependencies
- L-0662 (spec written 2026-10-04, not started): must be merged.
- L-0661 (spec written 2026-10-04, not started): must be merged, same file.
- T-0057 (ready) and T-0087 (merged), through those.
- Blocks: nothing.

## Size
0 production lines. About 30 lines in `sabotage_route.py`.

## Touch
- `plugin/crew/tests/sabotage_route.py`
- `plugin/crew/tests/test_crew_route.py` - only if a mutation needs a test that does not exist
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `.claude/rules/**` - regenerated
- `.crew/verify.json` - rule 30's measured figures only
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `graphify-out/**`

## Acceptance checks
- [ ] `ROUTE_MUTATIONS` gains these, each naming the L-0662 test that must go red:
  - a `sleep` pattern loses its whole-prompt bound or gains a trailing wildcard -> `test_wave_split_sleep_wake_phrases_that_must_not_route`
  - the wave rule accepts one id -> `test_wave_needs_two_real_tickets`
  - the wave rule skips the folder check -> `test_wave_needs_two_real_tickets`
  - the split rule takes the first of several open tickets -> `test_split_without_a_resolvable_ticket_asks`
  - bare `this is too big` is added to the split patterns -> `test_wave_split_sleep_wake_phrases_that_must_not_route`
  - `sleep` is dropped from the undo-sentence set -> `test_sleep_route_line_names_the_undo`
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_route.py -q -k test_every_route_sabotage_anchor_is_present_exactly_once`
- [ ] `python3 plugin/crew/tests/sabotage.py` reports each new label RED and exits 0 (heavy-run wrapper on a memory-bound host; quote the totals); afterwards `git status --porcelain plugin/crew/hooks/scripts/` is empty.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; the harness rule's three commands (.crew/verify.json:469-471) ran and are named in the PR body with results.
- [ ] Version bumped, committed, then `python3 scripts/check-marketplace.py` exits 0. PR body carries `Docs: none - test-harness mutations only; code map count updated`.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
