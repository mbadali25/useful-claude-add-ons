# L-0541 direction - autopilot goals: mint the approved split, drive the tickets in dependency order (mode backlog), per-ticket approval, run caps, --goal resume

Status: approved 2026-10-05 for cloud hand-off (orchestrator, owner's standing self-approve authority). The seed text below is kept verbatim; the brainstorm sections follow it.

Split from T-0012 (owner 2026-09-30 "Triage pass now"). Owner decision 2026-09-30 ~11:30: work the oldest tickets first; a ticket with more than 1-2 separate deliverables has the extra ones split out so each ticket is a small PR.

## Original text (verbatim, from T-0012 spec.md ## Intent (second paragraph; this ticket takes the part from "After the split approval" on) and plan.md Step 3)

> The split proposal is approved under `autopilot.approval`, with the goal's risk being the highest proposed ticket risk (unknown reads `high`). `self` approves. `risk` approves only when every proposed ticket is `risk: low`. `human` stops, naming `/crew:approve goal:<slug>` for the owner to type. Nothing approves it without `scope.allowCliApproval: true` and an armed autopilot. After the split approval, autopilot mints each ticket with T-0019's `crew_ticket.mint` (status `ready`, with a direction.md that points at the goal file). It then works the tickets one at a time in dependency order (`autopilot.mode: backlog`), within per-run caps. Each ticket reaches its own approve phase, where T-0010's `crew_autopilot.py approve --ticket <id>` applies the same policy to that one ticket. A refusal stops the run with that ticket's `/crew:approve <id>` line. Review acceptance and production deploys always stop for the owner. Goal state lives in `.work/autopilot/<slug>.json`. `resume: /crew:autopilot --goal <slug>` (T-0006's grammar) picks a run back up after `/clear`. T-0013 types it where the terminal can be identified; otherwise T-0006 names it for the human to accept (no `initialUserMessage`: T-0006's spike failed interactively).
>
> ### Step 3: mint on approval, backlog arming, order, per-ticket approval, caps, `--goal` resume
> Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/config.template.json, plugin/crew/tests/test_crew_autopilot_goals.py, plugin/crew/tests/test_crew_config.py
> Where: T-0019's `crew_ticket.mint`; T-0010's `settings` `crew_autopilot.py:653-686` and `approve` `:812-831` (abd4f29b, branch-only); `AUTOPILOT_DEFAULTS` `crew_state.py:1091` (abd4f29b); `resume_target`'s goal stop; `leaf_paths` checks `test_crew_config.py:106`, `:246`
> Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_goals.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_autopilot_policy.py -q
> Risk: high. The picker decides what runs next unattended, and arming `backlog` widens where T-0010's `approve` can run.
> - [ ] after `split_approved`: for each ticket in order, `crew_ticket.mint(top, title, risk, status="ready", direction=<a body naming the goal file and this ticket's place in it>)`, recording each id in the goal file as it returns. A raise stops the run, naming the minted and unminted tickets
> - [ ] `settings` (T-0010's): `armed` is true for exactly `plan` or `backlog`, and `mode` reports which. Every other value still reads as off with its warning. Nothing else in `settings`, `approval_policy` or `approve` changes
> - [ ] `next_goal_ticket(root, slug)`: the first ticket (in list order) not `closed` whose every `depends_on` is `closed`; a dependency that stopped -> stop naming it; all closed -> goal done
> - [ ] per-ticket approval: at a ticket's approve phase, run T-0010's `crew_autopilot.py approve --root . --ticket <id>` for that one ticket. Exit 0 -> report the `self-approved` line and continue. Any other exit -> stop the run with exactly `/crew:approve <id>` for that ticket, then the `resume: /crew:autopilot --goal <slug>` line. Never a group line
> - [ ] `mode: backlog` continues to `next_goal_ticket` after `closed`; `mode: plan` stops after one ticket
> - [ ] caps: `maxTicketsPerRun` (default 3, counted in the goal file's `runs`), `maxTokensPerSession` (default 2,000,000, summed from the session transcript's `message.usage` input+output); unreadable -> stop
> - [ ] `resume_target`: `--goal <slug>` (argument or handoff line) -> `next_goal_ticket`, replacing the "arrives with T-0012" stop
> - [ ] tests: `test_mint_after_split_approval`, `test_mint_failure_midway_names_minted_and_unminted`, `test_minted_ticket_status_ready`, `test_backlog_arms_like_plan`, `test_backlog_grants_nothing_plan_does_not` (parametrised over T-0010's refusal fixtures), `test_mode_typo_still_reads_off`, `test_backlog_respects_dependencies`, `test_stopped_dependency_blocks`, `test_minted_ticket_self_approved_one_at_a_time`, `test_minted_ticket_refusal_stops_with_one_id`, `test_plan_mode_stops_after_one`, `test_ticket_cap_stops`, `test_token_cap_stops`, `test_unreadable_transcript_stops`, `test_goal_resume_from_handoff`; leaf count re-measured

## Dependencies

- T-0012 (goal file, proposal and split approval: this ticket consumes `split_approved`)
- T-0019 (`crew_ticket.mint`), T-0010 (`settings`, `approve`), T-0006 (resume grammar)

## Evidence carried over

- T-0012 spec.md ## Evidence and ## Unknowns cover this part too; carry the relevant lines into this spec
- Anchors in the quoted Step 3 (`crew_autopilot.py:653-686`, `:812-831`, `crew_state.py:1091`) are at abd4f29b, branch-only


## Ask
Owner, 2026-09-30 (triage split of T-0012): after a goal's split proposal is approved, autopilot mints the
proposed tickets and works them one at a time in dependency order, each through its own approval, inside
per-run caps, resumable with `/crew:autopilot --goal <slug>` after `/clear`.

## What brainstorm found (origin/main `5c40ffa7`, T-0012-build `ab1bb915`)
- `crew_ticket.mint(root, title, status="ready", direction=None)` is on main (`plugin/crew/hooks/scripts/crew_ticket.py:1371`).
  It has **no `risk` parameter**; the seed's `mint(top, title, risk, ...)` call does not exist.
- T-0012 is not merged (PR #354, draft). Its branch is cut from `d67098ad`, far behind main: its
  `crew_autopilot.py` is 2307 lines against main's 3311. It prints a `MINT_PENDING` stub where this ticket mints,
  and names `GOAL_RESUME_ARRIVES = "L-0541"` where this ticket resumes.
- `backlog`, `maxTicketsPerRun` (3) and `maxTokensPerSession` (2000000) already exist only as `COMING` rows in
  `plugin/crew/hooks/scripts/crew_keys.py:524-530`.
- `crew_metrics.transcript_tokens` (`plugin/crew/hooks/scripts/crew_metrics.py:436`) already sums `message.usage`,
  but over four fields, cache reads included. The seed says input + output.

## Options
1. **One ticket, built on T-0012's branch after it merges (recommended).** Mint, `backlog` arming, the picker,
   per-ticket approval, caps and `--goal` resume land together, because each is only reachable through the others:
   a picker with nothing minted has nothing to pick, and `backlog` armed without the caps runs unbounded.
   Risk goes into each minted ticket's direction body and stays in the goal file's `tickets[].risk`, so `mint`
   is unchanged (T-0012 Exclusions: "No change to `crew_ticket.mint`").
2. Split further: (a) mint + picker + per-ticket approval in `plan` mode, (b) `backlog` + caps, (c) `--goal` resume.
   Smaller PRs, but (a) alone ships a goal that never advances past ticket 1 without a human, and (b) arms
   unattended running in a PR whose resume path does not exist yet. Three review rounds for one picker.
3. Add a `risk` parameter to `mint`. Breaks T-0012's exclusion and T-0019's contract for one caller; the
   goal file already holds the risk.

## Recommendation
Option 1. Token cap counts **input + output only**, as the seed says, through a `fields` keyword on
`crew_metrics.transcript_tokens` whose default stays the four fields (no change for existing callers). Counting
cache reads would trip a 2M cap within a few long turns and stop every real run.

## Open questions (default taken; the owner can overturn in the PR)
- Token fields: input + output (default) vs. all four. Default taken for the reason above.
- Minted ids: `mint` picks the next free `T-####` on main. This repo mints `L-` / `C-` ids by hand
  (two-box numbering). Default: use whatever `mint` returns; changing mint's prefix is a separate ticket.
- Sabotage entries for the picker, cap and per-ticket approval are harness paths, so they cannot ride in this
  PR (T-0087). Default: a follow-up tooling-only ticket, filed when this lands, like L-0660 for T-0056.
