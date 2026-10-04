# L-0668: sabotage mutations for the review policy, the fix phase and the stop contract (tooling-only PR)          status: spec   risk: high
Split from T-0067 on 2026-10-04. Written against origin/main `155fe6d8` (crew 1.0.322). Start only after T-0067 and L-0666 have merged; anchors are taken from the code they land, not from this file.

## Intent
Every rule T-0067 and L-0666 added to `crew_autopilot.py` and `commands/autopilot.md` has a committed mutation that breaks it and a named test that goes red. The PR changes the harness and nothing else.

## Exclusions
- No production code and no prompt: not `crew_autopilot.py`, not `crew_state.py`, not `commands/autopilot.md`. A mutation that stays green means a missing test (add the test here; tests may ride along) or a production bug (stop, file it, fix it in its own feature PR).
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint line limit). New tuples join the tuples `sabotage_autopilot.py` already exports.
- No change to existing mutations, to `review_*.py`, `commands/review.md`, or `scripts/check-tooling-pr.py`.
- No `Tooling-seam:` trailer: no seam path changes.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (`plugin/crew/tests/sabotage*.py`), :99-118 `ALONGSIDE`, :200 prints `tooling-pr: OK - <n> harness path(s) ...`.
- plugin/crew/tests/sabotage_autopilot.py:28 `AUTOPILOT_MUTATIONS`; each entry is `(name, target file, anchor text, replacement, test id)`; :54-65 the three review-phase entries; :473 the tuples are concatenated; :475 `STATUS_MUTATIONS`; :687 `POLICY_MUTATIONS`. 1118 lines.
- plugin/crew/tests/test_sabotage_harness.py:371 `test_every_shipped_anchor_is_present_in_its_target_exactly_once`.
- .pylintrc:140 `max-module-lines=3400`.
- .crew/verify.json: the harness rule runs `scripts/check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, the golden replay, the seam contracts and the canary review whenever a harness path changes (repo CLAUDE.md, "Scope discipline").
- The rules to mutate are in `.work/tickets/T-0067/spec.md` (Design, "Fail closed") and `.work/tickets/T-0067/children/1/spec.md` (Design).

## Unknowns
- Exact anchor text: taken from the merged code at plan time. An anchor must be one line, present exactly once.
- How to run a subset of mutations: resolved at plan by reading `plugin/crew/tests/sabotage.py`'s arguments. If there is no filter, the whole run goes through the host's heavy-run wrapper, once.
- Whether L-0666 has merged. If not, mutations (m) to (o) move to a follow-up and this ticket lands (a) to (l).
- The next free crew patch version is set at implement time.

## Size and split
No production lines. About 60 lines of mutation tuples in one harness file, plus any missing tests. Tooling-only by construction.

## Touch
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_review_policy.py` - only to add a test a green mutation shows is missing
- `plugin/crew/tests/test_crew_autopilot_stop_contract.py` - the same
- `plugin/crew/tests/test_sabotage_harness.py` - only if it pins a mutation count
- `plugin/crew/README.md` - the sabotage count, if stated
- `plugin/crew/BUDGETS.md`
- `.crew/codemap/**`
- `.crew/verify.json` - only if a rule pins the mutation count or timing
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`

## Acceptance checks
Commands run from the repo root; the sabotage run goes through the host's heavy-run wrapper.
- [ ] Each mutation below is in `sabotage_autopilot.py` and turns its named test red under `python3 plugin/crew/tests/sabotage.py`:
  - (a) `clean-only` is treated as `fix-and-rereview`
  - (b) the policy value is normalised (strip, lower) before comparison
  - (c) an `unknown` policy reads as `fix-and-rereview`
  - (d) the default in `AUTOPILOT_DEFAULTS` is `fix-and-rereview`
  - (e) the rounds-left check is dropped, so the final round is fixed and re-reviewed
  - (f) the fixes.md check is dropped (a changed bundle alone goes to review)
  - (g) the bundle check is dropped (fixes.md alone goes to review)
  - (h) the whole-line match becomes a substring match
  - (i) the `## Round <n>` heading is ignored
  - (j) a bundle rebuild failure reads as changed
  - (k) a row with no `findings` reads as nothing to fix
  - (l) the command drops the test-first rule or the outside-Touch refusal from the fix phase
  - (m) a stop with no decision gets a default decision
  - (n) `MECHANICAL` is emptied
  - (o) the FINDINGS stop says "or fixes then /crew:review" again
- [ ] Every existing mutation still goes red, and `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q` passes (anchors present exactly once).
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and `python3 scripts/_test/tooling-pr.py` passes.
- [ ] The harness rule's other checks pass as `.crew/verify.json` runs them: the golden replay, the seam contracts and the canary review. Each is named in the PR body as run or not run.
- [ ] `git diff --name-only origin/main...HEAD` lists only paths in this Touch; none is under `plugin/crew/hooks/` or `plugin/crew/commands/`.
- [ ] `python3 -m pylint plugin/crew/tests/sabotage_autopilot.py` scores 10.00 and the file stays under 3400 lines.
- [ ] Crew is bumped to the next free patch with a CHANGELOG entry (the tests ship inside the plugin directory); after the commit `python3 scripts/check-marketplace.py` passes. PR body: `Docs: none beyond the code map and counts - no behaviour change`.

## Dependencies
Must land first: T-0067 (ready) and L-0666 (filed 2026-10-04). T-0087 (merged): the rule and its checker.
Blocks: nothing. T-0073 should not start before this lands, so it builds on mutated-and-proven rules.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
