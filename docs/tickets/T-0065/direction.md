# T-0065 direction          status: ready   risk: med

## Ask
Reported 2026-09-27 by the TSS session (TSS [2f09b9]) at the owner's request: crew 1.0.41 tooling gaps hit on TheSelectSource. Evidence is TSS's report, quoted in `.work/intake/tss-gaps-2026-09-27.md`.

## Problems (items 3, 7-tmp, 8 and 10, observed)
- **Item 3:** verify.json rule `tss-321-admin-private-documents` names the agent `php-developer`, which is not installed. `/crew:review` reports that as a gap, but nothing warns earlier. `/crew:status` and `/crew:verify` should flag unknown agents.
- **Item 7, the part crew owns:** about 2,900 leftover mktemp git-archive exports from review lanes exhausted /tmp inodes. The guard and the Stop verify-gate then failed closed. Whatever creates these exports must remove them (trap/finally) and use `TMPDIR`. The rest of item 7 (heredoc, python -c, process-substitution, xargs and grep-pathspec refusals) is TheSelectSource's own secrets guard (`.crew/hooks/`, SS10), not crew's, and is reported back to TSS.
- **Item 8:** `crew_upgrade.py --force` overwrites `UPGRADE.md` and rewrites `.crew/config.json`, so a lane cannot reconcile anchors without losing history. Make it append, and back up config before writing (T-0050's backup helper). T-0038 folds upgrade into migrate, so coordinate with it.
- **Item 10:** `codex exec` run from /tmp fails with "Not inside a trusted directory". The provider probe should run from the repo root, or pass `--skip-git-repo-check` for the probe only.

## Recommendation
Four small, independent fixes, one per item, each with a test. If the ticket trips T-0052's split thresholds, split it.

## Approval
Direction approved under the owner's standing authorization (2026-09-26). Open questions take the recommendation.

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
