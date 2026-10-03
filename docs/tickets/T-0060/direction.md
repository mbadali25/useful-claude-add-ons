# T-0060 direction          status: ready   risk: high
## Ask
Split from T-0051 by owner decision, 2026-09-26: "Those features will be a new ticket." The features are T-0051's failure and blocker pings: the `blocker` event and its four reasons (a plan waiting on approval, batched; a ticket out of review rounds with BLOCKs still open; a lane or agent that died or stalled; the verify gate or completion audit refusing at Stop after the session's own retry). The original ask, the owner's brainstorm answers, the options and the approved recommendation are T-0051's: `.work/tickets/T-0051/direction.md` (Ask, Recommendation). The pre-split contract text is `.work/tickets/T-0051/spec.pre-split.md` and `.work/tickets/T-0051/plan.pre-split.md`; where each of its checks and steps went is the `## Split` table in `.work/tickets/T-0051/spec.md`.

Owner context at the split (2026-09-26): basic notifications for now - failure, promotion, deployment and "it stopped". T-0051 carries promotion and deployment (`deploy`) and "it stopped" (`question`); this ticket carries the failure and blocker pings. Every message leads with a short subject naming what happened (T-0051), and this ticket adds one subject per blocker reason.
## Options
Considered once, in T-0051's direction (option 1: one Python sender, `crew_notify.py`, porting the notify skill's send path). This ticket carries one slice of that option; no new options.
## Recommendation
Build the slice on T-0051's `crew_notify.py` (config, filter, dedupe, transport, subjects) and `sabotage_notify.py`. The lane reason reads T-0049's in-flight markers and takes its staleness from T-0049's heartbeat TTL, never a timeout of its own. Depends on T-0051 (the sender) and T-0049 (the lane reason).
## Open questions
none beyond the spec's Unknowns.
## Approval
Status `ready` carries T-0051's direction approval (owner, 2026-09-26: "You can self-approve on these tickets."), recorded at the split.

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
