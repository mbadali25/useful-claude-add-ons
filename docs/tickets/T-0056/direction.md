# T-0056 direction          status: ready   risk: high

## Ask
Owner (the owner, 2026-09-26): "Also, when we do a crew autopilot goal, we need to make sure that
it survives a clear handoff note so that if something happens and we resume, it would resume that
goal."

## What T-0012 already covers, and what it does not (T-0012 spec/plan as approved 2026-09-26)
- **Covered, reading side:** `/crew:autopilot --goal <slug>`, and a handoff `resume: /crew:autopilot
  --goal <slug>`, resume at the goal's next ticket (T-0012 spec acceptance line 82, plan step 3
  `resume_target`). Goal state is in `.work/autopilot/<slug>.json`.
- **Gap 1, nobody writes the goal line.** T-0004 writes `resume: /crew:autopilot <id>` (a ticket)
  when context runs low. The PreCompact hook (`handoff-write.sh` -> `crew_resume.py precompact`),
  T-0017's auto wrap-up and `/crew:handoff` are not told a goal is running. A handoff written
  mid-goal therefore resumes the one ticket and drops the goal: when that ticket finishes, autopilot
  stops instead of moving on to the next.
- **Gap 2, the branch check rejects a goal handoff.** `resume_target` uses a handoff only when its
  `branch:` and `head:` match this checkout (`plugin/crew/hooks/scripts/crew_autopilot.py:504-515`,
  origin/main). A goal moves across ticket branches, so a handoff written on one ticket's branch
  and read after the next ticket's branch was checked out is thrown away.
- **Gap 3, no handoff at all.** A crash, OOM or killed terminal writes nothing. A bare
  `/crew:autopilot` then falls to the active ticket or INDEX and never learns a goal was running.

## Options
1. **The goal file is the source of truth; the handoff is only a pointer (recommended).**
   - The goal file records `state: running|stopped|done` plus the current ticket, updated at every
     phase boundary through a temp file and `os.replace`.
   - Every handoff writer asks one function, `crew_autopilot.resume_line()`, which returns
     `--goal <slug>` whenever a goal is running here and the ticket form otherwise. That covers
     autopilot's low-context stop, PreCompact, T-0017's wrap-up and `/crew:handoff`.
   - A `--goal` handoff is checked against the goal file, not against the branch and head. The goal
     file and each ticket's state on disk decide where to continue.
   - A bare `/crew:autopilot` with no usable handoff looks for running goals first. Exactly one
     resumes; several stop and list them; an unreadable goal file is "could not tell" and stops,
     never "no goal".
2. **Only fix the writers (gap 1).** Smallest change, but a crash or a branch switch still loses the
   goal, which is the "if something happens" case the owner named.
3. **Amend T-0012 instead of a new ticket.** One ticket owns goals end to end, but it stales T-0012's
   fresh approval and grows a ticket that is already high-risk and cross-cutting. Kept separate, as a
   follow-up T-0012 does not wait for.

## Recommendation
Option 1, as a follow-up to T-0012. The acceptance test is the owner's scenario, run three ways:
start a goal, get to ticket 2 of 3, then (a) `/clear` after a normal handoff, (b) switch to ticket 3's
branch before resuming, and (c) kill the session with no handoff. Each must resume the goal at the
correct next phase. Plus the negative: two running goals and no pointer stop and list both.

## Open questions (recommendation applies)
- A `stopped` goal (human stop, cap reached): should bare resume offer it? Recommendation: yes, it
  is named with its stop reason and never resumed silently past a human stop.
- Sleep mode (T-0053) and in-flight markers (T-0049): a resumed goal re-checks both before its first
  phase. No new rule; just do not skip them on the resume path.

## Depends on
T-0012 (goal file, `--goal` resume), T-0006 (grammar, merged), T-0017 (wrap-up writer, if landed).
Coordinates with T-0049 and T-0053. It also belongs in the autopilot guide (T-0054) as a worked
example.

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Not done on main; the problem is still real, and
its prerequisites have not landed.

Still true:
- No goal file exists on main. `goal` is not in `AVAILABLE` (`plugin/crew/hooks/scripts/crew_autopilot.py:224-226`),
  `route` stops `--goal` with "arrives with T-0012" (`:1311-1313`), and `_handoff_ticket` stops a goal
  handoff the same way (`:645-647`). T-0012 is `approved`, not merged; its driving half was split out as
  L-0541 (`direction`). `git log origin/main --grep goal -i` shows no goal work merged.
- Gap 1 (no writer emits the goal line). `plugin/crew/commands/autopilot.md:104-109` tells the low-context
  stop to write `resume: /crew:autopilot <ticket>`. `plugin/crew/commands/handoff.md:17-23` and
  `plugin/crew/skills/crew-context/SKILL.md:96-106` name the grammar but have no rule for a running goal.
- Gap 2 (branch check). The check moved: it is now `crew_autopilot.py:650-661` (was `:504-515`), and the
  same pair of checks sits in `crew_resume.decide` (`plugin/crew/hooks/scripts/crew_resume.py:694-701`)
  and in status's `_resume_line` (`crew_autopilot.py:1507-1513`). Three sites, not one.
- Gap 3 (no handoff at all). `resume_target` falls to the active ticket, then INDEX (`:691-709`), and
  reads no goal file.

Changed since 2026-09-26:
- The PreCompact skeleton writes **no** `resume:` line at all (`plugin/crew/hooks/scripts/handoff-write.sh:91-108`,
  `handoff-write.ps1:392-412`). The skeleton is only written when no handoff exists. So "PreCompact drops
  the goal" is really "PreCompact names nothing"; the fix adds a line there only when a goal is running.
- `crew_resume` already knows the goal form: grammar (`crew_resume.py:126-133`), render (`:148-149`),
  the goal-file existence check (`:706-707`) and the goal file in the progress fingerprint (`:525-529`).
- `_resume_line` is already a private name in `crew_autopilot.py` (`:1478`, status's rendering of the
  handoff line). The new writer-side function is named `handoff_resume` to avoid two meanings of one name.
- T-0017 (auto wrap-up) is still `approved`, not merged: there is no wrap-up writer on main to wire.
- The tooling-PR rule (T-0087) landed: `plugin/crew/tests/sabotage*.py` is harness and cannot ride with
  feature code (`scripts/check-tooling-pr.py` `HARNESS`). `crew_autopilot.py`, `crew_resume.py` and
  `autopilot.md` are `SEAM` files, which matters only to a harness PR.
- T-0012 was split (L-0541 owns driving, caps and `--goal` resume). This ticket now depends on both.

Recommended option: unchanged, Option 1 (the goal file is the source of truth, the handoff is a pointer).
It no longer fits one PR. It is split into this ticket plus three children, one gap each and the sabotage
entries on their own (see spec.md "Size and split"):
- T-0056 (this ticket): run state in the goal file, `handoff_resume`, and every writer that exists on main.
- L-0658: a `--goal` handoff is validated against the goal file instead of `branch:`/`head:`.
- L-0659: bare `/crew:autopilot` with no usable handoff finds running goals.
- L-0660: the sabotage mutations for all three, as a tooling-only PR.

Open questions for the owner (the recommended default was taken in each case):
- A `stopped` goal: bare resume names it with its stop reason and never resumes it. Unchanged from above.
- Several running goals, or an unreadable goal file, when a handoff is written: the writer emits
  `resume: none` and says why. Default taken. The alternative (fall back to the ticket form) silently
  drops the goal, which is the bug.
- The PreCompact skeleton gains a `resume:` line only while a goal runs. Default taken: yes. A skeleton has
  no author record, so auto-resume names it and never types it (`handoff.md:21-23`).
- Build order against T-0017: whichever of T-0017 and this ticket lands second wires the wrap-up writer to
  `handoff_resume`. Default taken: not in this ticket's Touch.
