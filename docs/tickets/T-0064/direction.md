# T-0064 direction          status: ready   risk: high

## Ask
Reported 2026-09-27 by the TSS session (TSS [2f09b9]) at the owner's request: crew 1.0.41 tooling gaps hit on TheSelectSource. Evidence is TSS's report, quoted in `.work/intake/tss-gaps-2026-09-27.md`.

## Problem (item 6, observed)
`graphify . --no-viz --code-only` scans `config/` and `init.php`/`index.php`/`cron.php`, which are TSS's secrets denylist. No `.graphifyignore` guidance ships, so lanes cannot run the graph refresh safely, and the owner had the lead session run it by hand.

## Recommendation
1. `/crew:init` and the refresh step write or extend a `.graphifyignore` from the repo's secrets denylist (whatever the repo's secrets guard reads). A refresh refuses to run if a denylisted path is not ignored.
2. The crew-graph skill documents it.
3. Test: a fixture with a denylisted file whose content must not appear in `graph.json`.
Note: this repo's CLAUDE.md now makes `graphify update .` the owner of the tracked pair; the same ignore rules apply to it.

## Approval
Direction approved under the owner's standing authorization (2026-09-26). Open questions take the recommendation.

## Evidence (TSS [a8ac98], 2026-09-27 03:56Z)
The owner typed `graphify . --no-viz --code-only` in TSS's `.claude/worktrees/tss-510` (exit 0, 60,860 nodes). TSS's tracked `.graphifyignore` (the same on origin/development and origin/main) keeps `config/` on purpose and does not list init.php/index.php/cron.php. So graphify READ 12 secrets-bearing files: `TSSLive` and `TSSwebsite` `config/env.{development,production}.php`, `TSSwebsite/config/global.config.php`, and each tree's `init.php`/`index.php`/`cron.php`/`newsletter-cron.php`. A literal scan of all 3,035 files under `graphify-out/` for the secret-like values found 0 hits. That is a heuristic, not proof. `graphify-out/` is git-ignored and local to that machine.
Implications for this ticket:
- The check must run BEFORE graphify reads anything. `/crew:graph --refresh` (T-0067) refuses when `.graphifyignore` does not cover every denylisted path, and names the missing ones.
- A raw `graphify` typed by a person bypasses any crew check. So `/crew:init` and `/crew:status` also flag a `.graphifyignore` that misses a denylisted path, before anyone runs it.
- Where the graph could hold secret-derived text, the refresh output is treated as tainted until it is rebuilt with the ignore in place. The runbook: delete `graphify-out/`, fix `.graphifyignore`, rebuild.

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
