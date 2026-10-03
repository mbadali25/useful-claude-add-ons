# T-0025 direction - contextual help

## Request (owner, Matthew Badali, 2026-09-25, verbatim)
"crew commands should also be understood contextual help make it simple and easy to use"

## Scope, from the coordinator brief of 2026-09-25
1. `/crew:help` with no argument prints at most about 8 lines: where you are (active ticket, phase, what it waits on), the one next command and why, and 2-3 other commands relevant to that state.
2. `/crew:help <command-or-question>` prints the command's purpose in one line, when to use it, its arguments, and what to run next.
3. Contextual nudges: a lifecycle command refused in the wrong state ends with the one command that fixes it. The refusals that leave the user stuck are audited and fixed.
4. Simplify the surface: an advisory recommendation over `plugin/crew/commands/` (33 files on main). Nothing is deleted or renamed here; CLAUDE.md says ask first.

## Recommendation
One state reader and one phrase table. State comes from T-0004's `crew_autopilot.py` (`resume_target`, `next_phase`). Questions resolve through T-0023's `crew_route.PHRASES`. `/crew:help` is a thin command over a read-only `crew_help.py`. Depends on T-0004 (hard) and T-0023 (hard, for the table).

Approved direction: owner request above; coordinator brief of 2026-09-25.

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
