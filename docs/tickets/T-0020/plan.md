# T-0020 plan            spec: .work/tickets/T-0020/spec.md

Owner approves (risk: high). The approval also accepts two things from the spec's Unknowns: that every explicit active-ticket pointer is a focus, and that findings go to `.work/tickets/<id>/out-of-scope.md` when Touch does not cover TODO.md. Preconditions: T-0004 and T-0018 are merged. T-0012 and T-0019 are not required, because the router refuses `goal`/`assign` under focus whether or not they have landed. No new hook, so CLAUDE.md's "Adding a hook" does not apply. `hooks.json` is pinned unchanged by a test. Crew version: one patch past main at merge (the HANDOFF rule, not pre-assigned).

### Step 1: `crew_autopilot.py focus` over the active-ticket pointer
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_focus.py
Where: `crew_ticket.activate` `crew_ticket.py:621` (checks the id shape only), `deactivate` `:632`, `resolve_active` `:642`, `ticket_dir` `:186`; scope mode via `crew_ticket.configured_mode` `:681`; fixtures `make_repo`/`make_ticket(..., activate=False)` `plugin/crew/tests/scope_fixtures.py:63`, `:80`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_focus.py -q -k "focus_set or focus_off or focus_show"
Risk: high. A focus onto a folderless ticket is a broken pointer, and the guard then refuses every write under `block`.
- [ ] `focus_state(root)` -> `{"focus": id|None, "broken": bool, "why", "scope_mode"}`. Only source `active-ticket` is a focus. The `.work/INDEX.md` fallback reads `focus: None`
- [ ] `focus_set(root, ticket)`: refuse when there is no `.work/tickets/<id>/`, when the pointer is broken, or when focus is already on a different ticket ("focus is on T-A; type /crew:autopilot focus off first"). Otherwise `crew_ticket.activate`. The same ticket again is a no-op
- [ ] `focus_off(root)`: the only `crew_ticket.deactivate` call in the module
- [ ] `REMINDER`: "Claude Code's built-in /focus only toggles the display (just your prompt, summary, and response); it does not scope work, and only you can type it". It is appended to every `focus` output, with a `scope.mode` line: under `off`, "the scope guard is off: writes outside Touch are not refused as they happen; autopilot's drift stop still applies"
- [ ] CLI `focus --root . [--ticket <id> | --off | --findings --ticket <id>]`
- [ ] tests: `test_focus_set_writes_this_worktree_only` (two worktrees of one repo), `test_focus_refuses_folderless_ticket`, `test_focus_refuses_switch`, `test_focus_same_ticket_is_noop`, `test_focus_off_clears_this_worktree_only`, `test_focus_show_index_fallback_is_not_focus`, `test_focus_show_broken`, `test_focus_output_carries_reminder`, `test_focus_scope_off_says_so`

### Step 2: `focus_guard` in the router - no start, no switch
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_focus.py
Where: T-0018's `route` (and its `AVAILABLE`); T-0004's `resume_target` (handoff first, then pointer)
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_focus.py -q -k guard
Risk: high. This is the lock itself. An allow-by-default branch here is the rabbit hole the owner asked to close.
- [ ] `focus_guard(root, sub, ticket)` returns None or a refusal. Focused on T-A: `run` with no ticket or with T-A is allowed; `run` with another ticket is refused; `resume_target` naming another ticket (from the handoff) is refused with both named; `assign` and `goal` are refused; `status` and `focus off` are always allowed. A broken pointer refuses all but `status` and `focus off`
- [ ] `route` calls `focus_guard` after resolving the subcommand, so `assign`/`goal` are refused even while they are unavailable
- [ ] `AVAILABLE` gains `focus`, and `ARRIVES` loses it
- [ ] tests: `test_guard_allows_focused_ticket`, `test_guard_refuses_other_ticket`, `test_guard_refuses_handoff_other_ticket`, `test_guard_refuses_assign`, `test_guard_refuses_goal`, `test_guard_allows_status_and_focus_off`, `test_guard_broken_pointer_refuses`, `test_guard_index_fallback_is_no_focus`

### Step 3: drift stop and where findings go
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_focus.py
Where: `completion_audit.audit` `completion_audit.py:112` (read-only; unapproved Touch fails every path `:126-145`); `crew_ticket.accepted` `crew_ticket.py:525`; `crew_ticket.in_touch` `:376`, `touch_for` `:722`; T-0004's `next_phase`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_focus.py -q -k "drift or findings"
Risk: high. An audit that raised or could not run must stop, not pass.
- [ ] in `next_phase`, only when `focus_state` names this ticket and `accepted` is `approved`: `audit(root, ticket)`. `(False, lines)` -> phase `drift`, `stop: true`, reason = the first two lines, command empty. An exception -> `drift` with "the audit could not run". Otherwise unchanged
- [ ] `findings_target(root, ticket)` -> `TODO.md` when `in_touch("TODO.md", touch)`, else `.work/tickets/<id>/out-of-scope.md`, with the reason "the scope guard exempts nothing outside Touch"
- [ ] tests: `test_drift_stops_on_path_outside_touch`, `test_drift_not_judged_before_approval`, `test_drift_audit_exception_stops`, `test_unfocused_next_unchanged` (T-0004 fixtures, same output), `test_findings_todo_when_in_touch`, `test_findings_ticket_file_when_not_in_touch`

### Step 4: the `focus` section in `autopilot.md`
Files: plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_autopilot_focus.py
Where: T-0018's router section and line budget; T-0004's loop, whose `stop=1` handling already covers `drift`
Test: python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_focus.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: med
- [ ] section, 6 lines or fewer: `focus <ticket>` / `focus off` / `focus` map to the CLI, and its output is printed as-is. While focused, an out-of-scope finding is written to `focus --findings`'s target as a TODO entry (path:line, why deferred, what unblocks it) and never fixed in the diff. Autopilot never runs `focus off` unless the owner's own arguments are `focus off`
- [ ] tests: `test_focus_section_at_most_6_lines`, `test_command_still_at_most_120_lines`, `test_focus_off_named_only_in_focus_section`, `test_deactivate_has_one_call_site` (AST over `crew_autopilot.py`), `test_hooks_json_unchanged` (byte-compare with `git show HEAD:plugin/crew/hooks/hooks.json` at the base)

### Step 5: sabotage, verify rule, docs, version
Files: plugin/crew/tests/sabotage_autopilot.py, .crew/verify.json, plugin/crew/README.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md
Where: `AUTOPILOT_MUTATIONS` (T-0004), registered at `sabotage.py:2927`
Test: python3 plugin/crew/tests/sabotage.py restricted to the new mutations; python3 -m pytest plugin/crew/tests/ -q serially; bash plugin/crew/hooks/scripts/_test/run-tests.sh; python3 scripts/check-marketplace.py
Risk: low
- [ ] mutations: INDEX fallback read as focus (`test_guard_index_fallback_is_no_focus`); `focus_guard` returns None for another ticket (`test_guard_refuses_other_ticket`); drift reads `ok=False` as a pass (`test_drift_stops_on_path_outside_touch`); a `crew_ticket.deactivate` call added to `next_phase` (`test_deactivate_has_one_call_site`)
- [ ] anchor-presence test extended. Run all four and record which went red in the PR body. Any green mutation is a finding
- [ ] `.crew/verify.json`: add `test_crew_autopilot_focus.py` to the autopilot rule
- [ ] README "Scope and approval": focus is the active-ticket pointer; what it refuses; the drift stop; findings; the limit under `scope.mode: off`; the `/focus` reminder. Bump the crew version in plugin.json, marketplace.json and PLUGINS.md; add a CHANGELOG entry that names the rabbit-hole ask it answers

## Self-review
- Spec coverage: set, off, show, per worktree, reminder, scope-off note -> 1; no start or switch, and the broken pointer -> 2; drift and findings -> 3; prose, single call site and unchanged hooks -> 4; sabotage, verify, docs and version -> 5.
- Touch coverage: every Files: entry is in the spec's Touch. `crew_ticket.py`, `scope_guard.py`, `completion_audit.py`, `scope_fixtures.py` and `hooks.json` are read, not modified.
- Interfaces: `focus_state` (1) is what 2 and 3 read. `focus_guard` (2) is called by T-0018's `route`. `findings_target` (3) is what 4's prose names. `audit` and the pointer functions come from main unchanged.
- Read while planning: `completion_audit.audit` calls `scope_base.resolve` (`scope_base.py:242`), which reads the record and runs git reads only. Not yet proven by a test: that nothing is written when `next` calls it in-process. Step 3's drift tests should also hash `<git-common-dir>/crew/` before and after. Not verified: how `route` receives `$2` for `focus off`, which T-0018 settles when it fixes argument passing.
