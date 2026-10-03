# T-0066 direction          status: ready   risk: med

## Ask
Owner (Matthew Badali, 2026-09-27): "Create a ticket to address it". "It" is five T-0023 commits
carrying `Co-Authored-By` lines. The owner's global CLAUDE.md says "Never append Co-Authored-By lines to
commit messages".

## Measured (2026-09-27)
- origin/main: 390 commits carry `Co-Authored-By` (2026-07-28 7280c1fc through 2026-09-26 19ce4d28).
  They are merged and published history.
- Unmerged ticket branches: only `T-0023-build` (5: 33b8e3cc, f86825e8, dcc07374, 311388b7, fa4d8cd5).
- **Where it comes from:**
  1. `plugin/crew/skills/crew-best-practices/references/practices.md:58-60` tells agents that "this
     repository's own attribution requirement ... adds `Co-Authored-By`" and that it wins. That is false
     for this owner, and it ships to every crew user.
  2. The Claude Code harness adds an attribution reminder asking for the trailer, and the main session
     copied it into lane prompts (the T-0005 landing prompt did; that agent correctly refused it).
  3. Workflow lane scripts written before 2026-09-26.

## Options
1. **Stop new trailers at the source, plus one mechanical check; leave history (recommended).**
   - Correct `practices.md`: the owner's instructions decide attribution, and crew never adds a trailer
     on its own.
   - Lane and landing prompts (autopilot, wave lanes, `/crew:implement`, `/crew:promote` land steps)
     say nothing about trailers, so the owner's CLAUDE.md governs.
   - A config key `git.forbiddenTrailers` (global, personal; default `[]`). The scope guard refuses a
     `git commit` whose message (`-m`, `-F` file or `--trailer`) contains a listed trailer, naming the
     key. The same list is checked in `/crew:done` over the ticket's commits, as a finding rather than a
     rewrite. Must-block and must-allow suite, sabotage-tested.
   - The owner's global crew config gets `["Co-Authored-By"]`.
2. **Also rewrite T-0023's five commits.** This changes the head that review round 2 recorded
   (ad74ed35), so the round no longer matches and acceptance and `/crew:done` refuse; it also moves
   every codemap anchor. Only worth it before a review, never after.
3. **Rewrite main's 390.** A force-push of published history, which breaks every clone, every anchor and
   every merged PR's commits. Not proposed.

## Recommendation
Option 1. T-0023's five commits and main's history stay as they are, recorded here as known. The rule
holds from the first commit after this lands.

## Open questions (recommendation applies)
- Should the guard also cover `gh pr create --body` (the owner's PR-body attribution)? No: the owner's
  instructions ask for the Claude Code link in PR bodies. Only commit trailers are listed.

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

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
