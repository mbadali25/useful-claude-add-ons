# L-0671: sabotage entries for the auto-replan policy and the successor-plan check; review.md names the policy          status: spec   risk: high
Split from T-0074. Written 2026-10-04 against origin/main `155fe6d8`. Tooling-only PR: no production code, no feature work.

## Intent
Each way the T-0074 guards could wrongly let autopilot reject a review, pass the cap, or approve a successor plan that drops a finding has a sabotage entry that turns a named test red. `commands/review.md` step 3 says that a BLOCK at the last round is rejected and replanned by autopilot when `autopilot.maxAutoReplans` allows, and otherwise stops for the owner as today.

## Design
- New tuple `REPLAN_MUTATIONS` in `plugin/crew/tests/sabotage_autopilot.py`, appended to `AUTOPILOT_MUTATIONS` the way `STATUS_MUTATIONS` is, so `sabotage.py` needs no edit. Same tuple shape: (label, target, find, replace, test).
- At least these mutations, each against `crew_autopilot.py` unless noted:
  1. the default `maxAutoReplans` reads as 1 (`crew_state.py`);
  2. a garbage setting value reads as 1 instead of 0;
  3. an unarmed autopilot may auto-reject;
  4. the `approval_policy` condition is dropped;
  5. a ledger state other than REVIEWED is allowed;
  6. an INCOMPLETE verdict is treated as FINDINGS;
  7. a BLOCK count of 0 is allowed;
  8. a bool BLOCK count is taken as an int;
  9. a round left is ignored;
  10. the reviewer-family condition is dropped;
  11. the cap comparison is off by one (`<` becomes `<=`);
  12. `auto-reject` writes without asking the policy;
  13. `AUTO_REJECT_BY` comparison in the `replan` branch accepts any `rejected.by`;
  14. the `rejected.round` equals latest-round condition is dropped;
  15. (L-0670) `replan_check` strips lines before comparing;
  16. (L-0670) `replan_check` ignores duplicate counts;
  17. (L-0670) a could-not-tell reads as `ok`;
  18. (L-0670) `approve` skips `replan_check`;
  19. (L-0670) FIX lines are not required.
- A test in `plugin/crew/tests/test_crew_autopilot_replan.py` asserts every `REPLAN_MUTATIONS` anchor matches its target exactly once and that every entry is in `sabotage.MUTATIONS`.
- `commands/review.md` step 3: one sentence after "stops for me with 2-4 options", saying that under `/crew:autopilot` with `autopilot.maxAutoReplans` of 1 or more, `crew_autopilot.py next` then names `auto-reject`; `/crew:review` itself still ends at its verdict.

## Exclusions
- No edit to `crew_autopilot.py`, `crew_state.py`, `commands/autopilot.md` or any other production or prompt file outside the harness. If a mutation needs a code change to become testable, that change is a separate feature PR first.
- No edit to `plugin/crew/tests/sabotage.py` (at the `.pylintrc` module line limit).
- No new guard behaviour, no new config key.
- No `Tooling-seam:` trailer: no seam file changes.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (:79 `plugin/crew/tests/sabotage*.py`, :83 `plugin/crew/commands/review.md`); :99-118 `ALONGSIDE` (`plugin/crew/tests/**`, README, BUDGETS, version files, CHANGELOG, `docs/**`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`).
- plugin/crew/tests/sabotage_autopilot.py:1-14 the tuple shape and how `STATUS_MUTATIONS` joins `AUTOPILOT_MUTATIONS`; :16-26 the target path constants; 1118 lines. `.pylintrc:140` `max-module-lines=3400`.
- plugin/crew/commands/review.md:505-507 step 3, closure: any BLOCK "stops for me with 2-4 options".
- CLAUDE.md "Stop and ask": a guard needs a regression suite that is sabotage-tested.
- `.crew/verify.json`'s harness rule runs `scripts/check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, the golden replay, the seam contracts and the canary review whenever a `HARNESS` path changes.

## Unknowns
- The exact find and replace strings depend on the code T-0074 and L-0670 land. Resolved at plan: read the merged `crew_autopilot.py` and write each anchor so it matches once.
- Whether L-0670 has landed. If not, entries 15 to 19 are left out and listed in the PR body as owed.
- The sabotage run is heavy. Resolved at implement: run it through the repo's heavy-run wrapper, one suite at a time, and quote the count.

## Size
No added production lines. About 110 lines in `sabotage_autopilot.py`, about 25 test lines, one sentence in `review.md`.

## Touch
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_replan.py`
- `plugin/crew/tests/test_crew_autopilot.py` - only if its anchor-count test enumerates tuples by name
- `plugin/crew/commands/review.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `.crew/codemap/**`
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt

## Acceptance checks
`.crew/verify.json` rules: the harness rule (runs on any `HARNESS` path) and the autopilot rule (maps `sabotage_autopilot.py`).
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 and reports only tooling changed. `git diff --name-only origin/main...HEAD -- plugin/crew/hooks plugin/crew/commands/autopilot.md plugin/crew/templates` prints nothing.
- [ ] `python3 scripts/_test/tooling-pr.py` passes.
- [ ] `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_sabotage_harness.py -q` passes, including the new `test_replan_mutations_anchor_once_and_are_registered`.
- [ ] The sabotage run reports every `REPLAN_MUTATIONS` entry RED and every restore byte-identical: `python3 plugin/crew/tests/sabotage.py` (through the heavy-run wrapper), with the count quoted in the PR body. After it, `git status --porcelain plugin/crew/hooks` prints nothing.
- [ ] The harness rule's other commands pass: the golden replay, the seam contracts and the canary review, each named in the PR body with its result.
- [ ] `grep -n "maxAutoReplans" plugin/crew/commands/review.md` prints one line, in step 3.
- [ ] crew bumped one patch past origin/main in both version files, CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` exits 0.
- [ ] PR body: `Docs:` line listing README and the code map, the mutations owed if L-0670 has not landed, and that `scripts/_test/drift-detection.sh` was not run.

## Dependencies
- T-0074, direction (spec written 2026-10-04): must be merged; its guard is what entries 1 to 14 mutate.
- L-0670, proposed: should be merged; entries 15 to 19 mutate its check. Not a hard block (see Unknowns).
- T-0087, merged: the tooling-PR rule and its checker.
- Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
