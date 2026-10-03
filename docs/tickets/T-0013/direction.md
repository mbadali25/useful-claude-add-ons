# T-0013 direction
## Ask
Owner decision 6 (Matthew Badali, 2026-09-25), triggered by T-0006's spike FAILING: "if the initialUserMessage spike fails, the typing fallback becomes its own ticket". Title: auto-resume types the resume command into its own session. When `resume.auto` is on and T-0006's decision says resume, reuse crew's existing auto-clear typing path to type the parsed, re-rendered command plus Enter after SessionStart(clear|compact), with the same target verification, a one-shot marker per handoff, defaults OFF, a must-fire/must-not-fire suite with sabotage, no keystroke from any test, and a stated answer to "typing lands before the session is ready".

## Options
1. **A resume mode inside `auto-clear.sh`/`.ps1`, started from the context hook (recommended).** Reuses the method resolution, the owning-pane / window-owner / focus / tab checks, the detached sender and `CREW_AUTOCLEAR_INHIBIT` exactly as they are; only the conditions before them (T-0006's `decide` instead of the wrap-up marker) and the typed text differ. No new hook registration.
2. **A new `resume-type.sh/.ps1` pair registered on SessionStart.** Cleaner file boundary, but a copy of every target check - the second copy is how two guards come to disagree (CLAUDE.md) - and two more registrations. Rejected.
3. **Typing from Python directly (tmux only).** Smallest, but no Windows path and a third sender. Rejected.

## Recommendation
Option 1. Consent is T-0006's `resume.auto` (machine-only, repo veto); the machine's terminal description (`context.autoClear.method`, `windowTitle`, `onlyRepos`/`onlySessions`) is reused as-is; `auto` still never resolves to sendkeys on Windows (owner rule), so native Windows types only under an explicit `method: sendkeys`. Depends on T-0006.

## Open questions
- None blocking. The ready delay's default is measured in plan step 1, not chosen here.

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
