# T-0029 direction - /crew:autopilot parallel lanes

Status: direction APPROVED by the owner 2026-09-25 ("i like that approve the spec"). See Decided.

## Ask (owner, Matthew Badali, 2026-09-25, verbatim)
"do we have /crew:autopilot should drive more than just one ticket"
Offered: (1) amend T-0012 so backlog mode also drains already-approved tickets;
(2) file a new ticket for parallel lanes - several tickets at once, each in its own worktree.
"Lets go with optino 2."
"maybe the command would be /crew:autopilot workflow"
"maybe the command would be /crew:autopilot workflow (where we can go through ticket spces and we
work out design and I will approve and then it will work it and make its own decisions [configurable])
and complete the full workflow the crew has [ brainstorm -> spec -> approve -> impelment -> review -> done]"
"please bring in mutliple sub agents oto help with the crew workflow so that it can ask questions
and approve (if auto approve) isn't enabeld and etc"

## Shape the owner described (2026-09-25; restated, the verbatim text above governs)
1. Design together: `/crew:autopilot workflow` walks the owner through several tickets' specs
   interactively - brainstorm and spec - and the design is worked out with the owner.
2. One human gate: the owner approves.
3. Autonomous run: autopilot then works the approved tickets through implement -> review -> done,
   making its own decisions, and how much it may decide alone is configurable (T-0010's approval
   and questions policies are the existing home for that setting).
4. It covers the whole crew lifecycle: brainstorm -> spec -> approve -> implement -> review -> done.
Related, same day: "I want it to review the crew plugin and what we are doing and ask if its
work it to use /workflows command in with auto pilot ?"

## Background
- T-0004 drives one ticket (`.work/tickets/T-0004/spec.md:9`). Its direction deferred
  parallel lanes: "Parallel lanes (worktrees + a writer agent) deliberately out of scope;
  file as a follow-up." (`.work/tickets/T-0004/direction.md:37`). This is that follow-up.
- T-0004, T-0012 and T-0019 each exclude parallel tickets, worktree lanes and a writer
  subagent (`.work/tickets/T-0004/spec.md:17`, `.work/tickets/T-0012/spec.md:12`).
- T-0012's `mode: backlog` is sequential, in dependency order (`.work/tickets/T-0012/spec.md:65`).
- This session already landed tickets in parallel through a workflow ("crew-land-lanes",
  `.crew/handoffs/HANDOFF-20260926-0119.md`).

## Constraints already fixed elsewhere (to be confirmed, not re-decided)
- Every existing gate still decides: approval receipt, scope guard, verify gate, review
  ledger, completion audit. A lane never starts an unapproved ticket.
- Only tickets whose dependencies are all closed can run in parallel.
- Version bumps: each lane that changes a plugin bumps it, and landing must respect version
  order (CLAUDE.md "Content change with no version bump"; handoff dead end: "letting the
  workflow land out of version order").

## Decided (owner, 2026-09-25)
Owner: "do you think /crew:autopilot wave would be better than workflows ... I am looking for it to
ask questions , figure out problmes nad make its own decisions if i enable it" -> "i like that
approve the spec".
- Command: `/crew:autopilot wave` (not `workflow`, not `lanes`). The Workflow tool is an optional
  engine underneath it; plain parallel `Agent` lanes are the fallback with the same lane prompts.
- Ask questions: a lane never prompts the owner. It stops, writes its question, and the main
  session batches every lane's questions and approval requests to the owner in one message.
- Figure out problems: before asking, a lane researches (researcher/explorer) and writes the
  question with its recommendation first (T-0010's questions research).
- Own decisions, only when enabled, all default off: T-0010's plan approval policy (`self|risk`),
  a questions policy that takes its own recommendation, and a review policy
  (`clean-only`; `fix-and-rereview` = fix findings and re-review within the round cap).
- Never, whatever the config: autopilot accepting a review with findings, or writing an
  `owner-accepted` receipt; `gh pr merge --admin`. Exhausted rounds stop for the owner.
- Everything else in the Recommendation below stands as the direction.

## Options (from the independent Fable 5.1 review, 2026-09-25)
Evidence cited by that review; [V] = it read the code or run record, [J] = its judgement.
- A. Workflow tool for the autonomous run only (implement -> refresh -> review, then land).
  Deterministic fan-out; proven here by `crew-land-lanes` [V]. Costs: a permission dialog per
  run, no mid-run steering, resume only within the starting session, and crew's ledger steps are
  not idempotent - a resumed run re-reserved a bundle (`refused: true`) and re-recorded a round
  ("round 4 already has a result") [V, that run's journal].
- B. `Agent` with `isolation: worktree`, fanned out from the main loop. No opt-in and no replay
  problem, but every lane's output lands in the main session's context.
- C. Both: A when the owner opts in, B as the fallback with the same lane prompts.
- Out of reach of any option: design/brainstorm/spec (a background run cannot hold a dialogue [J]),
  approval (`approval_hook.py` records only from UserPromptSubmit [V]), and review acceptance
  (the owner's, T-0004 spec:21 [V]). The land-lanes run accepted rounds by subagent under ad hoc
  delegation; shipped as a feature that is the bypass T-0010 excludes.

## Recommendation (the review's final answer to the owner's shape; not yet the owner's)
- C, split by phase: the main session designs and approves; a workflow runs the wave over
  pre-placed worktrees (`crew_state.py --worktree-path`). Plain `Agent` + `isolation: worktree` is
  the fallback, but it picks its own path (`emergency.md:66-68`), so the active-ticket entry cannot
  be pre-set.
- 1. Design phase stays in the main session: the command loops `/crew:brainstorm` -> `/crew:spec`
  -> `/crew:plan` per ticket and writes a set file `.work/autopilot/<set>.json` (ids, deps). The
  hand-off to the wave is the moment every id in the set has a current approval receipt.
- 2. The one approval is T-0024's group approval: the owner types `/crew:approve T-a T-b`, then
  `--confirm`. Both are UserPromptSubmit, so no new hook path; autopilot prints the line and waits.
- 3. "Its own decisions [configurable]": T-0010 covers plan approval and questions. Autonomous
  review acceptance is NOT offered: `check_receipt` trusts `kind: owner-accepted`
  (`review_ledger.py:383-386`), so a policy-written receipt would make that label lie. Instead
  `autopilot.reviewPolicy: clean-only` - proceed on a CLEAN round, stop on FINDINGS.
- 4. Stay separate from T-0012 but share the set file and the wave runner: `goal` is a
  machine-proposed split, this command an owner-designed set; both end in the same approved set.
- 5. Name: `wave` (or `set`), not `workflow` - it collides with Claude Code's `/workflows` and the
  Workflow tool, and must work when the tool is absent. Args: `wave <T-a> <T-b>...`, `--set <slug>`,
  `--all-approved`; bare `wave` shows the set and stops. (An earlier pass of the same review
  suggested `lanes`.) Owner to decide.
- First slice: `wave` over tickets that are approved, dependency-free and not `direction`-status;
  lanes run implement -> refresh -> review rounds (record only, never accept); serial land only for
  CLEAN rounds; FINDINGS stops for the owner. Depends on T-0004 and T-0018; not on T-0012.
- Must-block: a lane on an unapproved ticket; a lane whose dependency is open; a lane version
  <= origin/main at land; any `--accept` or `--admin` in built argv; a relaunch re-reserving a
  reserved round (idempotency); two lanes sharing one worktree; overlapping Touch lists.
- Must-allow: N approved independent tickets in N worktrees each pass the scope guard inside their
  own Touch; a CLEAN round lands in version order; a crash mid-wave leaves every ledger readable and
  `status` names what each lane was doing.
- Sabotage: a lane starting on a `direction` ticket; the land chain made parallel; `unknown-role`
  promoted to writer - each turns a named test red.
- Gaps the spec must close: `hooks.json` registers `Stop` only (`:57-63`) and verify-gate /
  completion-audit read the main checkout, so lane worktrees are unaudited unless `/crew:done
  --root` runs in each; role-write-guard allows an unknown agent type (`role_write_guard.py:54-57`).
- Already happened, as a one-off under delegated authority: the `crew-land-lanes` run had a subagent
  run `review_ledger.py --accept --by "Matthew Badali (delegated...)"` and `gh pr merge --admin`.
  Shipped as a feature, that is the gate failing open with a receipt that looks human.
- Not verified by the review: whether PreToolUse hooks fire inside workflow subagents;
  cross-session workflow resume; any test suite; `drift-detection.sh`.

## Open questions
- Owner asked for several subagents in the flow, with questions and approvals (when auto-approve
  is off) reaching the owner. A lane subagent cannot prompt the owner and cannot record an approval
  (`approval_hook.py` is UserPromptSubmit-only), so a lane must stop, write its question or approval
  request, and the main session must batch them to the owner between waves. Where do lane questions
  live (T-0010's `questions.md`?), and can other lanes keep running while one waits?
- Entry point: the owner suggested the subcommand `/crew:autopilot workflow`. That makes this
  depend on T-0018's subcommand router (`workflow` joins its `AVAILABLE`), like T-0012's `goal`.
- Is the approval one batch approval over all the tickets designed in the session (T-0024's group
  approval), or one per ticket?
- Which decisions the autonomous run may take alone, per T-0010 policy, and which always stop.
- Lane mechanism: Workflow tool, `Agent` with worktree isolation, or both?
- Maximum concurrent lanes (the repo already caps dispatches with `pm.maxDispatches=9`).
- Does this depend on T-0012 (backlog picker) or does it stand alone over approved INDEX tickets?
- How do the scope guard and role-write-guard treat several writers in separate worktrees?
- Resuming after /clear or a crash: a workflow resumes only within the session that started it.

## Note added 2026-09-27 (owner request, T-0073/T-0074)
The owner asked for an opt-in option to never be asked for review accept/reject ("I'd like an option to have these gone entirely"), tracked as T-0073 and T-0074. The "never, whatever the config" rule above therefore becomes "never, unless `autopilot.reviewAcceptance` opts in, and then only through the one dedicated policy command". The scope_guard rule this ticket adds must keep refusing a subagent's hand-run `review_ledger.py --accept|--reject`, but must allow that policy command. Whichever of T-0029 and T-0073 lands second carries the carve-out; T-0073's spec owns the design.

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

Kept in T-0029: plan Steps 1-6 and 8-10 for the wave itself: settings and the set file, `crew_wave.py plan`, `start`/`lane-init`, `lane-prompt`/`lane-done`, `collect`, the router and command file.

Moved:
- L-0544: plan Step 7, scope guard never-list for subagents and review_ledger `allow_abbrev=False`.
- L-0545: plan Step 11, `crew_wave.py cleanup` of merged lanes' worktrees.

Both moved parts are ALREADY BUILT on branch T-0029-wave (head 574985ce: crew_wave.py `cleanup` :943; review_ledger.py:469-470; test_scope_guard_wave.py). Splitting means taking them out of the branch and a replan; the owner may prefer to finish T-0029 as is and close L-0544/L-0545 as folded back.

spec.md and plan.md are APPROVED and were not edited. Before implement, they need a successor amendment narrowed to the kept scope, and a re-approval.

## Split reverted 2026-09-30
Owner: "Fold back, finish T-0029 whole". L-0544 and L-0545 are closed as folded back; T-0029 keeps its full approved scope and plan.
