# T-0053 autopilot sleep mode, slice 1: a schedule overlays approval and questions          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; there was no spec.md or plan.md before. Written against origin/main
`155fe6d8` (crew 1.0.322) from direction.md and its "Direction check 2026-10-04".

What this spec narrows, and why:
- **Split.** The whole direction is over the size rule and mixes a harness path
  (`plugin/crew/tests/sabotage*.py`) with feature work. This ticket is the first slice only. The
  rest is in `children/1` to `children/6` (see "Size and split").
- **Shape.** Overrides are direct keys of `autopilot.sleep`, with no `overrides` sub-object, so
  every default is a scalar leaf.
- **Layer.** Repo-only, like the rest of the `autopilot` block. A machine-global layer waits for
  T-0050 / T-0070.
- No plan.md exists. Plan after this spec is approved.

## Intent
A repo can set a nightly window in `.crew/config.json`. Inside it, autopilot uses the window's
values for `approval` and `questions` instead of the day values, so an unattended overnight run
keeps going where the day setting would stop. Every policy read re-resolves the window from the
clock, so a run that crosses the end of the window is back on the day values at its next decision.
Anything that cannot be told (the schedule, an override value, the clock) leaves the day values in
force and says why.

## Design
- Config, all three default `null`:
  - `autopilot.sleep.schedule`: one string `HH:MM-HH:MM`, 24-hour, zero-padded, machine local time.
  - `autopilot.sleep.approval` and `autopilot.sleep.questions`: one of `human|self|risk`, or `null`
    for "not overridden".
- New module `plugin/crew/hooks/scripts/crew_sleep.py`, pure and read-only:
  - `parse_schedule(value)` returns the two minute-of-day numbers or a reason. The grammar is the
    whole string `[0-2][0-9]:[0-5][0-9]-[0-2][0-9]:[0-5][0-9]` with ASCII digits (`[0-9]`, not
    `\d`), hours 00 to 23. Start equal to end is refused: it would be a 24-hour grant.
  - `in_window(start, end, minute)`: start inclusive, end exclusive. Start greater than end
    crosses midnight.
  - `resolve(block, now)` returns `{"state", "schedule", "overrides", "warnings"}`. `state` is
    `off` (no schedule set), `awake`, `asleep` or `unknown`. `now` is a naive local `datetime`;
    the caller passes `datetime.datetime.now()`.
- `crew_autopilot._settings_at` calls `resolve` after it has read the day policies. When the state
  is `asleep`, each valid, non-null override replaces the day value. The result gains
  `"sleep": {"state", "schedule"}` and `"day": {"approval", "questions"}`; `approval` and
  `questions` stay the effective values, so `approval_policy`, `question_policy`,
  `crew_ticket.accepted` and `scope_guard.py` need no change.
- Fail closed, each with a `warning:` line that names the key:
  - a schedule that is not a string or does not match the grammar: state `unknown`, day values;
  - an override that is not `null` and not one of `POLICIES`: that key keeps its day value;
  - `autopilot.sleep` present and not an object: state `unknown`, day values;
  - any other key under `autopilot.sleep` (for example `deploy`, `reviewPolicy`, `notifyHold`):
    "not available in this crew version; it has no effect";
  - `resolve` raising: state `unknown`, day values.
- The existing could-not-tell path is unchanged: an unreadable `.crew/config.json` or a
  non-object `autopilot` block still reads both policies as `unknown` and never looks at sleep.
- Reporting:
  - `crew_autopilot.py settings` prints a third line,
    `sleep=<state> schedule=<value|none> approval=<override|-> questions=<override|->`.
  - While asleep, the `reason` of `approval_policy` and `question_policy` ends with
    ` (asleep <schedule>; day value <day>)`, and `approve` prints that suffix after
    `self-approved <id> under approval=<policy>, risk=<risk>`.
- Everything else `approval_policy` requires still holds asleep: `scope.allowCliApproval` exactly
  `true`, a readable ledger, autopilot armed for `approve`.

## Exclusions
- No manual `/crew:autopilot sleep` or `wake`, and no state file (L-0652).
- No sleep log and no morning summary (L-0653).
- No change to `autopilot.deploy` or `deploy_allowed`: its answer is the same asleep and awake
  (L-0654).
- No review-acceptance change. A CLEAN round and L-0510's 0-BLOCK auto-accept behave as on main.
- No `reviewPolicy` or notify-hold override: those keys do not exist on main (L-0656).
- No edit to any harness path: `crew_ticket.py`, `scope_guard.py`, `review_*.py`,
  `plugin/crew/tests/sabotage*.py` (`scripts/check-tooling-pr.py:58-87`). Sabotage mutations for
  this slice are L-0651.
- No clock override by environment variable or CLI flag. Tests pass `now` to `resolve` or
  monkeypatch `crew_sleep.now` in-process; an override the session could set would be a way to
  grant itself the night values.
- No per-weekday windows, no second window, no time zone setting.
- No machine-global `autopilot.sleep`.
- `status` output does not change: it reads no policy (`crew_autopilot.py:1523-1532`).
- `AUTONOMOUS_STOPS` and every stop in `FIXED_STOPS`, `PROCEDURE_STOPS` and `HUMAN_STOPS` bind
  asleep exactly as awake.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:788 `_settings_at`; :820-822 reads the two policies
  through `_policy_setting`; :823-827 the returned dict. :759-785 `settings`, with the
  could-not-tell return at :776-784.
- crew_autopilot.py:989-992 `POLICIES`, `TAKE`/`STOP`, `ALLOW_CLI`. :995-1003 `_policy_setting`:
  anything outside `POLICIES` reads `human` with a warning.
- crew_autopilot.py:1022-1026 `_decision` calls `settings(top)` on every call. :1034
  `approval_policy`. :1075 `question_policy`. :1129-1151 `approve`; the receipt's `by` at :1146.
- crew_autopilot.py:904 `deploy_allowed`'s `_decide` reads `_settings_at(top)` too, so the overlay
  must leave `deploy` and `deploySaw` untouched.
- crew_autopilot.py:1725-1729 the `settings` CLI prints two lines, then `warning:` lines.
- plugin/crew/hooks/scripts/crew_ticket.py:670-684 `_autopilot_refusal` and :687 `accepted`: an
  `autopilot` receipt stands only while `approval_policy` still allows.
  plugin/crew/hooks/scripts/scope_guard.py:247 asks `approval_policy` before allowing
  `crew_autopilot.py approve`.
- plugin/crew/hooks/scripts/crew_state.py:1134 `AUTOPILOT_DEFAULTS`; :1115 `AUTONOMOUS_STOPS`.
- plugin/crew/hooks/scripts/crew_config.py:389-394: the `autopilot` block is repo-only and is a
  deep copy of `AUTOPILOT_DEFAULTS`.
- plugin/crew/hooks/scripts/crew_config_menu.py:67-80 `_KNOWN_VALUES`; `autopilot.mode` at :80,
  with a `None` choice already used by `context.autoClear.enabled`.
- plugin/crew/templates/config.template.json:215-221 and plugin/crew/skills/crew-setup/SKILL.md:232
  state the `autopilot` block.
- plugin/crew/CONFIG.md:166 ("**130**, so **58** are repo-only"), :789 ("## 11. Repo-only keys —
  58 leaves"), :847-848 the two policy rows, :2591 section 20.
  plugin/crew/tests/test_crew_config.py:328-340 asserts the declared leaves.
- plugin/crew/commands/autopilot.md is 109 lines; plugin/crew/tests/test_lifecycle_commands.py:112
  `AUTOPILOT_MAX_LINES = 110`. Section 2's "Note `maxPhases`, `deploy` ... `approval` and
  `questions`" sentence is where the `sleep=` line is named.
- plugin/crew/README.md:859 ("One writer, by design") and :919 ("Approval and questions
  policies"); plugin/PLUGINS.md:130 the `/crew:autopilot` row and :14 the version cell;
  docs/guides/crew/src/daily-workflow-scope.md:53 and docs/guides/crew/src/troubleshooting.md:248
  state when an `autopilot` receipt stands; .crew/codemap/crew.md:767 quotes the defaults dict.
- .crew/verify.json:360-367: the rule that maps `crew_autopilot.py` and `commands/autopilot.md` to
  `test_crew_autopilot_policy.py`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (`sabotage*.py` at :79, `crew_ticket.py` at :65,
  `scope_guard.py` at :69); :89-95 `SEAM` lists `crew_autopilot.py` and `commands/autopilot.md`. A
  branch that changes no `HARNESS` path exits 0 (docstring, :34), so this slice is an ordinary
  feature PR.
- Nothing on main implements this: `git grep -nIiE "autopilot\.sleep|crew_sleep|sleep-log" origin/main -- plugin scripts docs`
  prints nothing.

## Unknowns
- Morning re-ask. A plan self-approved under the night value reads unapproved once the window
  ends, when the day value would not have approved it (`crew_ticket.py:670-684`). Accepted as the
  designed behaviour and pinned by a test; owner question 1 in direction.md.
- A `taken:` line written asleep makes `questions-check` print `valid=0` by day when the day
  policy says `stop`, as any policy change does on main. The answers already written into the
  ticket stay. Accepted; pinned by a test.
- Daylight-saving changes. The window is compared on wall-clock minutes, so on a change night it is
  an hour longer or shorter. Accepted as risk.
- Exact leaf counts for CONFIG.md (130 and 58 today, three more leaves here). Resolved at
  implement by re-running `leaf_paths(default_config())`, not by arithmetic.
- Whether any test pins the `settings` CLI to exactly two lines. Resolved at implement: run
  `test_crew_autopilot*.py` after adding the third line.
- The next free crew patch version is set at implement time.

## Size and split
- Estimate for this slice: about 175 added production lines. `crew_sleep.py` about 110,
  `crew_autopilot.py` about 50, `crew_state.py` about 8, `crew_config_menu.py` about 5, the
  template 2.
- It holds one parser (`parse_schedule`) and no state machine: `resolve` is a pure function of the
  config block and the clock.
- The rest of the direction, each its own ticket under `children/`:
  1. Tooling-only PR: sabotage mutations for this slice.
  2. Manual `/crew:autopilot sleep` and `wake` (one fail-closed state file).
  3. Sleep log and morning summary.
  4. `deploy` override, `nonprod` only; production always waits while asleep.
  5. Tooling-only PR: sabotage mutations for L-0652 to L-0654.
  6. Overrides for keys that do not exist yet (`reviewPolicy`, held pings). Blocked.

## Touch
- plugin/crew/hooks/scripts/crew_sleep.py
- plugin/crew/hooks/scripts/crew_autopilot.py
- plugin/crew/hooks/scripts/crew_state.py
- plugin/crew/hooks/scripts/crew_config_menu.py
- plugin/crew/templates/config.template.json
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_autopilot_policy.py
- plugin/crew/tests/test_crew_autopilot.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/tests/test_config_menu.py
- `plugin/crew/commands/autopilot.md` - section 2's settings sentence only, at most one line added
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/skills/crew-setup/SKILL.md
- plugin/crew/BUDGETS.md
- plugin/PLUGINS.md
- docs/guides/crew/src/daily-workflow-scope.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- .crew/codemap/crew.md
- .crew/codemap/INDEX.md
- .crew/verify.json
- `docs/diagrams/**` - only if the crew config data-flow diagram gains the sleep overlay
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/tests/sabotage_autopilot.py` (harness; L-0651),
`crew_ticket.py`, `scope_guard.py`, `crew_config.py` (the default is a deep copy of
`AUTOPILOT_DEFAULTS`, so no edit is expected; amend this list first if implement finds one). The
crew, configuration and autopilot guides of T-0048 and T-0054 have not landed, so there is nothing
of theirs to update yet.

## Acceptance checks
Commands run from the repo root; each pytest command goes through the repo's heavy-run wrapper on
a memory-bound host. All new tests are in `plugin/crew/tests/test_crew_autopilot_sleep.py` unless
a file is named. The verify rule is `.crew/verify.json`'s policy rule (`:360-367`), which gains
`crew_sleep.py` and the new test file.
- [ ] Schedule grammar, one parametrised test:
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_parse_schedule`
  - accepted: `22:00-07:00`, `00:00-23:59`, `09:30-17:00`;
  - refused, each with a reason: `7:00-22:00`, `24:00-07:00`, `22:60-07:00`, `22:00-22:00`,
    `22:00 - 07:00`, `22:00-07:00 `, `22:00`, `""`, a list, `true`, `2200`, a string with
    non-ASCII digits.
- [ ] Window edges: `-k test_in_window`. For `22:00-07:00`: 21:59 awake, 22:00 asleep, 23:59
  asleep, 00:00 asleep, 06:59 asleep, 07:00 awake. For `09:00-17:00`: 08:59 awake, 09:00 asleep,
  16:59 asleep, 17:00 awake.
- [ ] Must-allow: day `approval: risk`, `sleep.approval: self`, a `risk: high` spec,
  `scope.allowCliApproval: true`, clock inside the window: `approval_policy` allows and
  `crew_autopilot.py approve` exits 0 and prints the asleep suffix.
  `-k test_asleep_self_approves_a_high_risk_plan`
- [ ] Must-allow: the same for `sleep.questions: self`: `question_policy` answers `take`.
  `-k test_asleep_takes_the_recommendation`
- [ ] Must-block, one test each. Each of these leaves the day value in force, and where a warning
  is named `settings` prints it:
  - the clock is outside the window;
  - `sleep.schedule` is `null` (state `off`, no warning);
  - the schedule is malformed (state `unknown`, warning);
  - `sleep.approval` is `"always"`, `true` or a list (warning; `sleep.questions` still applies);
  - `autopilot.sleep` is a string or a list (state `unknown`, warning);
  - `scope.allowCliApproval` is not exactly `true`: asleep with `sleep.approval: self` still refuses;
  - `.crew/config.json` is unreadable: both policies read `unknown`, as on main;
  - `crew_sleep.resolve` raises (monkeypatched): state `unknown`, day values, warning;
  - an unknown key under `autopilot.sleep` (`deploy`, `reviewPolicy`): "not available in this crew
    version", and no other effect.
- [ ] Re-resolved per decision: one process, the clock moved from 06:59 to 07:00 between two
  `approval_policy` calls, first allows and second refuses.
  `-k test_a_run_that_crosses_the_window_end_returns_to_day_values`
- [ ] Morning re-ask pinned: a receipt written by `approve` asleep makes `crew_ticket.accepted`
  read `approved` inside the window and `unaccepted` after it, with the reason naming
  `autopilot.approval`. `-k test_receipt_written_asleep_stops_standing_after_the_window`
- [ ] `deploy_allowed` returns the same dict asleep and awake for `none`, `nonprod` and `all`.
  `-k test_deploy_allowed_ignores_sleep`
- [ ] A sleep override can lower authority too: day `self`, `sleep.approval: human`, asleep:
  `approve` refuses. `-k test_asleep_human_refuses`
- [ ] `crew_autopilot.py settings` prints the `sleep=` line in each of the four states, and
  `--json` carries `sleep` and `day`. `-k test_settings_cli_prints_the_sleep_line`
- [ ] Read-only: `crew_sleep.py` opens no file for writing, and
  `test_approve_is_the_only_writing_subcommand`
  (`plugin/crew/tests/test_crew_autopilot_policy.py:682`) still passes with a schedule set.
- [ ] Existing suites pass:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py -q`
  with `autopilot.md` still at most 110 lines.
- [ ] Config surface: `test_crew_config.py`'s declared-leaves test names
  `autopilot.sleep.schedule`, `autopilot.sleep.approval` and `autopilot.sleep.questions`; the
  config menu offers `human`, `self`, `risk` and unset for the two overrides.
- [ ] Not a tooling PR: `python3 scripts/check-tooling-pr.py` exits 0 on the branch, and
  `git diff --name-only origin/main...HEAD` lists no `HARNESS` path.
- [ ] Docs, per the repo rule for a `plugin/crew/` change: CONFIG.md has the three rows in section
  11, a "Sleep" paragraph in section 20 and re-measured leaf counts; README.md:919's paragraph and
  the two guide sources say that a receipt written asleep stops standing when the window ends;
  the guide outputs are rebuilt (`python3 docs/guides/crew/src/build.py`); `.crew/codemap/crew.md`
  describes `crew_sleep.py` and the new defaults. Crew is bumped to the next free patch with a
  CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
Must land first:
- T-0010 (merged, PR #261): the two policies this overlays.
- T-0072 (merged, PR #250): `autopilot.deploy` and `deploy_allowed`, which this slice must leave
  unchanged.
- T-0018 (merged): the router and `status`, unchanged here.
- T-0087 (merged): the tooling-PRs-land-alone rule that shapes the split.
- L-0510 (done): review auto-accept, which is why no review override is needed.

Coordinates with, no order forced:
- T-0050 and T-0070 (both spec): a machine-global `autopilot` layer. When either lands,
  `autopilot.sleep` becomes a candidate for it; until then it is repo-only.
- T-0019 / L-0611 (in-progress / direction), T-0012 (approved), T-0020 (approved): they edit
  `crew_autopilot.py` and `autopilot.md` too. Merge main before review, as direction.md's
  2026-09-30 note says.

Blocks:
- L-0651 to L-0656.
- T-0057 (ready): plain-text routing for `sleep` / `wake` needs L-0652.
- T-0054 (ready): the autopilot guide's sleep section.
- T-0056 (ready): a resumed goal re-checks sleep before its first decision.
- T-0073 (direction): its text assumes sleep auto-accepts only CLEAN rounds.

## Split
- L-0651 (child 1 of T-0053, filed 2026-10-04): sabotage mutations for the sleep schedule overlay (tooling-only PR)
- L-0652 (child 2 of T-0053, filed 2026-10-04): manual /crew:autopilot sleep and wake (state file under git-common-dir/crew, gated on scope.allowCliApproval)
- L-0653 (child 3 of T-0053, filed 2026-10-04): sleep log and morning summary (.work/autopilot/sleep-log.md, sleep-note, sleep-summary)
- L-0654 (child 4 of T-0053, filed 2026-10-04): sleep deploy override, nonprod only; production always waits while asleep
- L-0655 (child 5 of T-0053, filed 2026-10-04): sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only PR)
- L-0656 (child 6 of T-0053, filed 2026-10-04): sleep overrides for keys that do not exist yet (review policy, held pings) - BLOCKED until T-0029/T-0067 and T-0051 merge

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
