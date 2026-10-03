# T-0061 direction          status: ready   risk: high

## Ask
Reported 2026-09-27 by the TSS session (TSS [2f09b9]) at the owner's request: crew 1.0.41 tooling gaps hit on TheSelectSource. Evidence is TSS's report, quoted in `.work/intake/tss-gaps-2026-09-27.md`.

## Problem (item 1, observed)
`_default_ref()` tries origin/HEAD, then origin/main, then main. TSS cuts every branch from `development`, so a first `--record` on a fresh ticket branch falls back to the merge-base with main. For TSS-510 that was 8cfbc66d: 492 files instead of 19. That poisons the review bundle and the completion audit. The owner-approved workaround (`git remote set-head origin development`, then clear and re-record) still labels the base "(fallback)".

## Recommendation
1. A repo-only config key, `tickets.baseBranch` (default: origin/HEAD's target), read by every scope-base, review-bundle and audit caller.
2. Record the scope base when the ticket branch is cut (`crew_ticket.py activate`, the `/crew:implement` branch step), not on the first `--record`.
3. When a recorded base is not an ancestor of HEAD, report "could not tell" and never fall back silently.
The tests use a fixture repo whose integration branch is `development`.

## Approval
Direction approved under the owner's standing authorization (2026-09-26). Open questions take the recommendation.

## Repro (TSS [2f09b9], observed 2026-09-27 ~03:40Z)
- `git worktree add .claude/worktrees/tss-510 -b fix/tss-510-srl-refusal-honest-flash origin/development` (HEAD f3d49450, zero ticket commits), then `scope_base.py --root <worktree> --record TSS-510`.
- Output, verbatim: "scope-base: (fallback) recorded 8cfbc66dbfc4 as the start of TSS-510 - the merge-base with the default branch, because HEAD was already past it when first recorded, so the true start is unknown and this shows MORE (.crew/.scope-base)". At the time, origin/HEAD pointed at origin/main.
- `git diff --name-only 8cfbc66d | wc -l` = 492; the true ticket diff (`git diff --name-only f3d49450`) = 19.
- After `git remote set-head origin development`, clearing the entry and re-recording: "(fallback) recorded f3d4945002ca ... merge-base with origin/development". The set is correct, but it is **still labelled fallback although HEAD == the merge-base** (a record at branch-cut, zero ticket commits). A second defect: when HEAD equals the base, the record is exact, and it must say so. Add a test for it.

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
