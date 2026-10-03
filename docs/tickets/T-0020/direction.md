# T-0020 direction
## Ask
Owner (Matthew Badali, 2026-09-25): "/crew:autopilot should have a few commands: ... focus (using /focus commands and telling it to focus)". The design shown to the owner: `/crew:autopilot focus [ticket]` is a scope lock on one ticket. Out-of-scope findings go to TODO.md, never to the diff. Autopilot refuses to start or switch to another ticket until focus is released (`focus off`). Focus state is per worktree, in crew state. Autopilot reminds the owner that Claude Code's built-in `/focus` only toggles the display, and that only the user can type it. The owner's standing ask also applies (memory `crew-plan-before-execute`, 2026-09-22): "roles drifting into unrelated rabbit holes" is an open problem, and this ticket answers it.
## Options
1. Focus IS the existing active-ticket pointer (`crew_ticket.activate` / `deactivate` / `resolve_active`) (recommended). It is already per worktree, under `<git-common-dir>/crew/`, and protected from Write/Edit by the scope guard. Under `scope.mode` report or block, the scope guard and the completion audit already judge every write against the pointer's ticket. The router refuses a switch while it is set, and `run` stops on drift, using the completion audit's own function as the check.
2. A new focus file beside the pointer. Rejected: it is a second per-worktree ticket pointer that can disagree with the first, and the owner asked for reuse where it fits.
3. A new PreToolUse hook blocking writes outside Touch while focused. Rejected: that is what `scope_guard.py` already does whenever `scope.mode` is not off. A second hook would only add enforcement in the one mode where the owner turned guards off.
## Recommendation
Option 1. No new state, no new hook, no change to `crew_ticket.py`, `scope_guard.py` or `completion_audit.py`. Depends on T-0004 and T-0018 (the router).
## Open questions
none beyond the spec's Unknowns.

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
