# T-0019 direction
## Ask
Owner (Matthew Badali, 2026-09-25): "/crew:autopilot should have a few commands: ... assign (give it work to do) ...". The design shown to the owner: `/crew:autopilot assign "<work>"` turns a free-text description into ONE ticket (direction, then spec, then plan), stops for the owner's plan approval (a typed `/crew:approve <id>`; no bypass), then drives it with `run`. It reuses T-0012's `crew_ticket.py mint`.
## Options
1. A thin subcommand over T-0012's `mint` and T-0004's `run` loop, with no goal file (recommended). Autopilot researches the work and writes a complete direction.md. `mint` then allocates the id, and `run`'s loop does spec and plan and stops at approval.
2. A pure alias for `goal "<work>"` capped at one ticket. Rejected: T-0012's goal flow adds a split approval (`/crew:approve goal:<slug>`) and a `.work/autopilot/<slug>.json` goal file before the ticket's own plan approval. For one ticket that is two owner stops where the owner asked for one, and it would mean changing T-0012's split-approval decision.
3. Reuse `/crew:brainstorm`. Rejected: brainstorm is a one-question-per-message dialogue that stops for a direction yes (`plugin/crew/commands/brainstorm.md:32-68`), and the owner asked for one stop, at the plan.
## Recommendation
Option 1. T-0012 covers a single-ticket goal only with that extra split approval and goal file, so T-0019 is not a pure alias. It is thin: one `assign` function, one approval-policy rule, and about 5 lines of prose. Depends on T-0012 (`mint`) and T-0010 (the approval and questions policies), and on T-0018 (the router).
## Open questions
none beyond the spec's Unknowns.
## Amendment (owner, Matthew Badali, 2026-09-26)
The owner's own message: "Another new feature we need to prioritize is giving Autopilot the ability to create tickets and approvals." His answers: (1) "Follow the policy (Recommended)": an assigned ticket is approved under `autopilot.approval` like any other ticket, which reverses the "no bypass" reading above. (2) "T-0019 then T-0012 (Recommended)": `crew_ticket.py mint` is built in this ticket, and T-0012 depends on T-0019 and reuses it. Dependencies are now T-0018 and T-0010. The spec and plan carry the detail and need the owner's re-approval.

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
