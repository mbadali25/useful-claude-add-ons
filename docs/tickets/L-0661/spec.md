# L-0661: sabotage mutations for the autopilot routing rows (tooling-only PR)          status: spec   risk: med
Split from T-0057. Written 2026-10-04 against origin/main `155fe6d8`; re-read `crew_route.py` on main after T-0057 merges, because every anchor below is a string T-0057 writes.

## Intent
Each guard T-0057 adds to plain-text routing has a mutation that removes it and a named test that goes red. The PR changes `sabotage_route.py` and nothing that is feature code.

## Exclusions
- No edit to `crew_route.py`, `crew_context.py`, `crew_autopilot.py` or any command, skill or prompt. If an anchor cannot be made unique without changing `crew_route.py`, stop: that is a feature PR first, then this one.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at the `.pylintrc:140` limit). `ROUTE_MUTATIONS` is already imported (`sabotage.py:79`) and registered (`:3066`).
- No new test behaviour. A test may be added to `test_crew_route.py` only if a mutation has no existing test that catches it.
- No mutations for `wave`, `split`, `sleep`, `wake` (L-0663).

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/tests/sabotage_route.py:20-138 `ROUTE_MUTATIONS`, 29 tuples of `(label, target, find, replace, test)`.
- plugin/crew/tests/test_crew_route.py:554-560 `test_every_route_sabotage_anchor_is_present_exactly_once`: each `find` occurs exactly once in its target and each `test` id starts `tests/test_crew_route.py::` or `tests/test_crew_route_hook.py::`.
- plugin/crew/tests/sabotage.py:79 imports `ROUTE_MUTATIONS`; :3066 adds it to the run.
- scripts/check-tooling-pr.py:79 `plugin/crew/tests/sabotage*.py` in `HARNESS`; :99-118 `ALONGSIDE` admits `plugin/crew/tests/**`, version files, `CHANGELOG.md`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`.
- .crew/verify.json:377-381 lists `sabotage_route.py` among rule 30's paths.

## Unknowns
- The exact anchor strings: they exist only after T-0057 merges. Resolved at plan by reading `crew_route.py` on main.
- Whether the harness rule's canary review and golden replay add wall time on the build host. Accepted; they are required for any harness path.

## Dependencies
- T-0057 (ready, spec written 2026-10-04): must be merged first.
- T-0087 (merged): the tooling-PR rule this ticket exists to satisfy.
- Blocks: nothing. L-0663 follows the same pattern for L-0662.

## Size
0 production lines. About 45 lines in `sabotage_route.py`.

## Touch
- `plugin/crew/tests/sabotage_route.py`
- `plugin/crew/tests/test_crew_route.py` - only if a mutation needs a test that does not exist
- `.crew/codemap/crew.md` - the mutation count in the routing section
- `.crew/codemap/verification-harness.md`
- `.claude/rules/**` - regenerated
- `.crew/verify.json` - rule 30's measured figures only
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `graphify-out/**`

## Acceptance checks
- [ ] `ROUTE_MUTATIONS` gains these mutations, each naming the T-0057 test that must go red:
  - the availability gate is skipped (a reserved subcommand routes) -> `test_a_reserved_subcommand_asks_softly`
  - a name the router does not know asks or routes instead of `none` -> `test_a_subcommand_the_router_does_not_know_is_none`
  - the gate's `except` is narrowed so a raising router escapes -> `test_an_unreadable_router_asks`
  - the pronoun guard is dropped (`take care of it` routes) -> `test_autopilot_phrases_that_must_not_route`
  - the shell-character guard is dropped -> `test_free_text_with_shell_characters_asks`
  - `focus on` accepts `it`/`this` -> `test_autopilot_phrases_that_must_not_route`
  - `goal-resume` routes when `--goal` does not stop -> `test_goal_resume_never_picks_a_slug`
  - the not-landed ask renders with the hard "before running anything" tail -> `test_a_reserved_subcommand_asks_softly`
- [ ] Every anchor is present exactly once: `python3 -m pytest plugin/crew/tests/test_crew_route.py -q -k test_every_route_sabotage_anchor_is_present_exactly_once`
- [ ] Every new mutation goes red and the file is restored: `python3 plugin/crew/tests/sabotage.py` reports each new label RED and exits 0 (run under the heavy-run wrapper on a memory-bound host; quote the totals).
- [ ] `git status --porcelain plugin/crew/hooks/scripts/` is empty after the sabotage run (no mutation left applied).
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 and `git diff --name-only origin/main...HEAD` holds no path outside `HARNESS` and `ALONGSIDE`.
- [ ] The harness rule in `.crew/verify.json` (:469-471) ran: `python3 scripts/check-tooling-pr.py`, `python3 scripts/_test/tooling-pr.py`, and the rule's `pytest_rule.py` line (golden replay, seam contracts, canary, refund), copied from the file. Each is named in the PR body with its result.
- [ ] Version bumped, committed, then `python3 scripts/check-marketplace.py` exits 0. PR body carries `Docs: none - test-harness mutations only; code map count updated`.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
