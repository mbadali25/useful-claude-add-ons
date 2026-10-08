# T-0043 direction
Fix: T-0004 follow-up (owner, 2026-09-26: "Accept, land, fix next") - round 2 FIX crew_autopilot.py:419 (the stop after FINDINGS never names a refresh before the next round), FIX crew_autopilot.py:429 (owner-accepted FINDINGS then an edit gets a false "INCOMPLETE" reason), and the 4 NITs (code fences in open questions, INSTALLATION.md:252, others). The plugin.json:3 FIX (1.0.41 shared with T-0005) is moot: land versions are set on the land branch. Findings with repros: uca-t0004 .work/review/T-0004-autopilot-baoVjx/out.txt and .work/followups.md "T-0004 r2".

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). No commit on origin/main carries T-0043's fixes (`git log origin/main --grep T-0043` finds only an unrelated mention); the earlier build branch was never merged and is 280 crew versions behind.

Still true on origin/main:
- FIX 1. The un-accepted FINDINGS stop still ends "or fixes then /crew:review" and names no refresh (`plugin/crew/hooks/scripts/crew_autopilot.py:522-524`). `plugin/crew/commands/autopilot.md:88-89` and `plugin/crew/README.md:907` still say `next` puts a refresh before every later round, which it does not do for a round the human starts after fixing.
- FIX 2. `crew_autopilot.py:540` is still `if latest.get("verdict") != "CLEAN" and not ok:`, so an accepted FINDINGS round whose receipt a later edit staled is told "the reviewer did not finish reading" (`:541-544`) and never reaches `_toward_review` (`:545`).
- NIT `_settles`. The guard at `crew_autopilot.py:346` has no failing control: no test in `plugin/crew/tests/test_crew_autopilot.py` passes a `stale` artifact with `refreshable` False.
- NIT fences. `_open_items` (`crew_autopilot.py:302-328`) has no fence state. A `#` line inside a fenced block under an Open-questions heading closes the section and hides the items after it.
- NIT count. `INSTALLATION.md:253` says crew has "34 slash commands"; `plugin/crew/commands/` holds 36 and `README.md:168` says 36. The number is unmarked, so `check_self_claims` does not check it.

Changed since the spec was written (2026-09-27):
- The codemap NIT is done. `.crew/codemap/crew.md:289-292` now quotes T-0004's CHANGELOG entry as "117 -> 119". Dropped from scope.
- L-0510 put an auto-accept clause in front of the FINDINGS stop's reason (`:515-524`) and made `review_ledger.receipt_stands` the one predicate. FIX 1 edits only the tail of that reason; FIX 2 covers any FINDINGS round whose receipt stands, owner- or auto-accepted.
- T-0087's tooling-PR rule landed. `plugin/crew/tests/sabotage*.py` is a harness path (`scripts/check-tooling-pr.py:79`), and `crew_autopilot.py` and `commands/autopilot.md` are feature files unless declared as seams (`:89-95`). The old plan edits `sabotage_autopilot.py` in the same PR as `crew_autopilot.py`; that PR would now be refused.
- `test_every_autopilot_sabotage_anchor_is_present_exactly_once` (`plugin/crew/tests/test_crew_autopilot.py:1336-1340`) requires every mutation's `find` text to occur exactly once. The old plan rewrote the `:540` line, which is the anchor of "an INCOMPLETE round is rerun unattended" (`plugin/crew/tests/sabotage_autopilot.py:58-61`). A feature PR must leave that line byte-identical.
- T-0010 added the questions policy: the open-questions stop now carries a policy hint (`crew_autopilot.py:449-452`, `:1123-1126`). The fence parser's output feeds that stop unchanged.

Recommended option (taken, owner unavailable): keep the direction, split it three ways.
1. T-0043 (this ticket, feature PR): FIX 1, FIX 2, the `_settles` failing control, the INSTALLATION count with its marker. FIX 2 is a new branch above `:540`, not a rewrite of it, so no harness file moves.
2. L-0642 (feature PR): code fences in Open-questions sections, the owner's 2026-09-27 successor rule (main's parser is the floor, a strict column-0 fence view, anything else is "could not tell" and stops).
3. L-0643 (tooling PR, lands alone): the sabotage mutations for 1 and 2 in `sabotage_autopilot.py`.

Options not taken: (b) one PR as the old plan had it - refused by `check-tooling-pr.py`; (c) drop the fence work - leaves a fail-open in a human stop that two review rounds already confirmed; (d) rebase the old branch - it carries the rejected CommonMark emulation and predates L-0510, T-0010 and T-0087.

## Open questions for the owner
- [x] FIX 2 routes an accepted FINDINGS round with a stale receipt to refresh, then to `/crew:review` unattended, spending the next round, the same as a stale CLEAN receipt does today. Taken: yes, as the approved spec had it. Say so if that round should be a human stop instead.
- [x] The codemap NIT is dropped as already fixed on main. Taken: dropped.
- [x] The sabotage mutations land in one tooling PR after both feature PRs, so the feature PRs carry hand-run sabotage evidence in their PR bodies only. Taken: one tooling PR (L-0643). The alternative is one tooling PR per feature PR.
