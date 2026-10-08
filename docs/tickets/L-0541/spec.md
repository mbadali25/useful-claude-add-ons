# L-0541: autopilot goals: mint the approved split, drive the tickets in dependency order (`mode: backlog`), per-ticket approval, run caps, `--goal` resume          status: spec   risk: high
Split from T-0012 (2026-09-30). Written against origin/main `5c40ffa7` and T-0012-build `ab1bb915`.
**Not buildable until T-0012 (PR #354) has merged**; re-find every line by content then. T-0012's branch is
cut from `d67098ad`, about 1000 lines of `crew_autopilot.py` behind main, so its anchors move on merge.

## Intent
Once a goal's split proposal is approved (T-0012's `split_approved`), autopilot mints each proposed ticket with
`crew_ticket.mint` in list order, records each id in the goal file as it returns, and then works the tickets one
at a time in dependency order. `autopilot.mode: backlog` arms autopilot exactly as `plan` does and, after a ticket
closes, continues to the next one; `plan` stops after one ticket. Each ticket reaches its own approve phase, where
T-0010's `approve --ticket <id>` applies the configured policy to that one ticket; a refusal stops the run with
that ticket's `/crew:approve <id>` line and the `resume: /crew:autopilot --goal <slug>` line. Two caps bound a
run: `autopilot.maxTicketsPerRun` (default 3, counted in the goal file's `runs`) and
`autopilot.maxTokensPerSession` (default 2,000,000, input + output summed from this session's transcript);
an unreadable count stops. `resume_target` accepts `--goal <slug>` (argument or handoff line) and resumes at
`next_goal_ticket`, replacing T-0012's "arrives with L-0541" stops. Review acceptance and production deploys
still always stop for the owner.

## Exclusions
- No change to `crew_ticket.mint`'s signature or behaviour (T-0012 Exclusions). Risk is carried in each minted
  ticket's direction body (`risk: <low|medium|high>` line) and in the goal file's `tickets[].risk`.
- No change to `approval_policy`, `question_policy` or `approve` beyond `settings` arming on `backlog`. No
  backlog-only approval path. No group approval: never a `/crew:approve` line naming more than one id, a range or
  `--confirm`; never runs `crew_ticket.py approve`, `/crew:approve` or `review_ledger.py`.
- No parallel tickets, no worktree lanes (T-0029's `maxLanes` stays COMING).
- No starting an unapproved ticket: every minted ticket goes through spec, plan and its own approval.
- No change to T-0012's proposal, split approval, goal-file schema keys or `/goal` line, except filling `tickets[].id`
  and appending to `runs`.
- No change to how a handoff is written (T-0056), validated against the goal file (L-0658) or discovered with no
  argument (L-0659). This ticket only makes `--goal <slug>` resolvable.
- No change to mint's id prefix (`T-####`); the repo's L-/C- numbering is out of scope.
- No edit to `plugin/crew/tests/sabotage*.py` (harness path, T-0087): sabotage entries are a follow-up tooling-only ticket.
- No change to `crew_metrics.transcript_tokens`'s default fields or its existing callers.

## Evidence
origin/main `5c40ffa7` unless marked T12 (T-0012-build `ab1bb915`, branch-only):
- `crew_ticket.mint(root, title, status="ready", direction=None)` `plugin/crew/hooks/scripts/crew_ticket.py:1371`:
  exclusive `os.mkdir` of `.work/tickets/T-NNNN`, optional `direction.md`, INDEX row through `crew_tracker.create`
  (+`move` for `ready`) under the INDEX lock; returns `{ticket, folder, status, warnings}`; raises `TicketError`
  (status outside `ready`/`direction` `:1048`, bad title, non-text direction, gate/lock/tracker failure, attempts
  exhausted). No `risk` parameter.
- `settings` `plugin/crew/hooks/scripts/crew_autopilot.py:1611`, `_settings_at` `:1658`: arms only on
  `mode == "plan"` `:1665`; any other value but `off` warns "autopilot.mode is {mode!r}: only the exact string
  'plan' arms autopilot, so it reads as off". T12: `:781`, `:810`, `:817`.
- `approval_policy` `crew_autopilot.py:2175`; `approve` `:2299` (args `--root`, `--ticket`, `--json` `:3263-3276`;
  exit 0 self-approved, 2 unarmed or refused, 3 NEEDS_REPLAN continuation refused, 1 crash via `_policy_main`
  `:3164`); success line `self-approved {ticket} under approval={policy}, risk={risk|unknown (high)}{sleep}` `:2321`.
- `AUTOPILOT_DEFAULTS` `plugin/crew/hooks/scripts/crew_state.py:1133` (mode, maxPhases, deploy, approval, questions,
  maxAutoReplans, sleep, ship, knownFailures, ciTimeoutMinutes). T12 `:1129` has only the first five.
- The three keys exist only as `COMING` rows: `plugin/crew/hooks/scripts/crew_keys.py:524-530`
  (`maxTicketsPerRun` "3", `maxTokensPerSession` "2000000", `mode` values `off`/`plan`/`backlog`), all naming
  T-0012. Not in `plugin/crew/templates/config.template.json`, `plugin/crew/CONFIG.md` or `crew_config.py`.
  `crew_keys.py:629-631` lists COMING `new key` rows the code already declares, so landing a key means moving its row.
- `resume_target` `crew_autopilot.py:1492`; handoff stop "goal resume arrives with T-0012" `:1470-1471`;
  `route` stops `--goal` with `run --goal <slug> arrives with {ARRIVES['goal']}` `:2489-2492`, `ARRIVES` `:360`.
  T12: `GOAL_RESUME_ARRIVES = "L-0541"` `:1321`, used `:669`, `:1842`, `:2032`; `MINT_PENDING` stub `:1327`,
  printed `:1780`.
- T12 goal file: `write_goal` `:1512`, `goal_path` `:1352` (`.work/autopilot/<slug>.json`); schema 1 keys
  `schema, goal, slug, proposal, tickets[{title,risk,depends_on,id:None}], approval:None, caps:None, runs:[]`
  `:1528`; `split_approved` `:1740`; owner receipt `<git-common-dir>/crew/goals/<slug>/approval.json` `:1360`;
  self-approval noted as `approval:{via,proposal_sha256}` `:1769`. Tests: `plugin/crew/tests/test_crew_autopilot_goals.py`.
- Goal slug grammar is T-0006's `_GOAL_SLUG_RE` in `plugin/crew/hooks/scripts/crew_resume.py` (`[a-z0-9][a-z0-9-]{0,63}`).
- Token source: `crew_metrics.transcript_tokens` `plugin/crew/hooks/scripts/crew_metrics.py:436` sums four usage
  fields (input, output, cache_read_input, cache_creation_input) and returns UNKNOWN on any unparseable line.
- Pinned text that moves: "arrives with T-0012" in `plugin/crew/tests/test_crew_autopilot_status.py:180`, `:189`,
  `:454` and `plugin/crew/README.md:871`.
- Leaf counts: `plugin/crew/tests/test_crew_config.py:323-331` (+ count comments after) and `:3231-3250` (CONFIG.md
  section count). Two new keys move both.
- Design intent: "`autopilot: backlog` - `plan` plus: picks the next APPROVED ticket ... never starts an
  unapproved ticket; per-session caps on tickets and tokens" (`TODO.md`, search "autopilot: backlog").
- Owner decisions carried from T-0012's spec Unknowns: "Follow the policy" (2026-09-26): goal-minted tickets are
  approved under `autopilot.approval` like any other; `backlog` arms T-0010's `settings` (recommended there, taken here).

## Unknowns
- **Token fields** (direction default): input + output only, via a new `fields=` keyword on `transcript_tokens`
  whose default stays the four fields. Owner may overturn to all four.
- **Which transcript**: the session transcript path the hook/command already has (`transcript_path`), resolved the
  way `crew_context.py:858` does. If no path is known, the token cap reads as unknown and stops.
- **Pointer for the next ticket**: how the active-ticket pointer moves to the picked ticket (the existing
  active-ticket mismatch stop must not fire for a goal-picked ticket). Resolved at plan from T-0012's merged code.
- **`runs` record shape**: one entry per run `{started, session, tickets:[ids], stop}`; the ticket cap counts ids in
  the current run's entry. Final shape decided at plan, coordinated with T-0056 (which adds run state to the goal file).
- **"Stopped" dependency**: a dependency whose status is `cancelled`, `superseded` or `needs-owner` (crew-known
  INDEX statuses) stops the picker naming it; `done` counts as closed. Mapping confirmed at plan.
- Next free crew patch version set at implement time (main is at 1.0.352 on `5c40ffa7`).

## Size and split
About 220 added production lines (mostly `crew_autopilot.py`, ~15 in `crew_metrics.py`, ~10 in `crew_state.py`,
key rows in `crew_keys.py`), and ~15 tests. Four fail-closed steps (mint failure, stopped dependency, cap,
unreadable transcript). No harness path. Further split rejected in direction.md (Option 2).

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_keys.py`
- `plugin/crew/hooks/scripts/crew_config.py` (only if key validation lives there after T-0012 merges)
- `plugin/crew/hooks/scripts/crew_metrics.py`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_goals.py`
- `plugin/crew/tests/test_crew_autopilot_policy.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/test_crew_metrics.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `docs/guides/crew/src/auto-cycle.md`
- `docs/guides/crew/src/configuration-reference.md` (autopilot key table, `:378-379`; and `config_reference.py` if the table is generated)
- `docs/guides/crew/src/guide.md` (`:247` "off until `autopilot.mode` is exactly `plan`")
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `.crew/codemap/crew.md`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `docs/tickets/L-0541/` (removed in the final PR)

Not in Touch: `crew_ticket.py` (mint unchanged); `crew_resume.py` (grammar already accepts `--goal`);
`approval_hook.py` (no new token shape); `plugin/crew/tests/sabotage*.py` (follow-up tooling ticket);
`docs/diagrams/` (no new box: the goal loop sits inside autopilot's existing box; say so in the PR if unchanged).

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
`G` is `plugin/crew/tests/test_crew_autopilot_goals.py`; run as `python3 plugin/crew/tests/pytest_rule.py G -q -k <name>`.
- [ ] After `split_approved`, each proposed ticket is minted in list order with status `ready` and a direction.md
  naming the goal file, its place in the list and its risk; each id is written to `tickets[].id` as it returns.
  `-k "test_mint_after_split_approval or test_minted_ticket_status_ready"`
- [ ] A `TicketError` on ticket 2 of 3 stops the run; the stop names ticket 1's id as minted and tickets 2-3 as
  unminted; the goal file keeps ticket 1's id; re-running does not mint ticket 1 twice. `-k test_mint_failure_midway_names_minted_and_unminted`
- [ ] `settings` arms on exactly `plan` or `backlog` and reports which in `mode`; `Backlog`, `backlog `, `auto` and
  any other value read as off with the existing warning. `-k "test_backlog_arms_like_plan or test_mode_typo_still_reads_off"`
- [ ] `backlog` grants nothing `plan` does not: every refusal case in `test_crew_autopilot_policy.py` refuses
  identically under both modes (parametrised). `-k test_backlog_grants_nothing_plan_does_not`
- [ ] `next_goal_ticket(root, slug)` returns the first ticket in list order not closed whose every `depends_on` is
  closed; all closed -> goal done; a dependency in a stopped status -> stop naming it.
  `-k "test_backlog_respects_dependencies or test_stopped_dependency_blocks"`
- [ ] At a minted ticket's approve phase, `approve --ticket <id>` runs for that one ticket: exit 0 prints its
  `self-approved` line and continues; any other exit stops with exactly `/crew:approve <id>` and then
  `resume: /crew:autopilot --goal <slug>`; no output names two ids. `-k "test_minted_ticket_self_approved_one_at_a_time or test_minted_ticket_refusal_stops_with_one_id"`
- [ ] `mode: plan` stops after one ticket closes; `mode: backlog` continues to `next_goal_ticket`. `-k test_plan_mode_stops_after_one`
- [ ] Ticket cap: the 4th ticket in one run (default 3) stops, naming the cap and the resume line. Token cap:
  input + output over 2,000,000 stops; cache-read tokens alone do not count; an unparseable transcript or no
  transcript path stops as "could not tell". `-k "test_ticket_cap_stops or test_token_cap_stops or test_unreadable_transcript_stops"`
- [ ] `transcript_tokens(..., fields=("input_tokens","output_tokens"))` sums only those; the default call is
  unchanged. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_metrics.py -q -k transcript_tokens`
- [ ] `resume_target` with `--goal <slug>` as argument or handoff line returns `next_goal_ticket`'s ticket; an
  unknown slug or unreadable goal file stops naming the file. No "arrives with L-0541"/"arrives with T-0012" text
  remains in code, tests or docs (`grep -rn "arrives with L-0541\|goal resume arrives with T-0012" plugin/` is empty).
  `-k "test_goal_resume_from_handoff or test_goal_resume_from_argument"`
- [ ] Keys: `autopilot.maxTicketsPerRun` and `autopilot.maxTokensPerSession` in `AUTOPILOT_DEFAULTS`,
  `config.template.json` and CONFIG.md; their COMING rows and the `mode` COMING row removed from `crew_keys.py`;
  leaf counts re-measured. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_config.py -q`
- [ ] Existing suites pass:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path touched).
- [ ] Docs: README, CONFIG.md, the guide sources and `.crew/codemap/crew.md` describe backlog mode, the caps, the
  picker order and the `--goal` resume; guides rebuilt (`python3 docs/guides/crew/src/build.py`); crew bumped to
  the next free patch with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0012 (PR #354, draft, not merged): goal file, proposal, `split_approved`, `MINT_PENDING` / `GOAL_RESUME_ARRIVES`
  stubs this ticket replaces. **Must merge first.**
- T-0019 (`crew_ticket.mint`), T-0010 (`settings`, `approve`), T-0006 (resume grammar): on main.
- Blocks: T-0056 (PR #459), L-0658 (#463), L-0659 (#469), L-0660 (#472).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
