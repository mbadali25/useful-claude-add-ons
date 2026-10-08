# L-0659: bare `/crew:autopilot` finds a running goal when there is no usable handoff          status: spec   risk: high
Split from T-0056 (2026-10-04). Written against origin/main `155fe6d8`. Not buildable until T-0056 and
L-0541 have merged; re-find every line by content then.

## Intent
When `/crew:autopilot` is run with no argument and no usable handoff, it reads this checkout's goal files
before falling back to the active ticket. Exactly one running goal is resumed at its next ticket. Several
running goals stop and list them. A goal file that cannot be read stops as "could not tell", never as "no
goal". A stopped goal is named with its stop reason and its resume command, and is not resumed. This is the
crash case: a session that died without writing a handoff no longer loses the goal.

## Exclusions
- No change when an argument is given (`<ticket>`, `--goal <slug>`), and no change to a usable handoff: both
  keep their place in the order.
- No change to how a handoff is validated (L-0658) or written (T-0056).
- No resuming past a human stop: `stopped` is reported, never continued.
- No new pointer file, no config key, no hook.
- The active-ticket mismatch stop (`crew_autopilot.py:710-719`) is unchanged for a ticket chosen any other way.
  How a goal sets the pointer for its next ticket is L-0541's.
- In-flight markers (T-0049, L-0589) and sleep mode (T-0053) are not re-implemented: the resumed goal goes
  through the same `next` checks as any run, so it re-checks them before its first phase.
- No edit to `plugin/crew/tests/sabotage*.py` (L-0660).

## Evidence
origin/main `155fe6d8`:
- The order is documented at `plugin/crew/hooks/scripts/crew_autopilot.py:104-112` and implemented in
  `resume_target` `:668-727`: argument `:682-685`, handoff `:686-690`, active pointer `:691-699`, INDEX
  `:700-709`. Fallthrough reasons are collected in `fallthrough` and printed as `fell through:` lines
  (`plugin/crew/commands/autopilot.md:48-52`).
- The INDEX step already has the shape wanted here: several candidates stop and list them `:702-705`.
- Unreadable is not absent: `_read_handoff` `:608-625`; a broken active pointer stops rather than being
  guessed past `:694-697`.
- Status composes `resume_target` (`status` docstring `:1523-1530`) and prints at most `STATUS_MAX_LINES = 12` (`:1355`).
- Docs stating the order: `plugin/crew/commands/autopilot.md:48-52`; `plugin/crew/README.md:913`, `:2159`;
  `.crew/codemap/crew.md:687`.
- From T-0056 (not on main): `running_goals(root)` returning `running`, `stopped`, `done`, `unknown`.
- From L-0541 (not on main): `next_goal_ticket(root, slug)` and `resume_target`'s `--goal` branch.

## Unknowns
- The return shape of `resume_target` for a goal after L-0541 (does it carry `goal`?). Resolved before plan.
- Whether a stopped goal should stop a bare run (direction.md). Default: named and carried past.
- Status's line budget: a `goal:` line must fit inside `STATUS_MAX_LINES`. Resolved at implement by the
  existing status tests; if it does not fit, the goal is folded into the `source` line.
- The next free crew patch version is set at implement time.

## Size and split
About 110 added production lines, all in `crew_autopilot.py`. One fail-closed step (goal discovery in
`resume_target`). No harness path. No further split.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_goal_resume.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/README.md`
- `docs/guides/crew/src/auto-cycle.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- `.crew/codemap/crew.md`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`

Not in Touch: `plugin/crew/CONFIG.md` (no setting); `crew_resume.py` (auto-resume needs a handoff, and
there is none in this case); `.crew/verify.json` (already mapped); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
`T` is `plugin/crew/tests/test_crew_autopilot_goal_resume.py`.
- [ ] No handoff, one running goal: `resume_target(root)` returns the goal's next ticket with source
  `goal-file`, and `fell through:` carries the handoff's reason. `python3 plugin/crew/tests/pytest_rule.py T -q -k test_bare_resume_finds_the_one_running_goal`
- [ ] No handoff, two running goals: stop, the reason lists both slugs and says
  `name one: /crew:autopilot --goal <slug>`. `-k test_two_running_goals_stop_and_list_both`
- [ ] No handoff, an unreadable or malformed goal file (alone, or beside a running goal): stop, the reason
  names the file and says it could not be read. The active ticket is **not** driven. `-k test_unreadable_goal_file_stops_bare_resume`
- [ ] No handoff, a stopped goal only: not resumed; a `fell through:` line names the slug, its recorded
  stop reason and `/crew:autopilot --goal <slug>`; the run continues with today's order.
  `-k test_stopped_goal_is_named_not_resumed`
- [ ] No handoff, only `done` goals or no `.work/autopilot/`: exactly today's behaviour, same output as on
  origin/main for the same fixture. `-k test_no_goal_keeps_todays_order`
- [ ] An argument still wins: `<ticket>` and `--goal <slug>` ignore discovery. A usable ticket handoff
  still wins, and a `disagreement:` line names the running goal. `-k "argument_wins or handoff_wins"`
- [ ] Status shows the running goal and where bare `/crew:autopilot` would go, inside `STATUS_MAX_LINES`,
  read-only (no file written). `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py -q -k goal`
- [ ] The owner's scenario, part (c): goal at ticket 2 of 3, no handoff, a new session's bare
  `/crew:autopilot` resumes the goal at the right phase of ticket 2. Plus the negative: two running goals
  and no handoff stop and list both. `-k "test_goal_resumes_after_a_crash or test_two_running_goals"`
- [ ] `autopilot.md` section 2 states the new order in one sentence and stays inside its line budget.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] Existing suites pass unchanged:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: README, the two guide sources and the code map state the order (argument, handoff, running
  goal, active ticket, INDEX) and the three stop cases. Guide outputs rebuilt
  (`python3 docs/guides/crew/src/build.py`). Crew bumped to the next free patch with a CHANGELOG entry;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0056 (`ready`): `running_goals` and the `run` block. Must land first.
- L-0541 (`direction`): goal resume in `resume_target`, `next_goal_ticket`. Must land first.
- T-0012 (`approved`), T-0004 (`merged`), T-0018 (`merged`, status).
- Independent of L-0658: either order.
- Coordinates with T-0049 (`in-progress`), L-0589 (`direction`), T-0053 (`ready`).
- Blocks: L-0660 (its mutations).

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
