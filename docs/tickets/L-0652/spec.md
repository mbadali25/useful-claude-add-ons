# L-0652 manual /crew:autopilot sleep and wake          status: spec   risk: high
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`. T-0053 must be merged first;
re-read its code and the line numbers below before planning.

## Intent
The owner can type `/crew:autopilot sleep` to enter sleep mode now and `/crew:autopilot wake` to
leave it now. The manual state beats the schedule until the next window edge, records who set it
and when, and expires by itself. A state that cannot be read is treated as not set.

## Design
- State file: `<git-common-dir>/crew/autopilot-sleep.json`, one object
  `{"state": "asleep"|"awake", "by": <text>, "at": <ISO local time>, "until": <ISO local time>}`.
  Written to a temp file and moved into place with `os.replace`.
- `until`:
  - `sleep` with a valid schedule: the end of the current window if inside one, else the end of
    the next window;
  - `sleep` with no schedule: `at` plus 12 hours (`MANUAL_SLEEP_HOURS = 12`);
  - `wake`: the end of the current window if inside one; otherwise the file is removed, since the
    schedule already says awake.
- `crew_sleep.resolve` gains the manual state as an input. Order: a valid, unexpired manual state
  wins; otherwise the schedule decides as in T-0053. The result names its `source`
  (`manual` or `schedule`).
- A manual state is valid only when the file parses as an object, `state` is one of the two
  words, `at` and `until` parse, `at` is not after now, and `until` is after now and at most 24
  hours after `at`. Anything else: ignored, with a warning that names the file and the reason.
- CLI: `crew_autopilot.py sleep --root . [--by <text>]` and `crew_autopilot.py wake --root .`.
  - `sleep` exits 2 with `refused: ...` when `scope.allowCliApproval` is not exactly `true`, when
    autopilot is not armed, when the config is could-not-tell, or when no `autopilot.sleep.*`
    override is configured.
  - `wake` never refuses for policy reasons. With nothing to undo it prints `already awake`.
  - Each prints one line: `asleep until <HH:MM> (set by <by>); /crew:autopilot wake undoes it`, or
    `awake; the schedule resumes at <HH:MM>`.
- Router: `sleep` and `wake` join `SUBCOMMANDS` and `AVAILABLE`. `route_args` refuses a second
  word after either.
- `autopilot.md`: the argument hint and section 0 name the two subcommands and the two CLI calls,
  inside the 110-line budget.
- `settings`' `sleep=` line gains `source=<manual|schedule>` and, for manual, `until=`.

## Exclusions
- No plain-text phrases ("going to bed"): that is T-0057.
- No log entry and no morning summary on `wake` (L-0653 adds both).
- No `deploy` change (L-0654).
- No edit to a harness path. `scope_guard.py` is not taught the new commands: with
  `scope.allowCliApproval` not `true` the CLI itself refuses, and with it `true` the session can
  already approve by CLI.
- No sabotage mutations (L-0655).
- The state file is never read from the worktree or from `.work/`.

## Evidence
Read at origin/main `155fe6d8`; lines inside `crew_sleep.py` are T-0053's and are re-read at plan.
- plugin/crew/hooks/scripts/crew_autopilot.py:224-226 `SUBCOMMANDS`, `AVAILABLE`, `ARRIVES`;
  :1299-1320 `route`; :1328-1346 `route_args`; :1662-1672 the subparser loop in `main`;
  :1602-1616 `_policy_main` (exit 0 only on a yes; a crash is a refusal).
- crew_autopilot.py:1129-1151 `approve`, the existing writer, and its "armed" refusal at :1139.
- plugin/crew/hooks/scripts/crew_ticket.py:654-660 `cli_approval_allowed`.
- plugin/crew/tests/test_crew_autopilot_policy.py:682
  `test_approve_is_the_only_writing_subcommand`; :761-768 the tests that pin every statement of
  the write exception.
- plugin/crew/README.md:859 and plugin/crew/commands/autopilot.md's first paragraph state the
  one-writer rule; plugin/PLUGINS.md:130 says "its one write".
- plugin/crew/commands/autopilot.md: 109 lines on main;
  plugin/crew/tests/test_lifecycle_commands.py:112 `AUTOPILOT_MAX_LINES = 110`; :105-111 says
  detail past the budget moves into `crew_autopilot.py` output.
- scripts/check-tooling-pr.py:89-95: `crew_autopilot.py` and `autopilot.md` are `SEAM`, not
  `HARNESS`; with no harness path changed the check exits 0 (:34).

## Unknowns
- Whether the wording fits in 110 lines. Resolved at implement by rewording section 0's sentence
  about subcommands that "arrive with" later tickets. If it cannot fit, stop and ask: raising the
  budget is the owner's call.
- T-0019 / L-0611, T-0012 and T-0020 also add to `AVAILABLE` and to `autopilot.md`. Resolved by
  merging main before review; conflicts there are mechanical.
- Clock moved backwards between `sleep` and a read (`at` after now): the state is ignored. Accepted.

## Touch
- plugin/crew/hooks/scripts/crew_sleep.py
- plugin/crew/hooks/scripts/crew_autopilot.py
- plugin/crew/commands/autopilot.md
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_autopilot_policy.py
- plugin/crew/tests/test_crew_autopilot_status.py
- plugin/crew/tests/test_lifecycle_commands.py
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- plugin/PLUGINS.md
- docs/guides/crew/src/daily-workflow-scope.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - rebuilt outputs
- .crew/codemap/crew.md
- .crew/verify.json
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

## Acceptance checks
New tests go in `plugin/crew/tests/test_crew_autopilot_sleep.py`; the verify rule is
`.crew/verify.json`'s autopilot policy rule.
- [ ] Must-allow: `sleep` at 20:00 with schedule `22:00-07:00` and `sleep.approval: self`: the
  next `approval_policy` call allows a `risk: high` plan, and `until` is 07:00 the next day.
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_manual_sleep_before_the_window`
- [ ] Must-allow: `wake` at 23:00 inside the window: the day values apply until 07:00, then the
  schedule decides again. `-k test_manual_wake_inside_the_window`
- [ ] Must-allow: `sleep` with no schedule: asleep for 12 hours, awake at 12 hours and one minute.
  `-k test_manual_sleep_without_a_schedule_expires`
- [ ] Must-block, one test each. `sleep` exits 2 and writes nothing when:
  - `scope.allowCliApproval` is absent, `false`, `"true"` or `1`;
  - autopilot is not armed;
  - `.crew/config.json` is unreadable;
  - no `autopilot.sleep.*` override is set.
- [ ] Must-block, one test each. The state file is ignored, with a warning, when it is: not JSON;
  a list; missing `until`; `state: "on"`; `until` in the past; `until` 25 hours after `at`; `at`
  in the future; `at` not a time.
- [ ] `wake` with no state file and the schedule awake prints `already awake`, exits 0 and writes
  nothing.
- [ ] Only-writer test extended: `sleep` and `wake` write exactly
  `<git-common-dir>/crew/autopilot-sleep.json` and nothing in the worktree; every other
  subcommand stays byte-identical. `python3 -m pytest plugin/crew/tests/test_crew_autopilot_policy.py -q -k only_writing`
- [ ] Router: `route --args sleep` and `route --args wake` print `sub=sleep stop=0` and
  `sub=wake stop=0`; `sleep T-0001` and `wake now` stop.
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_status.py -q -k route`
- [ ] `autopilot.md` is at most 110 lines and names both exact CLI calls:
  `python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] Linked worktree: a `sleep` in the main checkout is read by a lane worktree of the same repo.
  `-k test_manual_state_is_shared_by_worktrees`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; no `HARNESS` path in the diff.
- [ ] Docs: README.md:859, `autopilot.md`'s first paragraph and PLUGINS.md:130 state the writers
  as `approve`, `sleep` and `wake` and name the one file the last two write; CONFIG.md section 20
  describes the manual state and its expiry; guide outputs rebuilt
  (`python3 docs/guides/crew/src/build.py`). Crew bumped with a CHANGELOG entry;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0053 (ready; slice 1): must be merged first.
- T-0018 (merged): the router this extends.
- T-0010 (merged): `scope.allowCliApproval` gating.
Coordinates with T-0019 / L-0611, T-0012, T-0020 (same router and command file).
Blocks: T-0057 (plain-text `sleep` / `wake`), L-0653 (summary on `wake`), L-0655.

## Size
About 160 added production lines (`crew_sleep.py` about 95, `crew_autopilot.py` about 65). One
fail-closed state machine (the manual state), no new parser beyond two `datetime.fromisoformat`
calls.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
