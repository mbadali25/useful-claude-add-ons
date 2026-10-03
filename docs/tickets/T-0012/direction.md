# T-0012 direction
## Ask
Split from T-0004 by owner decision (Matthew Badali, 2026-09-25): "autopilot goals and ticket minting". The original ask, options and the approved recommendation are T-0004's: `.work/tickets/T-0004/direction.md` (Ask, Recommendation); the pre-split contract text is `.work/tickets/T-0004/spec.pre-split.md`.
## Options
Considered once, in T-0004's direction (option 1, /crew:autopilot as a lifecycle driver over the 1.0 commands, recommended and approved). This ticket carries one slice of that option; no new options.
## Recommendation
Build the slice on T-0004's `crew_autopilot.py` (next_phase, parse_risk, settings). Depends on T-0004.
## Open questions
none beyond the spec's Unknowns.
## Amendment (owner, Matthew Badali, 2026-09-26)
The owner's answers: (1) "Follow the policy (Recommended)": the split proposal and each minted ticket are approved under `autopilot.approval`, the tickets one at a time through T-0010's per-ticket path and never through T-0024's owner-only group confirm. (2) "T-0019 then T-0012 (Recommended)": `crew_ticket.py mint` moves to T-0019, and this ticket depends on T-0019 and reuses it. Dependencies are now T-0019, T-0010 and T-0018 (T-0004 and T-0006 are merged). The spec and plan carry the detail and need the owner's re-approval.

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

## Split 2026-09-30 (owner 2026-09-30 "Triage pass now")

Owner decision 2026-09-30 ~11:30: oldest tickets first, 1-2 deliverables per ticket, extras split into new tickets.

Kept in T-0012: plan Steps 1-2 (the goal file and proposal; split approval by the owner's prompt or the same policy), plus Step 4's `goal` subcommand, sabotage, docs and version for those.

Moved:
- L-0541: plan Step 3, mint on approval, backlog arming, dependency order, per-ticket approval, caps, `--goal` resume.

spec.md and plan.md are APPROVED and were not edited. Before implement, they need a successor amendment narrowed to the kept scope, and a re-approval.
