# T-0068 direction          status: ready   risk: high   priority: high

## Ask
Reported 2026-09-27 by the TSS session (TSS [a8ac98]). TSS-510's /crew:done deadlocks on crew's own
bookkeeping writes. The owner said in TSS the same day: "stop asking me to run those commands and you run them".

## Problem (observed, crew 1.0.41 hooks with 1.0.42 installed)
1. **The completion audit flags crew's own writes as out of Touch.** Check 3 lists `.crew/.scope-base`
   (written by `scope_base.py`) and `.crew/metrics.md` (appended by `review_run.py`). Adding them to Touch
   stales the plan approval, and only a typed `/crew:approve` re-records it. So a ticket that crew's own
   tooling dirtied cannot close unattended.
2. **The verify gate stales the review receipt.** `/crew:done` check 2 needs a verify-gate record. The gate
   writes `.crew/.verify-verified-at` and `.crew/.verify-gate.*`, which a repo's `.gitignore` may not ignore,
   and `review_patch.py` excludes only `.work/`. So running the gate adds untracked files to the bundle and
   stales check 1's accepted receipt. With the last round already accepted, no round is left: a deadlock.
3. **`review_run.py` appends `.crew/metrics.md` after the bundle is taken,** and review.md step 3.6 appends
   again. Either stales the receipt.

## Recommendation
- One list, `crew_state.CREW_BOOKKEEPING_PATHS` (`.crew/.scope-base`, `.crew/metrics.md`,
  `.crew/metrics.jsonl`, `.crew/.verify-verified-at`, `.crew/.verify-gate.*`, `.crew/guard.log`, and every
  other path a crew script writes on its own). It is excluded from the review bundle, the receipt digest,
  the completion audit's Touch check and scope_guard's out-of-Touch judgement, the way
  `REFRESH_ARTIFACT_PATHS` already is. A test walks every crew script's write targets (by AST or by a
  declared WRITES constant) and fails if one is missing from the list.
- `/crew:init` and `/crew:migrate` also add the untracked ones to the repo's `.gitignore` (or
  `.git/info/exclude` when the owner declines the tracked edit), and `check_crew_ignore_policy` knows them.
- Metrics are appended only after acceptance or `/crew:done`, never between bundling and the receipt.
- Must-block (a real out-of-Touch file still fails the audit) and must-allow (bookkeeping never does),
  sabotage-tested. This is a guard change.

## Depends on
Nothing to start. T-0010 (self-approval) removes the re-approval half for tickets whose Touch really
must grow. Coordinates with T-0067 (autopilot runs mechanical steps) and T-0046 (review bundles list
graphify-out by hash).

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

## More evidence (TSS [a8ac98], 2026-09-27, TSS-510)
- `verify-gate.sh --all` writes `.crew/.verify-gate.record.json` and `.crew/.verify-gate.timings.json` as untracked files, and that staled TSS-510's receipt (bundle 1028da4e -> edee5c83). Deleting both restored it. Both belong in `CREW_BOOKKEEPING_PATHS`.
- **Refresh artifacts with no verify rule fail the gate.** `.claude/rules/*`, `.crew/codemap/*` and `docs/diagrams/*` were committed by the ticket's own refresh step, and the gate reports unmapped paths as a failure. The gate should treat `REFRESH_ARTIFACT_PATHS` as mapped (they have their own freshness check) rather than unmapped.
- **Known-failure allowance.** Every rule touching TSS-510's code runs `bash _verify/smoke.sh`, which always fails `local:srl-merged-away-backfill` when run as root (TSS F496, pre-existing and on main too). Proposed: a repo-only `verify.knownFailures` list of named check ids, each with a ticket reference and an expiry. The gate reports those as `known-fail`, never `pass`. It never covers a check that passes on main but fails on the branch (a regression), and the done report lists each one. Must-block: a new failure outside the list; the same id failing on the branch but passing on main.

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
