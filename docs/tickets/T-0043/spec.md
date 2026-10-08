# T-0043 T-0004 follow-up: the FINDINGS stop names the refresh; an accepted FINDINGS round is not called INCOMPLETE; `_settles` control; INSTALLATION count          status: spec   risk: med
## Refreshed 2026-10-04
Re-checked against origin/main `155fe6d8` (crew 1.0.322) for hand-off to a cloud session. What changed from the 2026-09-27 spec:
- Narrowed to the first of three slices. The code-fence work moved to L-0642 and every `sabotage_autopilot.py` edit moved to L-0643, because `plugin/crew/tests/sabotage*.py` is a harness path since T-0087 and may not share a PR with `crew_autopilot.py`.
- FIX 2 is now a new branch placed above the INCOMPLETE condition, which stays byte-identical. The old spec rewrote that line; it is the unique anchor of an existing sabotage mutation, and rewriting it would force a harness edit into this PR.
- The codemap NIT is dropped: fixed on main (`.crew/codemap/crew.md:289-292`).
- The INSTALLATION count is 36, not 35, and the line is `:253`.
- Every line number was re-read at `155fe6d8`. Decisions kept from the approved spec: the un-accepted FINDINGS stop still stops, only its reason changes; no new stop ids; the version is set at land.
- `plan.md` in this folder does NOT match this spec. It is the 2026-09-27 successor plan for the old single-PR shape, written against `502cb137` line numbers and a build branch that is not on the remote. Treat it as history. This ticket needs a fresh `/crew:plan T-0043`; its steps 1-3 and the INSTALLATION half of step 6 are a usable outline once re-pointed to the lines below.
- Second pass, same day: every Evidence line was re-read at `155fe6d8` and holds. One check was corrected: the FIX 1 docs grep was line-wise and could not see the wrapped sentence at `autopilot.md:88-89`, so it passed before any change; it now joins lines first.
- No review ledger travels with this hand-off. The old ledger (NEEDS_REPLAN after round 2) lived in the previous checkout's git common dir, so a fresh clone starts at round 1 under the new plan.
## Intent
`crew_autopilot.py next` sends the human the right way after a FINDINGS round. The un-accepted FINDINGS stop names the refresh to run after fixing and before `/crew:review`, so the next round is not reviewed against stale artifacts. A FINDINGS round whose receipt stands (owner- or auto-accepted) and was then staled by a later edit goes to refresh and then review, the same as a stale CLEAN receipt, instead of a false "the reviewer did not finish reading" stop. Two small gaps close with it: `_settles`' refreshable guard gets a failing control, and INSTALLATION.md's crew command count becomes a checked claim.
## Exclusions
- `next` still stops at an un-accepted FINDINGS round. Only the tail of its reason changes; phase `accept-review`, stop true and the empty command stay. The L-0510 auto-accept clause at the front of that reason is not edited.
- The line `    if latest.get("verdict") != "CLEAN" and not ok:` stays byte-identical and occurs exactly once. No edit to any file matching `HARNESS` in `scripts/check-tooling-pr.py`: no `plugin/crew/tests/sabotage*.py`, no `review_*.py`, no `commands/review.md`. The committed mutations are L-0643.
- No code-fence handling in `_open_items`. That is L-0642.
- No change to the phase order, the review budget, `review_ledger.py`, `crew_refresh_check.py`, or any guard or hook.
- No new stop ids. FIXED_STOPS, HUMAN_STOPS and PROCEDURE_STOPS are unchanged.
- `README.md:168`'s unmarked "36 slash commands" stays as it is.
- No `.crew/verify.json` change: no file is added and rule `:348-359` already maps every file this ticket edits under `plugin/crew/`.
## Evidence
All line numbers are origin/main at `155fe6d8`, read on 2026-10-04 with `git show origin/main:<path>`. Nothing was executed for this refresh (the host is memory-bound); the repros below are from reading the code and are re-run by the first plan step.
- FIX 1: the un-accepted FINDINGS stop is `plugin/crew/hooks/scripts/crew_autopilot.py:515-524`. Its reason ends `the owner accepts with review_ledger.py --accept --by <owner>, or fixes then /crew:review` (`:523-524`) and names no refresh. The `how` prefix (`:519-521`) is L-0510's and precedes it.
- Why it matters: a round reviewed after fixing but before refreshing can come back CLEAN with artifacts stale, which is `stale-after-review` (`crew_autopilot.py:561-564`). Refreshing then stales the receipt, and with no round left `next` stops at `:527-531`. `BUDGET` is 2 (`plugin/crew/hooks/scripts/review_ledger.py:133`).
- The claim the docs make: `plugin/crew/commands/autopilot.md:88-89` says "Refresh runs after implement and before each later round, never after an accepted review (that stales the receipt): `next` enforces it." `plugin/crew/README.md:907` ends "any later round goes back through `next`, which puts a refresh before it." Both are true only for a round `next` itself reaches (`_toward_review`, `crew_autopilot.py:548-565`), not for the round a human starts from the FINDINGS stop.
- The refresh the human needs is `crew_refresh_check.py --root . --ticket <id>` followed by each `refresh with` command it prints, committed (described in `plugin/crew/commands/implement.md`; re-grep `crew_refresh_check.py` there for the current lines).
- FIX 2: `crew_autopilot.py:540-544`. The condition is `latest.get("verdict") != "CLEAN" and not ok`. A FINDINGS round gets past `:515` when `review_ledger.receipt_stands` is true (`review_ledger.py:710-733`: owner-accepted at `:727-728`, auto-accepted at `:729-733`). If a later edit staled that receipt, `check_receipt` (`:525`) returns not ok, and with a round left (`:526-527`) the round matches `:540` and is reported as "the reviewer did not finish reading, and it cannot be accepted". `_toward_review` (`:545`) is never reached for it.
- Fixtures for that state exist: `_ledger` `plugin/crew/tests/test_crew_autopilot.py:77`, `_round` `:88`, `_receipt` `:95`, `_receipt_ok` `:100`, `_refresh` `:105`. Expected repro: `_ledger(root, [_round(1, "FINDINGS")], state="ACCEPTED", receipt=_receipt(1, "owner-accepted"))`, `_receipt_ok(monkeypatch, False)`, `_refresh(monkeypatch, "stale")` gives phase `accept-review`, stop true, reason containing "did not finish reading".
- Tests to extend: `test_next_accept_review` `:285`, `test_next_owner_accepted_findings_move_on` `:294`, `test_next_budget_spent_without_a_receipt_stops` `:461-478`, `test_next_incomplete_round_stops` `:481-490`.
- The anchor rule: `test_every_autopilot_sabotage_anchor_is_present_exactly_once` (`test_crew_autopilot.py:1336-1351`) asserts each mutation's `find` occurs exactly once in its target. The mutation "an INCOMPLETE round is rerun unattended" (`plugin/crew/tests/sabotage_autopilot.py:58-61`) finds `    if latest.get("verdict") != "CLEAN" and not ok:\n`. The budget mutation at `:54-57` finds `    if not ok and (not isinstance(left, int) or left < 1):\n`. Neither string may gain a second occurrence or change.
- The tooling-PR rule: `scripts/check-tooling-pr.py:58-88` (`HARNESS`, with `plugin/crew/tests/sabotage*.py` at `:79`) and `:89-95` (`SEAM`, with `crew_autopilot.py` at `:91` and `commands/autopilot.md` at `:94`). An undeclared seam file is feature work, which is what this ticket is.
- The phase table in the module docstring: `crew_autopilot.py:77-81`. Row `:79` reads "latest round INCOMPLETE".
- NIT `_settles`: `crew_autopilot.py:339-348`. The guard is `:346`, `return artifact.get("refreshable", True) is not False`. The test helper `_freshness` (`test_crew_autopilot.py:783-791`) builds artifact rows, and no test passes status `stale` with `refreshable` False: the `stale` rows at `:835` and `:847` both pass True.
- NIT count: `INSTALLATION.md:253` says crew has "34 slash commands". `git ls-tree --name-only origin/main plugin/crew/commands/` lists 36 `.md` files. The marker `<!-- claim: plugin-commands:crew -->` is checked by `scripts/check-marketplace.py:789-812` against `count_plugin_commands` (`:643`), with `PLUGIN_COMMANDS_RE` (`:558`) taking the first `N slash commands` on the bound line; on `:253` the first is crew's. The marker is already used at `plugin/crew/README.md:2822`.
- `autopilot.md` is 109 lines; the budget is `MAX_LINES = 120` (`plugin/crew/tests/test_lifecycle_commands.py:28`).
- Verify rule: `.crew/verify.json:348-359` maps `crew_autopilot.py`, `commands/autopilot.md` and `test_crew_autopilot.py` to the autopilot suites plus `test_lifecycle_commands.py`.
- Version: crew is 1.0.322 at `plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:224` and `plugin/PLUGINS.md:14`.
## Unknowns
- Version number: content change, so crew needs a bump in all three places. Resolved at land: one patch above `git show origin/main:plugin/crew/.claude-plugin/plugin.json` at that moment.
- Whether a FINDINGS round with a stale standing receipt should spend the next round unattended. Decided as the approved spec had it: yes, through `_toward_review`, the same as a stale CLEAN receipt. Listed for the owner in direction.md.
- Auto-accepted receipts: with `BUDGET = 2` an auto-accepted round is round 2, so its stale receipt stops at "no review round left" before the new branch. The new branch is written on the verdict, not the receipt kind, so it stays correct if the budget grows. Accepted as risk; pinned by the must-block case below.
- T-0067 (ready) will rework stop messages and add a contract test for them. If it lands first, re-read the FINDINGS stop before editing and keep its contract. Resolved at plan time by re-grepping `is FINDINGS`.
- Sabotage evidence: the committed mutations wait for L-0643. Until then each fix is sabotaged by hand in a scratch copy and the result is quoted in the PR body. Accepted as risk.
- Docs with no change, to state in the PR body: `plugin/crew/CONFIG.md` (no setting changes) and `docs/guides/crew/src/*.md` (no guide states the refresh-before-review claim; `git grep -n -i "puts a refresh before" origin/main -- docs/guides` is empty).
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md` - only if the autopilot.md line count it records moves
- `INSTALLATION.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `.crew/codemap/**` - refresh only
- `.claude/rules/**` - refresh only
- `docs/diagrams/**` - refresh only
- `graphify-out/**` - refresh only, built with graphify update
## Acceptance checks
Suite command for every pytest check below, which is verify rule `.crew/verify.json:348-359`'s scope: `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q -p no:cacheprovider`.
- [ ] FIX 1: new test `test_next_accept_review_names_the_refresh_before_the_next_round`. With `_ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")`, `next` gives `("accept-review", True, "")` for phase, stop and command, and the reason contains `crew_refresh_check.py --root . --ticket <id>` at a lower index than `/crew:review <id>`. The reason still contains `review_ledger.py --accept --by <owner>`. Red before the change.
- [ ] FIX 1 docs: `cat plugin/crew/commands/autopilot.md plugin/crew/README.md | tr '\n' ' ' | grep -c "puts a refresh before\|before each later round"` prints 0 (the autopilot.md sentence wraps across `:88-89`, so a line-wise grep cannot see it; on origin/main this command prints 1). Both files say instead that the FINDINGS stop names the refresh the human runs after fixing, and that `next` itself puts a refresh before a round only when it reaches that round. `wc -l plugin/crew/commands/autopilot.md` is 120 or fewer and `test_lifecycle_commands.py` passes.
- [ ] FIX 2 must-allow: new test `test_next_accepted_findings_then_an_edit_goes_through_refresh`, parametrised over refresh `stale` and `fresh`. Owner-accepted FINDINGS round 1, `_receipt_ok(False)`: stale gives `("refresh", False, <the refresh command>)`, fresh gives `("review", False, "/crew:review <id>")`. Neither reason contains "INCOMPLETE" or "did not finish reading". Red before the change.
- [ ] FIX 2 must-block: `test_next_incomplete_round_stops` passes unchanged. New `test_next_round_without_a_verdict_stops` (a completed round with no `verdict` key, receipt not ok, artifacts fresh) gives `("accept-review", True)` with "without a verdict" in the reason. `test_next_budget_spent_without_a_receipt_stops` gains the id `round-2-findings-accepted-gone-stale` (`("FINDINGS", "ACCEPTED", _receipt(2, "owner-accepted"))`) and still stops with "no review round left".
- [ ] FIX 2 anchors: `grep -c 'if latest.get("verdict") != "CLEAN" and not ok:' plugin/crew/hooks/scripts/crew_autopilot.py` prints 1, and `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider -k sabotage_anchor` passes.
- [ ] The docstring phase table gains a row for the new branch and row `:79` reads "latest round INCOMPLETE or no verdict"; `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider` passes in full.
- [ ] NIT `_settles`: new `test_refresh_stale_artifact_marked_not_refreshable_stops` (a `stale` artifact with a command and `refreshable` False gives state `unsettled`) and its must-allow twin `test_refresh_stale_artifact_without_the_key_settles` (same artifact, key absent, gives `("stale", <its command>)`). No production change for this item.
- [ ] Hand sabotage, in a scratch copy made with `git archive HEAD plugin/crew | tar -x -C <scratch>`, never the worktree, each quoted in the PR body with the test that went red: the new FINDINGS branch's condition set to `False` reddens the FIX 2 must-allow test; the refresh clause removed from the FINDINGS reason reddens the FIX 1 test; `_settles`' stale return set to `return True` reddens the not-refreshable test.
- [ ] `git diff --name-only origin/main...HEAD` lists no path matching `HARNESS`; `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] `INSTALLATION.md:253` says `36 slash commands<!-- claim: plugin-commands:crew -->`. `python3 scripts/check-marketplace.py` passes after commit, and fails naming `INSTALLATION.md` and `plugin-commands` when the number is set to 35 in a scratch copy.
- [ ] Land: crew is one patch above origin/main in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`; `CHANGELOG.md` has an entry under Unreleased naming FIX 1, FIX 2, the `_settles` control and the INSTALLATION claim; `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0043` says fresh before `/crew:review T-0043`; the PR body carries a `Docs:` line naming the docs changed and `Docs: none` reasons for CONFIG.md and the guides.
## Dependencies
Must land first (all already on main):
- T-0004, merged: the autopilot `next` this ticket corrects.
- T-0008, merged: `crew_refresh_check.py`, the refresh the stop names.
- T-0010, merged: policy plumbing in `next_phase` the tests run through.
- L-0510, done: `receipt_stands` and the auto-accept clause in the FINDINGS reason.
- T-0087, merged: the tooling-PR rule that shapes the split.
Nothing unmerged blocks this ticket.

This ticket blocks:
- L-0643 (sabotage mutations): needs this ticket's branch and tests on main.
- L-0642 (fences) is independent in content but edits the same two files; land this ticket first, then L-0642 merges main in.
Touches the same stop, no ordering required: T-0067 (ready), T-0073 (direction).
## Size
About 15 added production lines (`crew_autopilot.py`: one new branch, one reworded reason, two docstring rows), plus about 60 lines of tests and 6 lines of docs. No new parser, guard or state machine. No harness path. Under the split thresholds once L-0642 and L-0643 are taken out.

## Split
- L-0642 (child 1 of T-0043, filed 2026-10-04): autopilot's open-questions stop sees through code fences, and stops when it cannot tell
- L-0643 (child 2 of T-0043, filed 2026-10-04): sabotage mutations for T-0043's autopilot fixes and the fence parser (tooling PR, lands alone)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
