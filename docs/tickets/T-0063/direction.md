# T-0063 direction          status: ready   risk: med

## Ask
Reported 2026-09-27 by the TSS session (TSS [2f09b9]) at the owner's request: crew 1.0.41 tooling gaps hit on TheSelectSource. Evidence is TSS's report, quoted in `.work/intake/tss-gaps-2026-09-27.md`.

## Problem (items 4 and 5, observed)
- **Item 4:** `crew_autopilot.py next` reads `.work/INDEX.md` from the worktree. In TSS the worktree came from `development`, which has no row for the ticket; the row lives in the main checkout's INDEX. Result: a "cannot tell whether TSS-510's direction is approved" stop for an approved ticket, and the owner added the row by hand.
- **Item 5:** `crew_refresh_check.py` printed "fresh" while 8 refreshed artifacts were uncommitted. It reads the working tree, so "fresh" does not mean "committed".

## Recommendation
1. Ticket-state reads (INDEX row, ticket folder) resolve through the main worktree of `git rev-parse --git-common-dir` when the local copy has no row. The result says which checkout answered, and two rows that disagree stop the run.
2. refresh-check reports `fresh`, `fresh-uncommitted` or `stale`, and every caller that gates on it (autopilot refresh, `/crew:done`) treats `fresh-uncommitted` as not done.
Coordinates with T-0030 (git-backed coordination record), which may subsume the first part.

## Approval
Direction approved under the owner's standing authorization (2026-09-26). Open questions take the recommendation.

## Related finding (T-0029 build, 2026-09-27)
The graph can never read fresh after a change with no topology effect. `graphify update .` (even `--force`) reports "No code-graph topology changes detected; outputs left untouched", so `built_at_commit` stays at the previous commit and `crew_refresh_check` reports the graph `stale`. The only way to make it fresh would be to rewrite history. An unchanged graph with no code-graph change since its commit should read `fresh` (compare the code-file diff since `built_at_commit`, not just the sha). Fold this into the fresh/committed work here.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
