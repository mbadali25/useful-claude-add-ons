# T-0062 direction          status: ready   risk: high

## Ask
Reported 2026-09-27 by a session working in another repository, at the owner's request: crew 1.0.41 tooling gaps hit in that repository. Evidence is that session's report, quoted in a local intake note that is not published.

## Problem (item 2, observed)
`promote-gate.sh` changes into CLAUDE_PROJECT_DIR (`plugin/crew/hooks/scripts/promote-gate.sh:29`) and blocks on `git status --porcelain` there (`:159`), counting untracked files. So a release run from a clean worktree at the exact ref is blocked because the main checkout holds session files. It also never reads the deploy command's `ref` input. Every worktree-based release in that repository (that night's release to dev and prod) needed an owner-approved bypass.

## Recommendation
Resolve the tree from the command: the `cd`/`-C` target, the working directory, and a `--ref`/`-f ref=` input. Judge that tree and ref. A dirty main checkout matters only when it IS the tree being deployed. If the tree cannot be resolved, the answer is "could not tell", which blocks, as today. The PowerShell twin (`promote-gate.ps1`) changes with it. This is a guard, so it needs a must-block/must-allow suite, sabotage-tested. The existing "first-row" bug in the followups belongs in the same pass.

## Approval
Direction approved under the owner's standing authorization (2026-09-26). Open questions take the recommendation.

## Repro (the other repository's session, observed 2026-09-26 ~23:05Z)
- CLAUDE_PROJECT_DIR: the other repository's main checkout, detached HEAD `<sha A>`, modified tracked files, hundreds of untracked files.
- cwd: a clean release worktree, HEAD `<sha B>`, `git status --short` empty.
- Command: `gh workflow run <deploy workflow>.yml -f environment=development -f ref=$(git rev-parse HEAD)` plus that workflow's other inputs
- Hook, verbatim: "PROMOTION BLOCKED (development): the working tree is dirty. You would be deploying "<sha A>" plus changes that are in no commit and no review. Commit or stash first."
- `$(git rev-parse HEAD)` expands in the cwd (`<sha B>`); the hook judged `<sha A>`.
- **Second finding, a coverage gap and more serious than the false block:** the owner-approved bypass `gh api -X POST repos/<owner>/<repo>/actions/workflows/<deploy workflow>.yml/dispatches -f ref=main -f 'inputs[environment]=development' -f 'inputs[ref]=...'` was NOT matched by promote-gate at all. The same workflow dispatch, spelled through `gh api`, skips the promotion gate. T-0009 (built on its branch) classifies the `gh api` dispatch form in `crew_guards.dispatch_scopes`; promote-gate must use that same parser, not a second one. It needs must-block cases for both spellings and for `inputs[environment]=production`.
- The production run hit the same false block.
- Depends on T-0009 for the shared dispatch parser.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner go 2026-10-04; the owner was not available, so each open question takes the recommended option and is listed in spec.md under "Open questions for the owner".

**Already fixed on main (no longer this ticket):**
- The false block. T-0505 (PR #296, merge `6fe0e0db`, crew 1.0.92) made both flavours judge the tree the deploy runs from: payload `cwd`, a leading `cd` chain, `git -C` (`plugin/crew/hooks/scripts/promote-gate.sh:17-25`, `:253-349`; `_promote_tree.py`). A dirty main checkout no longer blocks a clean worktree.
- The literal `ref` half of "judge the ref". Every 7-40 hex token in the command that resolves to a commit must be the tree's HEAD (`promote-gate.sh:376-384`). Symbolic refs (`ref=main`, `--ref <branch>`) were excluded by T-0505 on purpose and stay excluded.

**Still true (this ticket):**
- The coverage gap. A command is a deploy only when it and a declared `deploy` string contain one another (`promote-gate.sh:140`, `:213`; `promote-gate.ps1:90`). The same workflow dispatch spelled `gh api -X POST repos/<owner>/<repo>/actions/workflows/<wf>/dispatches -f 'inputs[environment]=...'` matches nothing and exits 0 with no check. So does `gh workflow run <wf>` with the inputs reordered or changed.
- The first-row bug. `passed()` returns on the first PROMOTIONS.md row for an environment and sha (`promote-gate.sh:397-407`; `promote-gate.ps1:428-438`), so an early failed row blocks for good and an early pass outlives a later failure.

**Changed since the direction was written:**
- T-0009's parser is not on main. It is PR #336 (branch `T-0009-deploy-guard`, head `f08ae7fb`, crew 1.0.156), owner-accepted at round 6, open, not merged. `git grep "def dispatch_scopes" origin/main` finds nothing. This ticket cannot be built until it merges.
- L-0564 (direction) carries T-0505's accepted round-2 findings in the same files. It is not a dependency; whichever lands second merges main.

**Options**
1. (Recommended, taken) Narrow T-0062 to the dispatch coverage gap and split it: this ticket is the shared reader plus the Bash flavour; L-0664 is the PowerShell twin; L-0665 is the first-row fix, which needs nothing from T-0009 and can land now.
2. Close T-0062 as done by T-0505 and file the gap fresh. Rejected: the gap is the part the direction called "more serious than the false block".
3. Give promote-gate its own small `gh` reader so it does not wait for T-0009. Rejected: the direction forbids a second parser, and T-0009's six review rounds were all bypasses of exactly such a reader.

**Design taken (detail in spec.md):** the substring match stays first and unchanged. Only when it finds nothing, and the map declares at least one deploy that is a workflow dispatch, is the command read with T-0009's reader in `crew_guards`. A dispatch of a declared deploy workflow is that environment's deploy, whichever spelling. A dispatch-shaped line the reader cannot read with certainty, a dispatch of a declared workflow that fits no single environment, and a workflow named by id or display name are "could not tell", which blocks.

Verdict: not obsolete. Spec-ready, blocked on T-0009 merging.
