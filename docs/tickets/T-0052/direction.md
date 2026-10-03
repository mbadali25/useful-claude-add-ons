# T-0052 direction          status: ready   risk: high

## Ask
Owner (Matthew Badali, 2026-09-26), asking about the autopilot setting "where you can drive through and
just work on tickets and handoff notes": "This same setting will create and split tickets if need be
as well, and split PRs if something is too big or there's a good reason to." Then: "This is most
likely a crew autopilot command. Go ahead."

Owner answers during brainstorm (2026-09-26):
- **Who decides:** the approval policy. A split is a proposal like a plan, approved under
  `autopilot.approval`. Under `human` it stops, and T-0051 pings it as an approval blocker. Under
  `self`/`risk` autopilot proceeds. This is the same rule the owner chose for T-0019's `assign`.
- **When to check:** after spec and after plan only. No mid-implement split and no re-slicing of a
  finished diff.
- **PR splits come from the plan:** a large ticket that holds together stays one ticket, and its plan
  groups steps into PR slices that ship in order. A ticket that is really two pieces of work becomes
  two tickets.

## What exists (measured 2026-09-26)
- Ticket creation is covered: T-0012 (goal → tickets, before any work) and T-0019 (`assign`, one
  ticket; builds `crew_ticket.mint`). No ticket covers splitting an existing ticket, or shipping one
  ticket as several PRs. T-0011 opens exactly one PR per ticket.
- `/crew:split` (`plugin/crew/commands/split.md`) already has the judgement half: split only on stated
  evidence, 2-5 children, every acceptance criterion lands somewhere or the split stops. Its evidence
  table is the findings-per-ticket rate (`HEALTHY_HIGH` 2.0), the `ticketsTooLarge` trigger, more than
  one subsystem, and criteria that cannot be verified together. It is **Jira-only on purpose**
  ("a files-mode ticket is a markdown file the user can split with an editor"). This ticket
  deliberately reverses that for autopilot, because under autopilot there is no one at the editor.
- The one manual precedent: T-0004 split into T-0010, T-0011 and T-0012, with the parent's text kept
  verbatim at `.work/tickets/T-0004/spec.pre-split.md` and each child's direction pointing back to it.
  That is the shape to automate.

## Options
1. **`/crew:autopilot split [<id>]` plus two automatic checks (recommended).**
   - `next` runs the size check after spec and after plan. The subcommand runs the same check on
     demand.
   - The check takes the evidence rules out of `/crew:split` into shared code, adding plan-time
     measures: subsystems named in Touch, Touch file count, plan step count, and groups of
     acceptance checks that do not share files.
   - **Too big and separable:** write `split.md` (children, the criteria each takes, what each
     excludes, what stays on the parent), approve it under T-0012's `split_policy`, mint children
     with T-0019's `mint`, and keep the parent's text as `spec.pre-split.md` the way T-0004 did.
   - **Too big but cohesive:** the plan gains a `## PR slices` section, and T-0011 ships each slice
     as its own PR in order.
   - **Not too big:** it says so and continues. A check that always finds a split is one nobody can
     trust.
2. **Widen `/crew:split` to files mode and have autopilot call it.** One command for the judgement.
   Tradeoff: `/crew:split` is built around Jira (MCP discovery, cloudId, real issues other people
   see, a confirmation prompt); making it serve both trackers and an unattended caller muddies a
   command whose whole point is care in a shared tracker.
3. **Plan-time only: `/crew:plan` flags "too big" and stops; no autopilot command.** Smallest.
   Tradeoff: it does not do what was asked. Autopilot still cannot split, so an autopilot run just
   stops, and a human splits by hand as with T-0004.

## Recommendation
Option 1, amended by the owner (2026-09-26): "let's just stay in sync with Jira's rules". There is
**one split rulebook**, and both `/crew:split` and autopilot use it in every tracker mode. Autopilot
gets no rule set of its own that could drift from `/crew:split`'s.

- Move `/crew:split`'s judgement rules into shared code: split only on stated evidence, 2-5
  children, every acceptance criterion placed or the split stops, each child's exclusions stated,
  and "not too big" reported as such. `/crew:split` and `/crew:autopilot split` both call it.
- `/crew:split` drops "Jira only" and splits in files and Obsidian mode too, with the same rules and
  the same confirmation. Its Jira path (MCP discovery, cloudId, real issues, links) stays as it is.
- Autopilot creates children through the same path for the tracker in use: Jira issues in Jira
  mode, T-0019's `mint` in files and Obsidian mode.
- `/crew:split`'s human confirmation becomes the approval policy under autopilot. The rules are the
  same; only who says yes differs, and that is the owner's earlier answer.
- The plan-time PR slices and the after-spec/after-plan checks are unchanged. A ticket that holds
  together stays one ticket and ships as ordered PR slices.

This automates the split that was done by hand for T-0004, and puts the PR-slice decision in the
plan, where it is reviewed before any code exists.

## Open questions (resolve at spec)
- Thresholds. Measure them from this repo's history (T-0004's pre-split spec, T-0028's four review
  rounds, T-0005's eight) rather than picking numbers. Say which evidence each threshold rests on.
- PR slices stacked (each based on the previous, merged in order) or independent (each off `main`)?
  Recommendation: independent where the slices do not share files, stacked only where they must. The
  merge-commit rule (D-028) applies to every slice.
- The parent's status after a split. T-0037 adds statuses; `split` or `cancelled` with a pointer to
  the children? Settle it with T-0037 rather than adding a status here.
- SDP mode: `/crew:split` has no SDP path today. Refuse the split there with a clear stop, or add
  one? Recommendation: stop; SDP is a service desk, not where this work gets decomposed.
- Unattended Jira: under `self`/`risk`, autopilot creates real Jira issues other people see with no
  human yes. Allow it, or always require the owner's yes in Jira mode? Recommendation: always ask in
  Jira mode, because that is the one place a wrong split is someone else's mess.
- Review budget: does each PR slice get its own review rounds, or share the ticket's four?

## Depends on
T-0011 (ship), T-0012 (`split_policy`), T-0019 (`mint`). Coordinates with T-0037 (statuses) and
T-0051 (the approval-blocker ping).

## Approval
Direction approved by the owner, 2026-09-26: "You can self-approve on these tickets." Recorded as INDEX status `ready`. Open questions take the recommendation given above.

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
