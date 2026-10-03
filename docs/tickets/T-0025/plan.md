# T-0025 plan            spec: .work/tickets/T-0025/spec.md

Owner approves (risk: med). Preconditions: T-0004 is merged (`crew_autopilot`) and T-0023 is merged (`crew_route`). One state reader and one phrase table (spec `## Decisions`). The surface recommendation is advisory and goes to TODO.md. The crew version is assigned at implementation. Five steps.

### Step 1: `crew_help.py where` - at most 8 lines from T-0004's reader
Files: plugin/crew/hooks/scripts/crew_help.py, plugin/crew/tests/test_crew_help.py
Where: create both. It calls `crew_autopilot.resume_target(root)` and uses its `next` (`crew_autopilot.py:338` and `:277` on T-0004's branch); read-only the way `plugin/crew/hooks/scripts/crew_status.py:1-20` is (`GIT_OPTIONAL_LOCKS=0`, `sys.dont_write_bytecode`)
Test: python3 -m pytest plugin/crew/tests/test_crew_help.py -q -k where
Risk: med. A help line that picks a ticket or names a command the disk does not support misleads the user. Every uncertain state must say so.
- [ ] `RELATED`: a dict from each `next_phase` phase name (brainstorm, direction-approval, spec, plan, approve, implement, refresh, review, accept-review, replan, stale-after-review, done, closed) to 2-3 `(command, why)` pairs, for example `implement` -> `/crew:status` (full picture), `/crew:handoff` (stopping mid-way), `/crew:autopilot <id>` (let it drive).
- [ ] `where(root) -> list[str]`, at most 8 lines. `where: <ticket> (<source>) - phase <phase>`; `waiting on: <reason>`; `next: <command> - <why>` (for a stop phase: "you type <command>"; approval is always "you type `/crew:approve <id>`"); then up to 3 `also:` lines. `resume_target` stop -> `where: no single ticket - <reason>`, `next: /crew:help <ticket-id>` or `/crew:brainstorm <idea>`, with the candidates listed. It never picks one.
- [ ] CLI `python3 crew_help.py where --root .`, exit 0 always.
- [ ] Tests: `test_where_has_at_most_8_lines` (parametrised over every phase, built with `plugin/crew/tests/crew_fixtures.py`/`scope_fixtures.py`), `test_every_phase_has_related_commands` (iterates the phase names; if T-0004 exposes no constant, the list is copied from its docstring with a comment saying so), `test_approve_phase_says_you_type_it`, `test_several_open_tickets_are_listed_not_picked`, `test_no_ticket_suggests_brainstorm`, `test_where_writes_nothing` (mtime snapshot).

### Step 2: `crew_help.py about` - a command, a question, or `commands`
Files: plugin/crew/hooks/scripts/crew_help.py, plugin/crew/tests/test_crew_help.py
Where: frontmatter `description`/`argument-hint` of `plugin/crew/commands/*.md` (e.g. `implement.md:1-5`); questions through T-0023's `crew_route.match`
Test: python3 -m pytest plugin/crew/tests/test_crew_help.py -q -k "about or group or table"
Risk: low. The output is read-only text. The risk is a second phrase table creeping in, which a test pins.
- [ ] `HELP`: for each core command, `(when, next)`, one line each (for example `spec`: "after /crew:brainstorm, to write the ticket contract", next `/crew:plan <id>`). Every other command falls back to its frontmatter `description`, with `next: /crew:help`.
- [ ] `GROUPS`: `core`, `through-help` (the 13 in the spec), `merge-candidates`, `specialist`, `removed`, exactly as the spec's advisory list. `about("commands")` prints the groups, core first, one line each.
- [ ] `about(text)`: strip a leading `/crew:`. If it names a command file -> 4 lines (purpose, when, arguments = `argument-hint` or "none", next). Else `crew_route.match(text)` (or `match("how do i " + text)`) -> that command's 4 lines, prefixed "you asked: <text>". Else the core group with "no command matched `<text>`".
- [ ] Tests: `test_every_command_file_resolves` (iterates `plugin/crew/commands/*.md`), `test_every_command_is_in_exactly_one_group`, `test_removal_stubs_are_in_removed` (`ticket`, `work`), `test_help_questions_use_the_route_table` (monkeypatch `crew_route.match` and assert it is called), `test_help_has_no_phrase_table_of_its_own` (the AST of `crew_help.py` holds no `re.compile` over prompt text), `test_about_unknown_lists_core`.

### Step 3: the `/crew:help` command and the route rows
Files: plugin/crew/commands/help.md, plugin/crew/hooks/scripts/crew_route.py, plugin/crew/tests/test_crew_route.py, plugin/crew/tests/test_lifecycle_commands.py
Where: `NEW_COMMANDS` at `plugin/crew/tests/test_lifecycle_commands.py:27-28` (cap `MAX_LINES` `:25`); `PHRASES` in `crew_route.py` (T-0023 step 1)
Test: python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_route.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: low. The command is a thin shell over step 1-2 output.
- [ ] `help.md`: frontmatter `description: What to do next, and what any crew command is for`, `argument-hint: [command | question | commands]`, `allowed-tools: Bash, Read`. The body: no argument -> run `crew_help.py where --root .`; otherwise `crew_help.py about "$ARGUMENTS"`. Print the output verbatim, add nothing, and never run the command it names. Under 40 lines.
- [ ] Register `help.md` in `NEW_COMMANDS`.
- [ ] `PHRASES` gains `help` rows -> `/crew:help`, rule `none`: `help`, `what now`, `what's next`, `where are we`; and `how do i <x>` / `how do i use <x>` -> `/crew:help <x>`, rule `topic`. Tests: `test_help_rows_match`, `test_next_and_done_alone_still_route_nowhere`, `test_no_route_ever_names_approve` still green.

### Step 4: nudges that name the one fix
Files: plugin/crew/commands/implement.md, plugin/crew/commands/review.md, plugin/crew/hooks/scripts/scope_guard.py, plugin/crew/tests/test_lifecycle_commands.py, plugin/crew/tests/test_scope_guard.py
Where: `implement.md:15-26`; `review.md:21-22`; `scope_guard.py:157-159` (the `none` reason) and the deny text `:291-296`; the sabotage anchor that must survive is `plugin/crew/tests/sabotage_scope.py:31-35`
Test: python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_approval_hook.py -q
Risk: med. `scope_guard.py` is a blocking hook. Only its message text changes, and its decision tests must stay green unchanged.
- [ ] `implement.md` step 0: run `crew_ticket.py status --ticket $1`. On `none`/`stale`: with plan.md present and `validate` clean, "stop - the user types `/crew:approve $1`"; plan.md missing -> "stop - run `/crew:plan $1`"; `validate` problems -> "stop - fix the plan (`/crew:plan $1`)". Remove the `--approve` pointer. Stay under 120 lines.
- [ ] `review.md:21-22`: the stop text becomes "no ticket id and no single active ticket - run `/crew:review <ticket-id>`; `/crew:help` lists the open ones" (still exit 1).
- [ ] `scope_guard.py`: for approval status `none`, the deny lines say "no approved plan for <id>: the user types `/crew:approve <id>`" (or "run `/crew:plan <id>`" when `.work/tickets/<id>/plan.md` does not exist). The "To widen scope" text is kept for the out-of-Touch reason only. The `if approval["status"] != "approved":` anchor text is unchanged.
- [ ] Tests: `test_implement_refusal_names_the_fix` (text contains `/crew:approve $1`, `/crew:plan $1`, and not `--approve`); `test_review_no_ticket_stop_names_a_command`; in `test_scope_guard.py`, `test_no_approval_deny_names_approve` and `test_no_plan_deny_names_plan` (module plus both flavours via the existing FLAVOURS fixture), plus an assertion that the out-of-Touch deny still says "To widen scope".

### Step 5: sabotage, docs, TODO, verify rule, version
Files: plugin/crew/tests/sabotage_help.py, plugin/crew/tests/sabotage.py, plugin/crew/README.md, TODO.md, .crew/verify.json, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md
Where: create `sabotage_help.py`; register at `plugin/crew/tests/sabotage.py:2927`
Test: python3 plugin/crew/tests/sabotage.py restricted to the HELP mutations and the existing SCOPE ones (each red on its named test, tree restored byte-identical); python3 -m pytest plugin/crew/tests/ -q serially; bash plugin/crew/hooks/scripts/_test/run-tests.sh; python3 scripts/check-marketplace.py
Risk: med. An anchor that drifts makes its mutation test nothing. This is held by `test_every_help_sabotage_anchor_is_present_exactly_once`.
- [ ] `HELP_MUTATIONS`: raise the line cap to 9 (`test_where_has_at_most_8_lines`); pick `candidates[0]` (`test_several_open_tickets_are_listed_not_picked`); add a local `re.compile` table (`test_help_has_no_phrase_table_of_its_own`); implement.md back to `/crew:plan $1 --approve` (`test_implement_refusal_names_the_fix`); scope-guard `none` text back to "To widen scope" (`test_no_approval_deny_names_approve`). Run all of them, including the existing `SCOPE_MUTATIONS`, and record red/green in the PR body.
- [ ] README: `/crew:help` in the command table's first rows, with the core group first and the rest under "more (see /crew:help commands)". No command is removed from the README.
- [ ] TODO.md: "crew command surface - owner decision" with the spec's advisory list (through-help, merge candidates, removal stubs), marked not started and ask-first.
- [ ] `.crew/verify.json` rule from the spec's Acceptance list. Version bump in plugin.json, marketplace.json and PLUGINS.md; CHANGELOG entry.

## Self-review
- Spec coverage: `where` and its 8-line cap -> step 1; `about`, questions, groups, the no-second-table check -> step 2; the command and route rows -> step 3; the three stuck refusals -> step 4; sabotage, README, TODO (advisory surface), verify rule, version -> step 5. No gap.
- Touch coverage: every Files: entry is in the spec's Touch. `crew_autopilot.py`, `crew_status.py`, `crew_fixtures.py`, `scope_fixtures.py` and `sabotage_scope.py` are read, not modified.
- Interfaces: `crew_autopilot.resume_target`/`next_phase` (T-0004) feed step 1. `crew_route.match`/`PHRASES` (T-0023) feed steps 2-3. `where`/`about` (steps 1-2) are what `help.md` (step 3) runs.
- Not verified while planning: whether T-0004 exposes a phase-name constant (step 1 says what to do if not); the exact FLAVOURS fixture shape in `test_scope_guard.py` (read at step 4).
