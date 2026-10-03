# T-0070 direction          status: ready   risk: high   priority: high

## Ask
Owner (Matthew Badali, 2026-09-27): "i have crew autopilot set approval mode set to self and just had to
approval manually 20+ tickets ... please create a ticket to address".

## What happened (measured, this session)
- `.crew/config.json` has held `autopilot.approval: "self"` since 2026-09-26. The installed crew (1.0.41, then
  1.0.42) does not implement that key; it arrives with T-0010, which is built but not landed. Crew said
  nothing: no SessionStart warning, no line from `/crew:status`, and `/crew:approve`'s text still says
  "only you can". The setting was silently inert.
- Self-approval has a bootstrap loop. T-0010, the ticket that makes self-approval work, itself needed typed
  approvals, and so did everything it depends on (T-0018, T-0024).
- Of the 25 approvals typed on 2026-09-27, 13 changed nothing: tickets already merged (T-0014, T-0015,
  T-0026) or already approved for the same plan (T-0011 twice, T-0012, T-0018, T-0019, T-0021, T-0023,
  T-0024 and others). `/crew:approve` recorded each one again with no "nothing changed".
- The main session also misled: it said the setting was configured and that it would stop asking, before
  the code that honours it existed.

## Recommendation
1. **Inert settings are loud.** `crew_config` gets one table of keys and values per installed version (T-0048's
   `crew_keys.py` if landed, otherwise a small `SUPPORTED` table here). At SessionStart and in `/crew:status`,
   a key or value the installed crew does not act on prints one line naming it, what it would do, and the
   ticket that brings it. For example: "autopilot.approval: self is set, but crew 1.0.42 does not implement it
   (T-0010); plans still need /crew:approve". `crew_autopilot.py settings` prints the same line.
2. **One list of what actually needs you.** `/crew:status --approvals` (and `/crew:approve` with no argument)
   prints only the tickets whose spec and plan exist and whose receipt is missing or stale, as ready-to-paste
   lines, with merged and current tickets left out.
3. **No-op approvals say so.** `/crew:approve` on a merged ticket, or on one already approved for the same
   digests, records nothing new and says "T-0015 is merged - nothing to approve" or "already approved for
   plan <sha> - nothing changed".
4. **Land the self-approval chain first.** Scheduling rule for this repo: T-0018, then T-0024 (group
   approval), then T-0010 go ahead of other lanes. The queue says so at every lane start.
Must-warn and must-stay-quiet tests (an unknown key warns; a supported key does not), plus a test that
the no-op message never hides a stale receipt.

## Open questions (recommendation applies)
- Also refuse to start autopilot while a set key is inert? No: warn only. Refusing would block the work the
  setting is meant to speed up.

## Depends on
Nothing to start. Uses T-0048's key table when it lands. Coordinates with T-0010, T-0024 and T-0050.

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
