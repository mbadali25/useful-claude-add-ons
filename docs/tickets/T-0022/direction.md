# T-0022 direction
## Ask
Owner, 2026-09-25, verbatim: "/crew:autopilot should auto fix documents, changelog, readme.mds, security.md, to-do.md, update tickets (files, obsidian kanban, jira, sdp, and etc..) and does the crew support obsidian kanban as tickets? if not we need to bring that back and not just bring it back fix it so it fits in here better"

This ticket takes the autopilot half: a docs phase and a tracker phase. The tracker interface it calls is T-0021.
## Options
- A. Run `/crew:docs` inside autopilot and trust it. Rejected: "none of them" is its common answer (`plugin/crew/commands/docs.md:22-23`), and nothing records or checks the decision, so a skipped CHANGELOG looks identical to a considered one.
- B. A read-only docs check that reports each document `updated | not needed (<reason>) | MISSING`, with the CHANGELOG rule mechanical for changed marketplace entries and the rest judgement with a recorded reason; placed like T-0008's refresh, before review. Plus a tracker step that calls T-0021 at each phase change. Recommended.
- C. Put docs after review. Rejected: every doc write after the receipt stales it (`plugin/crew/hooks/scripts/review_ledger.py:391-394`).
## Recommendation
B, with the phase order implement -> docs -> refresh (T-0008) -> review -> done, and tracker moves after every phase change including after review, which is safe only because tracker writes land outside the review bundle (verified in the spec's Evidence and by a test).
## Open questions
none - the Unknowns in spec.md carry the accepted risks.

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
